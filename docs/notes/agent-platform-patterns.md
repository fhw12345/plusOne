# Agent Platform Design Patterns

如何设计一个**通用 agent 运行时(Agent Runtime / Agent OS)**,而不是单一 agent 应用。

> 与 `agent-framework-patterns.md` 的关系:
> - 那份是 **application 级** — 解决"做一个具体的 agent 怎么做"(cycle、skill、controller)
> - 这份是 **platform 级** — 解决"做一个能承载多种 agent 的系统怎么做"(隔离、能力、生命周期、协作)
> - 当你的项目从"一个 agent"长成"很多 agent + 用户能定制"时,从前者过渡到后者

---

## 核心思想:Agent 是五个正交维度的组合

不要把"agent"当一个整体抽象,把它拆成五个互相独立的维度,每个维度有自己的扩展机制:

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   ┌────────────┐   ┌────────────┐   ┌────────────┐               │
│   │ 1. 执行    │   │ 2. 能力    │   │ 3. 领域    │               │
│   │   上下文   │   │   边界     │   │   知识     │               │
│   │ (Where)    │   │ (What)     │   │ (How)      │               │
│   └────────────┘   └────────────┘   └────────────┘               │
│                                                                  │
│   ┌────────────────────────┐  ┌────────────────────────┐         │
│   │ 4. 生命周期事件        │  │ 5. 协作关系            │         │
│   │   (When)               │  │   (Who with whom)      │         │
│   └────────────────────────┘  └────────────────────────┘         │
│                                                                  │
│   一个 agent 实例 = 这五个维度的具体配置                         │
└──────────────────────────────────────────────────────────────────┘
```

任意维度独立演进,不互相耦合。这是 application → platform 的关键跃迁。

---

## 维度 1:执行上下文(Where)

### 1.1 问题

Agent 在哪里跑?同进程?子进程?子机器?这决定了:
- 隔离强度(state 污染、内存泄漏、崩溃影响范围)
- 启动成本(进程 fork 几百毫秒、远程网络几秒)
- 可观察性(同进程能 attach debugger,远程只能看日志)

### 1.2 抽象:Task 多态 + 统一 kill 协议

```python
class Task(Protocol):
    name: str
    type: TaskType
    
    async def kill(self, task_id, set_state) -> None: ...
    # 注意:只有 kill 是接口里的!spawn / render / status 都不强制
```

**只统一终止协议,不统一启动协议。** 因为:
- 启动差异巨大(进程 fork vs HTTP 创建 vs 同进程 await)
- 终止永远只有一件事 — "停下并清理"

### 1.3 五种典型实现

| 类型 | 隔离机制 | 启动成本 | 适用场景 |
|------|----------|----------|----------|
| **InProcessTask** | AsyncLocalStorage / Context Var 隔离 state | ~0 | 轻量协作,同 host 多 agent |
| **LocalShellTask** | 子进程 + stdio | ~50ms | 跑外部 CLI 工具 |
| **LocalAgentTask** | fork 子进程,独立内存 | ~300ms | 重型后台任务,不污染主进程 |
| **RemoteAgentTask** | HTTP/WS 跨机 | ~1-3s | 跨地域、需要不同硬件 |
| **DreamTask / IdleTask** | 独立后台 worker | ~0(已起) | 后台慢任务(整理记忆、定期分析) |

### 1.4 关键设计

**Task 接口有意"贫瘠"** — 只暴露最小公约数。富特性下沉到具体子类:

```python
class InProcessTask(Task):
    queue: asyncio.Queue        # 消息队列(只有进程内任务有)
    state_token: ContextToken   # AsyncLocalStorage handle
    
class RemoteAgentTask(Task):
    transport: HybridTransport  # WS+HTTP(只有远程任务有)
    reconnect_policy: Policy
