# Agent Framework Design Patterns

通用的 agent 框架设计要点。从一个生产级"循环推理"项目里抽象出来,与具体业务无关,适用于任何"逐步深化 + 中间产物 + 自评估终止"类的 agent 任务。

---

## 一、核心架构模式:Cycle Framework

```
┌────────────────────────────────────────────────────────────┐
│                                                            │
│   ┌──────────┐   ┌─────────┐   ┌────────────┐              │
│   │ Producer │ → │ Joiner  │ → │ Controller │              │
│   │ (生新)   │   │ (配匹)  │   │ (要继续吗?)│              │
│   └────┬─────┘   └────┬────┘   └──────┬─────┘              │
│        │              │               │                    │
│        ↓              ↓               ↓                    │
│      tools/        external       rules first,             │
│      skills       data pool       LLM fallback             │
│                                                            │
│   loop until controller stops OR max_depth reached         │
└────────────────────────────────────────────────────────────┘
```

**三个职责单一的 agent 串成循环**,每个 agent 只做一件事:

| 角色 | 职责 | 输出特点 |
|------|------|----------|
| **Producer** | 基于上下文生成新内容/假设/候选 | 结构化列表,带 confidence |
| **Joiner** | 把 Producer 的产物配到外部数据/资源 | 关联 + 评分 |
| **Controller** | 评估当前进展,决定是否再循环一轮 | 二值决策 + 理由 + 摘要 |

**适用场景(只要符合这个形状):**
- 多步推理(假设 → 验证 → 判断够不够)
- 代码生成(写 → 检索上下文 → 自评估)
- 研究助手(问题 → 取证据 → 充分性判断)
- Bug 排查(假设 → 复现 → 收敛判断)
- DocQA(查询扩展 → 检索 → 答案完整度判断)

---

## 二、Skill 系统(框架灵魂)

### 2.1 Skill = 文件 + 自动发现

把"领域方法论 / SOP"做成可插拔的文件,运行时自动扫描注册:

```python
# 核心模式:扫目录 → 找指定符号 → 自动注册
for module_info in pkgutil.iter_modules([skills_dir]):
    mod = importlib.import_module(...)
    if hasattr(mod, "SKILL"):
        registry[mod.SKILL.name] = mod.SKILL
```

**收益:** 领域专家(非工程师)写一个文件即扩展系统能力。不改 router、不改 agent、不写注册代码。

### 2.2 Skill 是结构化模型,不是字符串

不要用 dict / 裸字符串。用 Pydantic 模型,IDE 提示 + 校验 + 自动文档:

```python
class Skill(BaseModel):
    name: str
    description: str               # 一行,用于路由
    framework: str                 # 完整的方法论 prompt
    output_schema: type[BaseModel] # 强约束的输出格式
    relevance_embedding: list[float] | None = None  # 用于动态路由
```

### 2.3 角色化 Skill 子集

不同 agent 拿不同的 skill 列表(共享池,按需取):

```python
PRODUCER_SKILLS = ["skill_a", "skill_b", "skill_c"]
JOINER_SKILLS   = ["skill_d", "skill_e"]
```

**避免:** 所有 agent 加载所有 skill — prompt 巨大,token 浪费,模型注意力分散。

### 2.4 两种注入策略,按模型能力选

```python
build_prompt(allowed_skills)             # 只注 description,让 agent 用 LoadSkill 工具按需取
build_prompt_full(allowed_skills)        # 直接把全部 framework 拼进 system prompt
```

经验法则:
- 工具调用稳定的强模型(Claude Sonnet 4+, GPT-4o+)→ 用前者,省 token
- 工具调用不稳的模型 → 用后者,稳定性 > token 成本

### 2.5 进阶:Embedding-based Skill Router

静态的 `[a, b, c]` 列表不够好。用 small LLM 或 embedding 在执行前选 1-3 个最相关 skill:

```python
async def route_skills(context: str, k: int = 3) -> list[Skill]:
    ctx_emb = await embed(context)
    return top_k_by_cosine(ctx_emb, all_skills, k=k)
```

---

## 三、Controller 设计原则

### 3.1 规则优先,LLM 兜底