```

**为什么贫瘠是好事:** 上层调度器只需要知道"我能 kill 你",不需要管你内部怎么跑。新增一种 Task 类型不影响调度器。

### 1.5 反模式

❌ "所有 agent 都跑在主进程里" — 一旦有重型/不可信 agent,主进程就被拖死或污染
❌ "所有 agent 都 fork 子进程" — 轻量协作场景白白付 fork 成本
❌ "Task 接口包含 100 个方法" — 每加一种新 Task 类型都要实现一堆无意义方法

---

## 维度 2:能力边界(What)

### 2.1 问题

每个 agent 实例能用哪些工具?这决定了:
- 安全边界(只读 agent 不能写文件)
- token 成本(工具越多 schema 越大,prompt 越贵)
- 模型行为(工具集大模型容易选错)

### 2.2 抽象:Tool + Permission 双层

```python
# Tool — 能力定义
class Tool(Protocol):
    name: str
    input_schema: BaseModel              # Pydantic / Zod, schema 即真理源
    is_read_only: bool                   # 用于权限策略
    is_concurrency_safe: bool            # 用于并发调度
    
    async def call(self, input, ctx) -> ToolResult: ...
    async def check_permissions(self, input, ctx) -> Decision: ...
    def description(self) -> str: ...
    def render(self, ...) -> ...: ...    # UI 渲染(可选)

# PermissionContext — 运行时策略
class PermissionContext:
    mode: Literal["default", "plan", "auto", "bypass"]
    always_allow: list[Rule]
    always_deny: list[Rule]
    require_confirmation: bool
```

### 2.3 关键设计

#### A. **Schema 单一真理源**

```python
class FileEditInput(BaseModel):
    path: str = Field(description="absolute path")
    old_string: str
    new_string: str
    replace_all: bool = False

# 一份 Pydantic 定义同时是:
# - 模型可见的 JSON Schema(自动生成)
# - 运行时输入校验
# - IDE 补全提示
# - 文档
```

#### B. **工具自报副作用属性**

```python
class BashTool(Tool):
    @property
    def is_concurrency_safe(self) -> bool:
        # 关键:工具最懂自己,不要让上层 router 决定
        return False  # bash 可能改文件
    
class FileReadTool(Tool):
    @property
    def is_concurrency_safe(self) -> bool:
        return True   # 纯读
```

调度器:
```python
async def run_tool_calls(calls):
    safe = [c for c in calls if c.tool.is_concurrency_safe(c.input)]
    unsafe = [c for c in calls if not c.tool.is_concurrency_safe(c.input)]
    
    safe_results = await asyncio.gather(*[c.run() for c in safe])
    unsafe_results = []
    for c in unsafe:
        unsafe_results.append(await c.run())   # 串行
```

#### C. **三层权限决策**

```
1. Tool 自检:    tool.check_permissions(input, ctx)        # 工具级业务逻辑
2. 全局规则:     match against always_allow / always_deny   # 用户配置规则
3. 模式策略:     mode == "plan" → 拦截所有写操作            # 全局开关
```

任意一层 deny → 拒绝。规则匹配支持 glob 模式(`Bash(git *)`、`FileEdit(/etc/**)`)。

### 2.4 工具暴露给模型的策略

不是简单"全暴露"。按 agent 角色过滤:

```python
COORDINATOR_TOOLS = ["TaskCreate", "SendMessage", "Agent", ...]
WORKER_TOOLS = ["Bash", "FileEdit", "Read", ...]
PLAN_MODE_TOOLS = [t for t in ALL if t.is_read_only]

def get_tools_for_agent(agent_role, mode):
    base = ROLE_TOOL_MAP[agent_role]
    if mode == "plan":
        base = [t for t in base if t.is_read_only]
    return base
```

---

## 维度 3:领域知识(How)

### 3.1 问题

Agent 知道怎么干这个领域的活吗?方法论从哪来?

### 3.2 抽象:Skill 三层来源 + 两种执行模式

#### A. 三层来源(优先级 bundled < user < project)

```
1. Bundled Skills      — 编译时打包,所有用户共享(框架内置)
2. User Skills         — ~/.claude/skills/  (用户全局)
3. Project Skills      — .claude/skills/    (项目特定,跟 git 走)
4. MCP Skills          — MCP server 暴露的 prompt/resource 自动包装
```

合并策略:同名时**后者覆盖前者**(project 覆盖 user 覆盖 bundled)。

#### B. Skill 文件格式(已成事实标准 — Anthropic Skills)

```markdown
---
name: financial-analysis
description: Analyze financial reports with macro context  # 用于路由匹配
when_to_use: User asks about earnings, valuation, or macro impact
allowed_tools: ["Read", "Grep", "Bash"]
---

# Skill body — 完整方法论 prompt

## Step 1: ...
## Step 2: ...
```

**Frontmatter 是 schema,body 是 prompt。** 解析后:

```python
class Skill(BaseModel):
    name: str
    description: str
    when_to_use: str
    allowed_tools: list[str]
    body: str
    source: Literal["bundled", "user", "project", "mcp"]
```

#### C. 两种执行模式

| 模式 | 实现 | 何时用 |
|------|------|--------|
| **Inline 拼 prompt** | 把 skill body 拼进当前 agent 的 system prompt | 轻量、频繁、需要保持上下文 |
| **Fork 子 agent** | 把 skill 当 task 派发给一个新的 agent 实例,独立 token 预算和工具集 | 重型、隔离、避免污染主上下文 |

**关键判断标准:**
- Skill 是"提供方法论" → inline
- Skill 是"完整执行某任务" → fork

### 3.3 Skill 路由(动态选取)

不要硬编码 `THINKER_SKILLS = [...]`。三种路由策略:

| 策略 | 实现 | 适用 |
|------|------|------|
| **静态匹配** | 角色 → skill 列表写死 | 场景固定时 |
| **关键词** | 用 `when_to_use` 描述匹配用户输入 | 中等成本,够用 |
| **Embedding** | skill description 预计算 embedding,cosine 选 top-k | 高质量,贵一点 |
| **小模型路由** | 让 GPT-4o-mini 选 1-3 个 skill | 最准,最贵 |

### 3.4 反模式

❌ Skill 是 dict / 裸字符串 — 用 frontmatter + Pydantic
❌ Skill 全部 inline 拼 prompt — token 爆炸,改用 fork
❌ Skill 全部 fork — 轻量任务付不起 fork 成本
❌ Skill 列表硬编码 — 加新 skill 要改代码

---

## 维度 4:生命周期事件(When)

### 4.1 问题

Agent 跑起来后,在哪些时刻别人需要"插一脚"?
- 启动时注入额外上下文
- 每次工具调用前审计/拦截
- 每轮结束后提取记忆 / 通知队友
- 上下文压缩前后做自定义处理

### 4.2 抽象:Hook 系统 = 用户可注册的生命周期回调

```python
class HookEvent(Enum):
    SessionStart      # 会话开始
    PreToolUse        # 工具调用前
    PostToolUse       # 工具调用后
    Stop              # 一轮结束(模型不再产出)
    PreCompact        # 上下文压缩前
    PostCompact       # 上下文压缩后
    TaskCreated       # 新任务创建
    TaskCompleted     # 任务完成
    UserPromptSubmit  # 用户输入提交时
```

### 4.3 关键设计:Hook 是 shell 命令,不是代码

```jsonc
// settings.json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "command": "audit-bash.sh" }
    ],
    "Stop": [
      { "command": "extract-memory.py" }
    ]
  }
}
```

**Hook 协议:**
- Claude spawn 子进程,事件数据通过 stdin 传 JSON
- Hook 通过 stdout 返回 JSON 决定:`allow` / `deny` / `modify input` / `inject context`
- 默认 15s 超时,异步 hook 可在 `AsyncHookRegistry` 注册长任务

### 4.4 为什么这个设计是金标准

| 对比 | Plugin SDK | Hook (shell 命令) |
|------|-----------|-------------------|
| 学习成本 | 学语言 / API / 打包 | 写 shell 脚本即可 |
| 部署 | 安装、版本管理 | 拷贝文件 |
| 调试 | 重启 / attach | 直接跑脚本看输出 |
| 跨语言 | 绑死框架语言 | 任何语言 |
| 用户门槛 | 必须是程序员 | 写过 shell 就行 |

**Hook 是"agent 框架的扩展点"的最干净抽象。**

### 4.5 异步 Hook + 全局注册表

```python
class AsyncHookRegistry:
    pending: dict[str, PendingHook]  # processId → hook
    
    def register(self, hook):
        self.pending[hook.process_id] = hook
    
    def collect_results(self):
        # 主循环每轮检查一次,完成的 hook 把结果合并进 context
        for pid, hook in list(self.pending.items()):
            if hook.is_done():
                yield hook.result
                del self.pending[pid]
```

**好处:** 长时间 hook(比如调用外部 API)不阻塞主 agent,结果异步收回。

---

## 维度 5:协作关系(Who with whom)

### 5.1 问题

多个 agent 之间怎么协调?有没有指挥官?消息怎么传?谁负责终止谁?

### 5.2 三种典型协作模式

#### A. **Coordinator + Workers(主从)**

```
Main Agent (Coordinator)
   ├─ spawn Worker 1 ─→ 报告通过 SendMessage
   ├─ spawn Worker 2 ─→ 报告通过 SendMessage
   └─ spawn Worker 3 ─→ 报告通过 SendMessage
```

实现要点:
- Worker 工具集是 main 工具集的**子集** — 比如 worker 没有 `TaskCreate`、`TeamCreate`(防止递归生 agent)
- Worker 完成或 idle 时主动 `SendMessage` 给 coordinator
- Coordinator 通过 `Agent` 工具 spawn worker,通过 `SendMessage` 接收回报

#### B. **Peer Teammates(对等团队)**

```
Team:
  ├─ Agent A ←→ Agent B ←→ Agent C
  └─ 共享 TaskList
```

实现要点:
- 团队 = TaskList,所有成员都能 claim/complete task
- 通过 `SendMessage` 互相通信(支持广播)
- 没有固定指挥关系,谁拿到 task 谁干

#### C. **Pipeline(流水线 — Nexis 范式)**

```
Producer → Joiner → Controller → (loop back)
```

详见 `agent-framework-patterns.md`。

### 5.3 消息传递机制

#### 进程内(InProcessTask)

```python
class InProcessTeammate:
    pending_messages: asyncio.Queue
    
    async def receive(self, msg):
        await self.pending_messages.put(msg)
    
    async def main_loop(self):
        while True:
            msg = await self.pending_messages.get()
            # 把 msg 注入下一轮 user prompt
            await self.process(msg)
```

#### 跨进程 / 远程

走 HybridTransport(详见维度 1.3 的 RemoteAgentTask):
- WS 入(streaming output)
- HTTP 出(user message + permission response)

### 5.4 关键设计:消息有类型

```python
class Message(BaseModel):
    type: Literal["text", "shutdown_request", "shutdown_response",
                  "plan_approval_request", "plan_approval_response",
                  "task_handoff", "broadcast"]
    from_: str
    to: str
    content: dict
```

**为什么有类型:** Coordinator 需要识别"shutdown 请求"和"普通文本",不能都当字符串处理。

### 5.5 反模式

❌ 所有 agent 同进程裸 await 调用对方 — 没有终止协议、没有隔离、死锁难调
❌ 用全局变量当消息总线 — 没法测试、无法跨进程
❌ 每条消息都是 str — 无法区分控制信令和业务内容

---

## 跨维度的核心机制

下面这些不属于任何单一维度,是跨维度的"基础设施":

### A. 主循环:`while(true)` + 多 stop signal

```python
async def query_loop(state):
    while True:
        # 1. 调模型(流式)
        async for chunk in call_model(state):
            yield chunk
        
        # 2. 跑工具(并发安全的并行)
        state = await run_tools(state)
        
        # 3. 跑用户 hook
        state = await run_stop_hooks(state)
        
        # 4. 检查所有 stop signal
        for signal in [
            check_token_budget,
            check_diminishing_returns,  # ★ 模型在原地打转?
            check_user_interrupt,
            check_model_finished,
            check_max_depth,
        ]:
            if signal(state).should_stop:
                return state
        
        # 5. 否则继续
```

**Diminishing returns 检测**(防止模型原地打转):
```python
def check_diminishing_returns(state):
    if state.continuation_count >= 3:
        recent_token_deltas = state.last_3_token_deltas
        if all(d < 500 for d in recent_token_deltas):
            return StopSignal("diminishing returns")
```

### B. Token Budget + 三级 Compaction

| 级别 | 何时触发 | 做什么 |
|------|----------|--------|
| **autoCompact** | token 用量到 50%/75%/90% 阈值 | 总结早期消息,保留近期 |
| **reactiveCompact** | 模型连续报"context too large" | 保留 prompt cache,只压 cache delta |
| **snipCompact** | 后台周期任务 | 删除已撤销/重试的"僵尸消息" |

### C. State + Signal 双原语

```python
# 状态快照(谁在哪、当前模式是什么)
class Store(Generic[T]):
    def get_state(self) -> T: ...
    def set_state(self, updater): ...
    def subscribe(self, listener): ...

# 事件信号(某事发生,无状态)
class Signal(Generic[Args]):
    def emit(self, *args): ...
    def subscribe(self, handler): ...
```

**别全塞 Store(过度耦合),也别全用 Signal(无法 query 当前状态)。** 状态用 Store,事件用 Signal。

### D. HybridTransport(WS 入 + HTTP 出 + 背压)

```python
class HybridTransport:
    ws_in: WebSocket            # streaming inbound
    http_out: SerialBatchUploader  # batched outbound
    
    BATCH_FLUSH_INTERVAL_MS = 100
    
    async def write(self, event):
        await self.http_out.enqueue(event)  # 满了会 block!
    
class SerialBatchUploader:
    async def enqueue(self, event):
        if self.queue.qsize() >= self.max_size:
            # 关键:返回 Promise 阻塞调用方,而不是丢数据
            await self.wait_for_space()
        self.queue.put(event)
```

### E. 多入口分叉

```bash
mytool                    # 普通交互 CLI
mytool --print            # 流式 JSON 输出(脚本管道)
mytool --mcp-server       # 暴露为 MCP server
mytool --bridge           # 桥接模式(连远程)
mytool --daemon-worker    # 后台 worker
```

同一份代码,不同入口路径。**这才是真"agent runtime"** 而不是单一 CLI。

---

## 现代化技术栈推荐(2025)

### 整体技术选型

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Runtime / Process Model                           │
│    Node.js / Python asyncio (async generator 主循环必需)   │
│    多入口:cli / mcp / bridge / daemon-worker              │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Orchestration                                     │
│    应用级:LangGraph (state machine + checkpointer)         │
│    平台级:自建 query loop(参考 Claude Code)              │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: LLM 调用                                          │
│    Pydantic AI / Anthropic SDK / Vercel AI SDK             │
│    避免:CrewAI(sync 限制)                                │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: Schema                                            │
│    Zod (TS) / Pydantic (Python)                            │
│    自动生成 JSON Schema 喂给模型                           │
├─────────────────────────────────────────────────────────────┤
│  Layer 5: Skill 系统                                        │
│    格式遵循 Anthropic Skills 标准(frontmatter + md)       │
│    三层来源 + 自动发现                                     │
├─────────────────────────────────────────────────────────────┤
│  Layer 6: Hook 系统                                         │
│    自建,shell 命令为 hook 协议                            │
│    AsyncHookRegistry 管异步 hook                          │
├─────────────────────────────────────────────────────────────┤
│  Layer 7: 多 Agent 协作                                    │
│    进程内:asyncio.Queue + AsyncLocalStorage              │
│    跨进程:HybridTransport (WS+HTTP)                       │
│    协议:typed messages                                    │
├─────────────────────────────────────────────────────────────┤
│  Layer 8: MCP                                              │
│    既要做 MCP server(暴露能力)                          │
│    也要做 MCP client(消费外部能力)                      │
├─────────────────────────────────────────────────────────────┤
│  Layer 9: 终端 UI(可选)                                  │
│    Ink (Node) / Rich (Python) / Textual (Python)          │
│    异步渲染,不阻塞 agent 主循环                          │
├─────────────────────────────────────────────────────────────┤
│  Layer 10: 观测                                            │
│    OpenTelemetry → Langfuse / Phoenix / Datadog           │
│    结构化事件,不要字符串日志                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 五大维度的"成熟度自检"

判断你的项目当前在哪个 platform 成熟度级别:

| Level | 表现 |
|-------|------|
| **L0 — 单 agent 应用** | 一个 agent、一组工具、一个主循环。没有任何维度的扩展机制。 |
| **L1 — 部分扩展点** | 工具系统抽象了,但 skill 写死、hook 没有、远程不支持。 |
| **L2 — Skill 可插拔** | 加 skill 不用改代码,但 hook、远程、协作仍写死。Nexis 大致在这。 |
| **L3 — Hook 系统** | 用户可在生命周期任意点插入逻辑。但 agent 间协作仍是单一模式。 |
| **L4 — 多 Task 隔离 + 协作** | 支持本地/远程 task,coordinator/teammate 等多种协作模式。 |
| **L5 — 完整 Agent OS** | 五维度全部正交可扩展,多入口,MCP 双向,生产级观测。Claude Code 在这。 |

**实操建议:** 大多数项目 L2 就够了,不需要冲到 L5。L5 是"做 agent 平台卖给别人"才值得投入,自用项目通常 L3 是最佳性价比点。

---

## 反模式速查(平台级常见错误)

| 反模式 | 后果 | 正确做法 |
|--------|------|---------|
| 所有 agent 同进程裸调 | 状态污染、崩溃传染 | Task 多态 + AsyncLocalStorage 隔离 |
| Hook 用 plugin SDK | 用户门槛高,跨语言难 | Hook 是 shell 命令 + JSON 协议 |
| Skill 硬编码列表 | 加 skill 要改代码 | 目录扫描 + frontmatter |
| 工具集对所有 agent 一样 | Plan 模式能写文件,危险 | 按角色 + 模式过滤工具集 |
| 全 WebSocket 通信 | head-of-line blocking | WS 入 + HTTP 出 + 100ms 批量 |
| Token budget 单纯查阈值 | 模型原地打转烧光 token | 加 diminishing returns 检测 |
| Compaction 一刀切 | 丢上下文 / 慢 / cache miss | 三级 compaction(auto/reactive/snip) |
| 状态全塞 Store | 事件触发逻辑变成 setState 链式调用 | Store + Signal 双原语 |
| Task 接口塞所有方法 | 加新 Task 类型痛苦 | 接口只暴露 kill,富特性下沉 |
| 单入口 CLI | 不能做 MCP server / 不能做 worker | 多入口分叉 |

---

## 设计原则速查

| 原则 | 一句话 |
|------|--------|
| **维度正交** | 五个维度独立演进,不互相耦合 |
| **接口贫瘠** | 共同接口只暴露最小公约数,富特性下沉到具体子类 |
| **Schema 真理源** | Zod / Pydantic 一份定义,模型可见 + 校验 + 文档 + IDE 全用 |
| **属性自报** | 工具的 `is_concurrency_safe` 这种"自我描述"由工具自己决定,不让上层猜 |
| **Hook = shell** | 用户扩展点用 shell + JSON,不用 SDK |
| **三层来源** | bundled / user / project,后者覆盖前者 |
| **类型化消息** | agent 间通信必须有 type 字段,区分控制信令和业务内容 |
| **多 stop signal** | 任意一个触发都停,不要单一退出条件 |
| **背压用 block** | 流式系统满了 await,不要丢数据 |
| **多入口** | 同代码支持 CLI / MCP / bridge / daemon 多种部署形态 |

---

## 落地路线图(从 L0 到 L4)

如果你从一个单 agent 应用起步,推荐的演进顺序:

### Phase 1 — 工具系统正规化(L0 → L1,1 周)
- 定义 `Tool` Protocol,Pydantic schema 自动生成 JSON Schema
- 工具自报 `is_read_only` / `is_concurrency_safe`
- 调度器按属性决定并行/串行

### Phase 2 — Skill 系统(L1 → L2,1 周)
- 选定 skill 格式(强烈推荐 Anthropic Skills 标准)
- 实现目录扫描 + frontmatter 解析 + 三层来源合并
- SkillTool:inline 拼 prompt(暂不做 fork)

### Phase 3 — Hook 系统(L2 → L3,1 周)
- 定义 hook 事件枚举
- 实现 shell command spawn + JSON stdio 协议
- 添加 AsyncHookRegistry

### Phase 4 — Task 多态(L3 → L4,2-3 周)
- 抽出 Task Protocol(只 kill)
- 实现 InProcessTask + LocalAgentTask + RemoteAgentTask
- HybridTransport(WS+HTTP+背压)
- typed messages + SendMessage 工具

### Phase 5 — 多入口 + MCP 双向(可选,L4 → L5,2 周)
- 添加 `--mcp-server` 入口
- 添加 `--bridge` 模式
- MCP client 集成

**总计:6-9 周从单 agent 到完整 agent platform。**

---

## 附:与 Application 级框架的关系

`agent-framework-patterns.md` 解决:
- 一个 agent 内部怎么循环推理
- skill 是什么形态
- 输出怎么校验
- controller 怎么决策

**这份文档**解决:
- 多个 agent 怎么共存(维度 1)
- 每个 agent 能干什么(维度 2)
- 知识怎么共享和复用(维度 3)
- 怎么让用户扩展(维度 4)
- agent 之间怎么协作(维度 5)

**两份文档不冲突,而是分层:** 先用 application 范式做出能跑的 agent,再用 platform 范式让它能扩展、隔离、协作。先功能,再框架。