**70% 的"是否继续"决策不需要 LLM**:

```python
def should_continue(state) -> bool:
    if not state.new_items:           return False  # 没新东西
    if state.depth >= max_depth:      return False  # 到底了
    if state.avg_confidence < thresh: return False  # 太虚了
    # 只有以上都不命中,才烧 token 让 LLM 评估
    return llm_judge(state)
```

### 3.2 Controller 输出三件套

```python
class ControllerOutput(BaseModel):
    should_continue: bool
    reasoning: str        # 决策依据(给人看)
    summary: str          # 截至目前的链条摘要(给下轮用)
```

`summary` 的设计很关键 — 它是把多轮上下文压缩成 LLM 可消化体积的核心手段。

---

## 四、输出可靠性:多级降级解析

### 4.1 主路径:Pydantic 强约束

```python
class ProducerOutput(BaseModel):
    items: list[Item]

resp = await llm.complete(..., response_model=ProducerOutput)
# 主路径直接拿到强类型对象,无需手动 parse
```

### 4.2 降级路径:多策略 JSON 提取

主路径失败时(模型没遵守 schema),用 fallback parser:

```python
def parse_json_response(raw: str) -> dict | None:
    # Strategy 1: markdown 代码块 ```json ... ```
    # Strategy 2: 直接 json.loads
    # Strategy 3: 剥离 XML 风格 tool_call 块
    # Strategy 4: 大括号匹配,找第一个完整 JSON 对象
```

**核心原则:** 永远不要寄希望于 LLM 100% 输出合法 JSON,但也不要因为偶发不合法就整个失败。

---

## 五、流式输出 + 批结构化共存

### 5.1 双路径同构

提供两个并行实现,共用核心逻辑:
- **Batch 模式** — 简单可靠,一次 LLM 调用拿全文
- **Stream 模式** — 边生成边推前端,UX 好

**复用关键:** Prompt 构造、节点构造逻辑两边共享,只在"LLM 调用 + 解析"层分叉。

### 5.2 流式 + 批构造的 ID 对齐技巧

流式时已经给前端推了 `node_start(id=xxx)`,等全文到齐后批量构造结构化对象,再用 `index_to_id` 字典把构造对象的 ID 改写成已推送的 ID:

```python
batch_to_stream: dict[str, str] = {}
for idx, node in enumerate(constructed_nodes):
    if stream_id := index_to_id.get(idx):
        batch_to_stream[node["id"]] = stream_id
        node["id"] = stream_id

# 同步重写所有引用该 ID 的 edge
for edge in edges:
    edge["source"] = batch_to_stream.get(edge["source"], edge["source"])
    edge["target"] = batch_to_stream.get(edge["target"], edge["target"])
```

**好处:** 既有流式 UX,又有批的结构化校验。

### 5.3 增量 JSON 解析器

流式 JSON 解析三个要点:

1. **用现成库** — `json_repair` (Python) 或同类,别手搓状态机
2. **追踪每字段已发字符数** — `{index: {field: char_count}}`,只发 delta 避免重复推流
3. **三种事件** — `item_start` / `item_text(delta)` / `item_complete`

```python
class IncrementalParser:
    def feed(self, chunk: str) -> list[Event]:
        self._buffer += chunk
        repaired = repair_json(self._buffer, return_objects=True)
        # 比较新旧字段长度,emit 增量
        ...
```

---

## 六、Tool 设计原则

### 6.1 Tool 内自降级,永不让 agent 看到失败

```python
async def fetch_external(query):
    budgets = await check_quotas()
    if not any(budgets.values()):
        return await local_fallback(query)   # 配额耗尽 → 退本地
    if budgets["primary"]:
        results.extend(await call_primary(...))
    if need_more and budgets["secondary"]:
        results.extend(await call_secondary(...))
    return results  # 永远非空
```

**为什么:** Agent 看到 error 后会开始"自我修复式胡说"。返回降级数据 > 抛错。

### 6.2 工具调用顺序写在 prompt 里,不写死代码

```python
TOOL_USAGE_GUIDE = """
TOOLS (use in this order):
1. cheap_search — handles 80% of queries. Start here.
2. inspect — see what's there before drilling.
3. expensive_full_scan — only if cheap_search insufficient.
4. raw_query — last resort.
"""
```

**好处:** 换模型/换场景只改文本,不改 router 代码。

### 6.3 Tool schema 用 Pydantic,自动生成

```python
class SearchInput(BaseModel):
    query: str = Field(..., description="...")
    limit: int = Field(default=20, ge=1, le=100)

class SearchTool(BaseTool):
    args_schema = SearchInput  # 自动生成 OpenAI/Anthropic tool 定义
```

---

## 七、Pipeline 编排原则

### 7.1 每个 agent 的失败语义不同

不要用统一的 try/except 兜底。失败处理要符合"它失败对全局意味着什么":

| Agent | 失败时 |
|-------|--------|
| **Producer** | 整层放弃,`should_continue=False`(没源数据没法推) |
| **Joiner** | 这层无 join 结果,**继续推下一层**(配对是锦上添花) |
| **Controller** | 用规则兜底决策(`depth < threshold ? continue : stop`) |

### 7.2 Retry + Timeout + 优雅取消

```python
async def call_with_retry(func, *args, **kwargs):
    for attempt in range(1 + MAX_RETRIES):
        try:
            return await asyncio.wait_for(
                run_in_executor(func, *args, **kwargs),
                timeout=AGENT_TIMEOUT_S,
            )
        except asyncio.CancelledError:
            raise  # 永远不吞 cancel,优雅关闭必备!
        except Exception:
            await asyncio.sleep(min(2**attempt, 10))  # 指数退避
    raise
```

**关键:** `CancelledError` 必须 re-raise。90% 的 Python 代码漏写,导致 SIGTERM 时进程挂起。

### 7.3 用状态机,不用 for 循环

❌ **不推荐:**
```python
for layer in range(max_depth):
    state = await run_layer(state)
    if not state.should_continue: break
```

✅ **推荐:** LangGraph / Burr / 自建 state machine
- 自带 checkpointer,可中断可恢复
- 节点关系可视化
- 出错可从最近 checkpoint 重跑,不用从头

---

## 八、上下文窗口管理

### 8.1 老压新留策略

多轮推理时,直接父节点保完整 reasoning,祖父及以上截断:

```python
def prepare_context(nodes, current_depth):
    for n in nodes:
        if current_depth - n.depth > 1 and len(n.reasoning) > LIMIT:
            n.reasoning = n.reasoning[:LIMIT] + "…"
    return nodes
```

简单粗暴但极其有效。比 RAG 召回 + rerank 便宜 100 倍,效果不差多少。

### 8.2 Chain Summary 滚动压缩

每轮 controller 输出一个 `summary` 字段,浓缩到目前为止的整条链。下轮把 summary 当历史,而不是把全部历史塞进去。

---

## 九、可观测性

### 9.1 别用字符串日志记 token/latency

❌ `log.info("AGENT L%d | %.1fs | tokens=%d", ...)`

✅ OpenTelemetry span:
```python
@traced(name="producer_layer")
async def run_producer(...):
    span.set_attribute("layer", layer)
    span.set_attribute("tokens", tokens)
    span.set_attribute("model", model_name)
```

### 9.2 推荐栈

- **Trace:** OpenTelemetry SDK
- **后端:** Langfuse(开源,自托管) / Phoenix(Arize 出品) / LangSmith
- **好处:** 多 agent 调用关系一键看 trace 树,token/cost/latency 自动收集,失败链路可重放

---

## 十、技术选型建议

### ✅ 推荐栈(2025 现代化版)

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Orchestration                                     │
│    LangGraph (state machine, 持久化)                        │
│    或 Burr (轻量,可视化)                                   │
│    或 Temporal (重型 workflow,适合长任务)                  │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Agent (LLM call)                                  │
│    Pydantic AI (推荐,async-native + schema 第一)           │
│    或 Anthropic SDK / OpenAI SDK 直调                      │
│    避免:CrewAI(sync 限制)、LangChain Agent(过度抽象)   │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Skill System                                      │
│    自建 — 目录扫描 + Pydantic Skill 模型                    │
│    可选:embedding-based router                            │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: Tools                                             │
│    全 async function,Pydantic schema 自动生成定义          │
│    工具内自降级                                            │
├─────────────────────────────────────────────────────────────┤
│  Layer 5: Streaming                                         │
│    SSE 或 WebSocket                                         │
│    json_repair 库做增量 JSON 解析                          │
├─────────────────────────────────────────────────────────────┤
│  Layer 6: Observability                                     │
│    OpenTelemetry → Langfuse / Phoenix                      │
└─────────────────────────────────────────────────────────────┘
```

### ❌ 反模式清单(踩过的坑)

| 反模式 | 为什么避免 |
|--------|-----------|
| `ThreadPoolExecutor + asyncio.run` 包 async 工具 | event loop 嵌套,context var 丢失,死锁风险 |
| 用 sync-first 框架(CrewAI 等)做生产 | 高并发下问题多,不如直调 LLM SDK |
| Skill / 配置用裸 dict | 无校验,IDE 无提示,refactor 易翻车 |
| 静态写死 skill 列表 | 浪费 token,模型注意力分散 |
| `for ... in range()` 当主循环 | 不可恢复,出错从头跑 |
| 字符串日志记结构化数据 | 无法 query,无 trace 关联 |
| 工具失败抛 error 给 agent | Agent 会开始"自我修复式胡说" |
| 寄希望于 LLM 100% 合法 JSON | 一定会有偶发不合法,必须 fallback |
| 统一 try/except 兜底所有 agent | 失败语义不同,处理也应不同 |
| 吞掉 `asyncio.CancelledError` | SIGTERM 时进程挂起 |

---

## 十一、最小可行框架 MVP

```python
# core/skill.py
class Skill(BaseModel):
    name: str
    description: str
    framework: str
    output_schema: type[BaseModel]

# core/registry.py
SKILLS: dict[str, Skill] = auto_discover("skills/")  # pkgutil 扫描

# core/agent.py — 替代重型 agent 框架
async def run_agent(
    role: str,
    skills: list[Skill],
    user_prompt: str,
    output_model: type[T],
    tools: list[Tool] | None = None,
) -> T:
    system = build_prompt(role, skills)
    return await llm.complete(
        system=system,
        user=user_prompt,
        tools=tools,
        response_model=output_model,
    )

# graphs/cycle.py — LangGraph 状态机
graph = StateGraph(CycleState)
graph.add_node("producer", producer_node)
graph.add_node("joiner",   joiner_node)
graph.add_node("controller", controller_node)
graph.add_edge("producer", "joiner")
graph.add_edge("joiner",   "controller")
graph.add_conditional_edges("controller",
    lambda s: "producer" if s.should_continue else END)
graph.compile(checkpointer=RedisCheckpointer())
```

200 行以内能落地一个生产级 agent 循环框架。

---

## 十二、设计原则速查表

| 原则 | 一句话 |
|------|--------|
| **职责单一** | 一个 agent 只做一件事,组合成流水线 |
| **规则优先** | 能用 if/else 决定的别问 LLM |
| **强 schema** | 所有 LLM 输出走 Pydantic,prompt 里"Return ONLY JSON"是祈祷 |
| **多级降级** | 主路径 + fallback parser + 工具自降级 + 规则兜底 |
| **流批同构** | 批模式简单可靠,流模式做 UX,共用 prompt 和构造逻辑 |
| **失败语义化** | 每个组件失败时怎么处理符合它的角色 |
| **上下文压缩** | 老内容截断,新内容保真,滚动 summary |
| **可观察** | OpenTelemetry trace 树,不要字符串日志 |
| **可恢复** | 状态机 + checkpointer,不要 for 循环 |
| **领域可插拔** | Skill 即文件,非工程师能扩展 |

---

## 适用场景速判

判断你的任务能否套这个框架,问三个问题:

1. **能不能拆成"生成 → 关联 → 评估"三步?** 不能 → 这框架不适合
2. **是否需要"多轮深化"直到某条件?** 不需要 → 简单 chain 就够,不用 cycle
3. **领域知识是否能模块化为方法论?** 不能 → 不需要 skill 系统,直接 prompt

三个都是 yes → 这套框架最合适。
