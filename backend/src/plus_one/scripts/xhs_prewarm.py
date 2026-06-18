"""Pre-collect XHS evidence into the DB-backed ``tool_cache``.

This script is intentionally conservative. It can run public search without
cookie/storage injection, runs one query at a time, sleeps between queries,
stops on public search gates or safety checks, and writes only usable live XHS
results into ``tool_cache``. It does not solve captchas or bypass gates.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import re
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from plus_one.core.tools import _playwright_session
from plus_one.core.tools._cache_db import put_cached
from plus_one.core.tools.xiaohongshu import (
    XHSSearchTool,
    annotate_xhs_posts,
    filter_authentic_xhs_posts,
    xhs_cache_key,
)
from plus_one.scripts.xhs_mvp_seed_data import MVP_XHS_QUERY_ITEMS, MVP_XHS_TARGET_CITIES

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_QUERY_FILE = ROOT / "tmp-xhs-reviewer-queries.json"
DEFAULT_REPORT_FILE = ROOT / "tmp-xhs-prewarm-report.json"
DEFAULT_LOCAL_CACHE_FILE = ROOT / "tmp-xhs-prewarm-cache.jsonl"
DEFAULT_COVERAGE_FILE = ROOT / "tmp-xhs-prewarm-coverage.json"
DEFAULT_PUBLIC_BROWSER_PROFILE_DIR = ROOT / "tmp-xhs-public-browser-profile"
DEFAULT_SEARCH_DIAGNOSTIC_FILE = ROOT / "tmp-xhs-search-state-check.json"
DEFAULT_SEARCH_DIAGNOSTIC_SCREENSHOT = ROOT / "tmp-xhs-search-state-check.png"
DEFAULT_SEARCH_DIAGNOSTIC_QUERY = "东京 AFURI 惠比寿 美食推荐"
XHS_HOME = "https://www.xiaohongshu.com/"
ASCII_MAX_CODEPOINT = 127
MAX_FALLBACK_NAME_CHARS = 48
MAX_QUERY_ATTEMPTS = 4
EMPTY_RETRY_VERSION = 4
RESULT_QUALITY_VERSION = 4
MIN_CANDIDATE_RELEVANCE_SCORE = 0.5
MIN_CJK_RELEVANCE_CHARS = 2
MIN_LATIN_RELEVANCE_WORD_CHARS = 2
MIN_LATIN_JOINED_RELEVANCE_CHARS = 3
STRONG_LATIN_RELEVANCE_WORD_COUNT = 2
MEDIUM_LATIN_RELEVANCE_WORD_CHARS = 4
MIN_REORDERABLE_RELEVANCE_TOKENS = 2
MIN_REORDERABLE_CJK_TOKEN_CHARS = 2
MIN_SPECIFIC_LATIN_BRAND_CHARS = 3
NORMAL_SKIP_REASONS = {
    "no_usable_authentic_posts",
    "no_relevant_authentic_posts",
    "no_content_images",
}
TRANSIENT_SKIP_REASONS = {"public_search_gated"}
FULLWIDTH_LEFT_PAREN = "\uff08"
FULLWIDTH_RIGHT_PAREN = "\uff09"
OPEN_PAREN_RE = f"[{FULLWIDTH_LEFT_PAREN}(]"
CLOSE_PAREN_RE = f"[{FULLWIDTH_RIGHT_PAREN})]"
PAREN_CONTENT_RE = (
    f"{OPEN_PAREN_RE}([^(){FULLWIDTH_LEFT_PAREN}{FULLWIDTH_RIGHT_PAREN}]+){CLOSE_PAREN_RE}"
)
PAREN_BLOCK_RE = (
    f"{OPEN_PAREN_RE}[^(){FULLWIDTH_LEFT_PAREN}{FULLWIDTH_RIGHT_PAREN}]+{CLOSE_PAREN_RE}"
)
PAREN_CHARS_RE = f"[(){FULLWIDTH_LEFT_PAREN}{FULLWIDTH_RIGHT_PAREN}]"
SEGMENT_SPLIT_RE = r"[/\u2014\u2013-]|\bor\b|\+|&|,"
CJK_TEXT_RE = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")
HAN_TEXT_RE = re.compile(r"[\u3400-\u9fff]")
QUERY_INTENTS = (
    "本地人必去景点推荐",
    "本地人推荐",
    "本地人常去",
    "美食推荐",
    "拉面推荐",
    "拉面店推荐",
    "排队拉面",
    "酒吧推荐",
    "居酒屋推荐",
    "饮品推荐",
    "茶室推荐",
    "茶道体验",
    "咖啡推荐",
    "甜品推荐",
    "街头小吃",
    "小众景点",
    "小红书推荐",
    "真实体验",
    "值得吃吗",
    "值得去吗",
    "攻略",
    "避雷",
    "氛围",
)
GAP_DEDUPE_STATUS_RANK = {
    "partial": 0,
    "untouched": 1,
    "no_usable_authentic_posts": 2,
    "error": 3,
}
STALE_PARTIAL_SKIP_THRESHOLD = 4
GENERIC_RELEVANCE_TERMS = {
    "area",
    "bar",
    "beer",
    "cafe",
    "circle",
    "city",
    "coffee",
    "department",
    "food",
    "garden",
    "honten",
    "hotel",
    "house",
    "japan",
    "kyoto",
    "market",
    "moon",
    "museum",
    "park",
    "ramen",
    "restaurant",
    "road",
    "shop",
    "site",
    "soba",
    "station",
    "street",
    "temple",
    "tokyo",
}
GENERIC_CJK_RELEVANCE_TERMS = {
    "餐厅",
    "美食",
    "海鲜",
    "市场",
    "早市",
    "茶室",
    "茶屋",
    "酒吧",
    "居酒屋",
    "烤肉",
    "肉屋",
    "拉面",
    "甜品",
    "早茶",
    "景点",
    "公园",
    "寺庙",
    "商店街",
    "大排档",
    "烤全羊",
}
CJK_NORMALIZATION_TABLE = str.maketrans(
    {
        "廣": "广",
        "東": "东",
        "寶": "宝",
        "華": "华",
        "麵": "面",
        "雲": "云",
        "燒": "烧",
        "點": "点",
        "園": "园",
        "館": "馆",
        "門": "门",
        "臺": "台",
        "灣": "湾",
        "區": "区",
        "舊": "旧",
        "裡": "里",
        "裏": "里",
        "鍋": "锅",
        "壽": "寿",
        "樂": "乐",
    }
)
GENERIC_CJK_COMPACT_RELEVANCE_TERMS = {
    re.sub(r"[\W_]+", "", value.translate(CJK_NORMALIZATION_TABLE), flags=re.UNICODE).casefold()
    for value in GENERIC_CJK_RELEVANCE_TERMS
}
DESTINATION_NAME_ALIASES: dict[str, tuple[str, ...]] = {
    "Delhi, India": ("Delhi",),
    "Guangzhou, China": ("Guangzhou",),
    "Hakone, Japan": ("Hakone",),
    "Shanghai, China": ("Shanghai",),
}
DESTINATION_QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    "Delhi": ("德里", "Delhi"),
    "Delhi, India": ("德里", "Delhi"),
    "Guangzhou": ("广州", "Guangzhou"),
    "Guangzhou, China": ("广州", "Guangzhou"),
    "guangzhou": ("广州", "Guangzhou"),
    "Hakone": ("箱根", "Hakone"),
    "Hakone, Japan": ("箱根", "Hakone"),
    "Kyoto": ("京都", "Kyoto"),
    "kyoto": ("京都", "Kyoto"),
    "Marrakech": ("马拉喀什", "Marrakech", "Marrakesh"),
    "New York": ("纽约", "New York"),
    "Osaka": ("大阪", "Osaka"),
    "Paris": ("巴黎", "Paris"),
    "Sapporo": ("札幌", "Sapporo"),
    "Seoul": ("首尔", "Seoul"),
    "Shanghai": ("上海", "Shanghai"),
    "Shanghai, China": ("上海", "Shanghai"),
    "Singapore": ("新加坡", "Singapore"),
    "Taipei": ("台北", "Taipei"),
    "Bangkok": ("曼谷", "Bangkok"),
    "Hong Kong": ("香港", "Hong Kong"),
    "London": ("伦敦", "London"),
    "Tokyo": ("东京", "Tokyo"),
}
XHS_NAME_ALIASES: dict[str, tuple[str, ...]] = {
    "+61": ("马拉喀什 +61 餐厅", "+61 马拉喀什"),
    "A Da Cong You Bing": ("阿大葱油饼", "阿大"),
    "Afuri": ("阿夫利", "AFURI"),
    "Afuri Ebisu": ("阿夫利 惠比寿", "AFURI 惠比寿", "AFURI 恵比寿"),
    "Afuri Harajuku": ("阿夫利 原宿", "AFURI 原宿"),
    "Aji no Nihachi (味の二幸)": ("味の二幸", "味之二幸", "二幸"),
    "Aji no Nikuya": ("味の肉屋", "味の肉や", "味之肉屋", "Aji no Nikuya 札幌"),
    "Al Bahriya": ("Al Bahriya", "Al Bahriya seafood"),
    "Al Fassia": ("马拉喀什 Al Fassia 摩洛哥菜", "Al Fassia 餐厅"),
    "Amal Women's Training Center": ("Amal", "Amal Women's Training Center"),
    "Amal Women's Training Center restaurant": (
        "Amal",
        "Amal restaurant",
        "Amal Women's Training Center",
    ),
    "Amazake-chaya": ("甘酒茶屋", "箱根 甘酒茶屋"),
    "Bab Doukkala morning market": ("杜卡拉门 早市", "Bab Doukkala 市场"),
    "Bai E Tan (白鹅潭) / Pearl River west bank": ("白鹅潭", "珠江西岸 白鹅潭"),
    "Baihua Tian Xin (百花甜品) / Nanxin Dessert": ("百花甜品", "南信甜品"),
    "Baiyun Mountain (白云山)": ("白云山",),
    "Bao Hua Mian Jia (宝华面家)": ("宝华面家", "宝华面店", "寶華麵家", "寶華麵店"),
    "Bao Hua Mian Shi Jia (宝华面店)": ("宝华面店", "宝华面家", "寶華麵店", "寶華麵家"),
    "Bao Hua Mian Shi Jia (宝华面食家)": ("宝华面食家", "宝华面家", "宝华面店"),
    "Baohua Mianjia (宝华面家)": ("宝华面家", "宝华面店", "寶華麵家", "寶華麵店"),
    "Baohuayuan Sampan Congee (宝华园)": ("宝华园 艇仔粥", "宝华园", "寶華園"),
    "Bar & Izakaya alley 'Norubesa' building + rooftop ferris wheel area": (
        "札幌 Norbesa 大楼 酒吧",
        "札幌 ノルベサ 居酒屋",
    ),
    "Bar Yamazaki": ("山崎酒吧", "Bar Yamazaki 札幌"),
    "Bayun (Baiyun) Mountain — Mingchun Valley side": ("白云山 明春谷", "明春谷"),
    "Beer Inn Mugishutei": ("麦酒停", "Beer Inn 麦酒停"),
    "Beijing Road Pedestrian Street": ("北京路步行街", "广州 北京路"),
    "Bigiya": ("びぎ屋", "Bigiya 拉面"),
    "Bing Sheng Mansion or Yan Yu Tai for morning tea": ("炳胜公馆 早茶", "宴遇 早茶"),
    "Bing Sheng Mansion's rival: Lai Heen / Jiang by Chef Fei": (
        "利苑 早茶",
        "江 by Chef Fei",
        "广州 利苑",
    ),
    "Bingsheng Mansion (炳胜公馆)": ("炳胜公馆",),
    "Bingsheng Pin Dao (炳胜品味)": ("炳胜品味",),
    "Bingsheng Pinwei (炳胜品味)": ("炳胜品味",),
    "Bingsheng Restaurant (炳胜品味)": ("炳胜品味",),
    "Cafe Clock": ("马拉喀什 Cafe Clock", "Cafe Clock 餐厅"),
    "Café Clock": ("马拉喀什 Cafe Clock", "Cafe Clock 餐厅"),
    "Camellia Flower (Camellia En)": ("山茶花茶道", "Camellia 茶道"),
    "Camellia Garden Tea Ceremony": ("山茶花茶道", "Camellia 茶道"),
    "Camellia Tea Ceremony (Flower location)": ("山茶花茶道", "Camellia Flower 茶道"),
    "Camellia Tea Ceremony (Flower)": ("山茶花茶道", "Camellia Flower 茶道"),
    "Camellia Tea Ceremony Flower": ("山茶花茶道", "Camellia Flower 茶道"),
    "Canton Tower & Pearl River night cruise": ("广州塔 珠江夜游", "珠江夜游"),
    "Canton Tower + Pearl River night cruise": ("广州塔 珠江夜游", "珠江夜游"),
    "Chairo Salon Tea Stand": ("箱根 茶室", "Chairo Salon 茶屋"),
    "Champa Gali": ("香帕加利", "德里 Champa Gali"),
    "Chandni Chowk & Paranthe Wali Gali": ("月光集市", "帕兰特瓦利街"),
    "Chandni Chowk / Paranthe Wali Gali": ("月光集市", "帕兰特瓦利街"),
    "Chandni Chowk food walk (Paranthe Wali Gali)": ("月光集市", "帕兰特瓦利街", "月光集市 美食"),
    "Chandni Chowk parathe wali gali": ("月光集市", "帕兰特瓦利街"),
    "Chanoma Tea House at Hakone Open-Air Museum": ("箱根雕刻之森 茶屋", "箱根露天博物馆 茶屋"),
    "Chez Lamine Hadj Mustapha": ("Chez Lamine", "Chez Lamine 烤羊", "马拉喀什 烤全羊"),
    "Chuka Soba Inoue": ("中華そば井上", "筑地 井上 拉面"),
    "Chukasoba Inoue": ("中華そば井上", "筑地 井上 拉面"),
    "Choanji Temple": ("长安寺", "箱根 长安寺"),
    "Columbia Circle (Shanghai Film Studio / Mansion 1933 area, Xinhua Road)": ("上生新所",),
    "Columbia Circle (Shanghai Film Studio site)": ("上生新所",),
    "Craft beer bar Mugishutei (麦酒停)": ("麦酒停", "札幌 麦酒停"),
    "D&Department Kyoto (in Bukkoji temple grounds)": ("佛光寺 D&Department", "D&Department 京都"),
    "D-matcha Kyoto Tea Farm (Wazuka)": ("d matcha 和束", "d:matcha 京都"),
    "D-matcha Kyoto Tea Farm Café (Wazuka day trip)": ("d matcha 和束", "d:matcha 京都"),
    "Daruma Honten": ("达摩 成吉思汗", "成吉思汗だるま", "だるま 本店"),
    "Daruma Honten (Jingisukan Daruma)": ("达摩 成吉思汗", "成吉思汗だるま", "だるま 本店"),
    "Dilli Haat": ("德里手工艺市场", "Dilli Haat INA"),
    "Dilli Haat (INA)": ("德里手工艺市场 INA", "Dilli Haat INA"),
    "Dongshankou (东山口)": ("东山口",),
    "Enning Road & Yongqingfang (永庆坊)": ("恩宁路 永庆坊", "永庆坊"),
    "Enning Road (恩宁路)": ("恩宁路",),
    "Enning Road (恩宁路) & Yongqingfang": ("恩宁路 永庆坊", "恩宁路"),
    "Fukujuen Kyoto Flagship Store": ("福寿园 京都本店", "福寿园 京都"),
    "Fuunji": ("风云儿", "風雲児"),
    "Ginza Hachigou": ("银座 八五", "銀座 八五"),
    "Ginza Kagari": ("银座 篝", "銀座 篝"),
    "Gora Brewery & Grill": ("强罗啤酒", "Gora Brewery 强罗"),
    "Gora Park Hakuun-do Tea House": ("强罗公园 白云洞茶苑", "白云洞茶苑"),
    "Gora Park Hakuun-do Teahouse": ("强罗公园 白云洞茶苑", "白云洞茶苑"),
    "Gōra Brewery & Grill": ("强罗啤酒", "Gora Brewery 强罗"),
    "Hachikyo": ("八协", "はちきょう"),
    "Hakone Checkpoint & Sugi Namiki": ("箱根关所 杉並木", "箱根旧街道 杉並木"),
    "Hakone Checkpoint (Hakone Sekisho) & Onshi-Hakone Park": ("箱根关所 恩赐箱根公园", "箱根关所"),
    "Hakone Kamon": ("箱根花纹", "箱根 花纹"),
    "Hakone Kowakien Yunessun": ("箱根小涌园 Yunessun", "箱根小涌园"),
    "Hakone Kyu-Kaidou cedar avenue & Mototsumiya shrine on Mt. Komagatake": (
        "箱根旧街道 杉並木",
        "箱根驹岳 元宫",
    ),
    "Hakone Maruyama Bussan": ("箱根 丸山物产", "丸山物产"),
    "Hakone Maruyama Bussan tea house at Owakudani": ("大涌谷 丸山物产", "丸山物产 茶屋"),
    "Hakone Museum of Art (Moss Garden)": ("箱根美术馆 苔庭", "箱根美术馆"),
    "Hakone Open-Air Museum": ("箱根雕刻之森美术馆", "箱根露天博物馆"),
    "Hakone Pirate Ship (Hakone Sightseeing Cruise)": ("箱根海贼船", "芦之湖 海贼船"),
    "Hakone Sekisho (checkpoint) and Old Tokaido cedar avenue": (
        "箱根关所 旧东海道杉並木",
        "箱根关所",
    ),
    "Hakone Shrine (Kuzuryu / lakeside torii)": ("箱根神社 九头龙", "芦之湖 鸟居"),
    "Hakone Shrine torii on Lake Ashi": ("箱根神社 鸟居", "芦之湖 鸟居"),
    "Hakone Sightseeing Cruise (pirate ships)": ("箱根海贼船", "芦之湖游船"),
    "Hakone Tea House Issaku": ("箱根 茶屋 一煎", "Issaku 茶屋"),
    "Hakone Yumoto shotengai": ("箱根汤本商店街", "箱根汤本"),
    "Hakone Yuryo": ("箱根汤寮",),
    "Hatajuku Yosegi Zaiku workshops": ("畑宿 寄木细工", "箱根寄木细工"),
    "Hatajuku yosegi-zaiku workshops": ("畑宿 寄木细工", "箱根寄木细工"),
    "Hatsuhana Soba Honten": ("初花荞麦 本店", "はつ花そば"),
    "Hauz Khas Village": ("豪兹卡斯村", "Hauz Khas 德里"),
    "Henna Cafe": ("Henna Cafe 马拉喀什", "汉娜咖啡馆"),
    "Hitsujitei": ("羊亭", "ひつじ亭"),
    "Hokkaido Shokusai Hiroba Sapporo": ("北海道食彩广场 札幌", "北海道食彩広場"),
    "Homemade Ramen Muginae": ("麦苗", "Homemade Ramen 麦苗"),
    "Houraidou Chaho": ("蓬莱堂茶铺", "Houraidou 茶铺"),
    "Huangpu Ancient Village (黄埔古港)": ("黄埔古港", "黄埔古村"),
    "Huangsha Aquatic Market & nearby seafood restaurants": (
        "黄沙水产市场 海鲜",
        "黄沙 海鲜大排档",
    ),
    "Huangsha Aquatic Market & surrounding seafood dai pai dongs": (
        "黄沙水产市场 大排档",
        "黄沙 海鲜",
    ),
    "Huangsha Seafood Market (黄沙水产市场)": ("黄沙水产市场", "黄沙海鲜市场"),
    "Humayun's Tomb": ("胡马雍陵", "德里 胡马雍墓"),
    "Hyosetsu no Mon": ("冰雪之门", "氷雪の門"),
    "Hyousetsu no Mon": ("冰雪之门", "氷雪の門"),
    "Ichiran": ("一兰拉面", "一蘭"),
    "Ichiran Shibuya": ("一兰拉面 涩谷", "一蘭 渋谷"),
    "Indian Accent": ("德里 Indian Accent", "Indian Accent 餐厅"),
    "Ippodo Tea Honten": ("一保堂茶铺 本店", "一保堂 京都"),
    "Ippodo Tea Kyoto Honten": ("一保堂茶铺 京都本店", "一保堂 京都"),
    "Ippodo Tea Main Store": ("一保堂茶铺 本店", "一保堂 京都"),
    "Ippudo Nishi-Azabu Honten": ("一风堂 西麻布本店", "一風堂 西麻布"),
    "Ippuku-do (一福堂) / Ippuku Chaya at Ninenzaka": ("一福堂", "二年坂 一福堂"),
    "Ippukudo": ("一福堂", "二年坂 一福堂"),
    "Ippukudo (一福堂)": ("一福堂", "二年坂 一福堂"),
    "Jemaa el-Fnaa food stalls (evening)": ("杰马夫纳广场 夜市", "马拉喀什 不眠广场 美食"),
    "Jemaa el-Fnaa night food stalls": ("杰马夫纳广场 夜市", "马拉喀什 不眠广场 美食"),
    "Kagari": ("篝", "银座 篝"),
    "Kaikado Cafe": ("开化堂咖啡", "Kaikado Cafe 京都"),
    "Karim's": ("卡里姆餐厅", "Karim's 德里"),
    "Khan Chacha & Khan Market": ("Khan Chacha", "汗市场", "可汗市场"),
    "Khan Market": ("汗市场", "可汗市场", "Khan Market 德里"),
    "Ki-Ya Kyoto (喫茶 樹や)": ("喫茶 樹や", "京都 樹や"),
    "Kikanbo": ("鬼金棒", "カラシビ味噌らー麺鬼金棒"),
    "Kissa Kaboku": ("喫茶 嘉木", "一保堂 嘉木"),
    "Kissa Kaboku side street alternatives: Ocha no Kanbayashi (上林春松本店)": (
        "上林春松本店",
        "喫茶 嘉木",
    ),
    "Kiyomizu": ("清水寺", "清水坂"),
    "Konjiki Hototogisu": ("金色不如归", "金色不如帰"),
    "Kyoto Obubu Tea Farms tasting room": ("京都 Obubu 茶园", "和束 茶园"),
    "Lanxin Canting (Lan Xin Restaurant)": ("兰心餐厅", "上海 兰心餐厅"),
    "Lao Ji Shi (Jesse Restaurant)": ("老吉士", "吉士酒家"),
    "Lao Ji Shi (Jesse Restaurant) original Tianping Road location": (
        "老吉士 天平路",
        "吉士酒家 天平路",
    ),
    "Liede Village (猎德村)": ("猎德村",),
    "Liwan Lake Park & Xiguan ancestral houses": ("荔湾湖公园 西关大屋", "荔湾湖公园"),
    "Liwan Lake Park morning crowd": ("荔湾湖公园 早茶", "荔湾湖公园 本地人"),
    "Liwan Mingshijia (荔湾名食家)": ("荔湾名食家",),
    "Lodhi Art District": ("洛迪艺术区", "Lodhi Art District 德里"),
    "Lujiazui SWFC observation deck": (
        "陆家嘴 环球金融中心 观光厅",
        "上海环球金融中心 观光厅",
        "上海环球金融中心",
        "环球金融中心100层",
    ),
    "M50 Creative Park": ("M50创意园", "上海 M50"),
    "Majnu Ka Tila": ("德里藏人区", "Majnu ka Tilla"),
    "Majnu ka Tilla": ("德里藏人区", "Majnu ka Tilla"),
    "Majnu-ka-Tilla": ("德里藏人区", "Majnu ka Tilla"),
    "Marché Central de Guéliz (Marché Municipal)": ("盖利兹中央市场", "马拉喀什 中央市场"),
    "Marukyu Koyamaen Nishinotoin Salon": ("丸久小山园 西洞院 茶房", "丸久小山园 京都"),
    "Marukyu Koyamaen Nishinotoin Saryo": ("丸久小山园 西洞院 茶寮", "丸久小山园 京都"),
    "Marukyu Koyamaen Nishinotoin Tea House": ("丸久小山园 西洞院 茶房", "丸久小山园 京都"),
    "Marukyu Koyamaen Nishinotoin Tearoom": ("丸久小山园 西洞院 茶房", "丸久小山园 京都"),
    "Mechoui Alley": ("马拉喀什 烤羊街",),
    "Mehrauli Archaeological Park": ("梅赫劳利考古公园", "德里 Mehrauli 考古公园"),
    "Mellah spice market (Place des Ferblantiers area)": ("Mellah 香料市场", "马拉喀什 香料市场"),
    "Menya Itto": ("麺屋一燈", "面屋一灯"),
    "Menya Musashi": ("麺屋武蔵", "面屋武藏"),
    "Menya Musashi Kosho": ("麺屋武蔵 虎嘯", "面屋武藏 虎啸"),
    "Menya Shono": ("麺や庄の", "面屋庄野"),
    "Mercado Mellah (Marché des Épices)": (
        "Mellah 香料市场",
        "Mellah spice market",
        "Marché des Épices",
        "马拉喀什 香料市场",
    ),
    "Mercado Plaza / Marché Central de Gueliz": ("盖利兹中央市场", "马拉喀什 中央市场"),
    "Moon-Light (Tsukiakari)": ("ムーンライト", "月光 札幌"),
    "Moon-Light (ムーンライト) / Susukino Ramen Yokocho fringe izakayas": (
        "ムーンライト",
        "薄野 拉面横丁 居酒屋",
    ),
    "Mouko Tanmen Nakamoto": ("蒙古タンメン中本", "蒙古汤面中本"),
    "Mugishutei (Beer Inn Mugishutei)": ("麦酒停", "Beer Inn 麦酒停"),
    "Mustapha's snail cart on Rue Riad Zitoun el-Kedim": ("穆斯塔法 蜗牛摊", "马拉喀什 蜗牛"),
    "Nakiryu": ("鸣龙", "鳴龍", "鸣龙 拉面", "鳴龍 拉面"),
    "Namara Ezo": ("なまら蝦夷", "Namara Ezo 札幌"),
    "Nanporo": ("なんぽろ", "札幌 南幌"),
    "Nanporo (なんぽろ)": ("なんぽろ", "札幌 南幌"),
    "Nanporo (なんぽろ) / Otaru-style izakaya alleys around Tanukikoji 4-5": (
        "なんぽろ",
        "狸小路 居酒屋",
    ),
    "Naraya Cafe": ("奈良屋咖啡", "NARAYA CAFE 箱根"),
    "Nijo Market izakaya counters (e.g., Magokoro)": ("二条市场 居酒屋", "二条市场 まごころ"),
    "Nijo Market izakaya stalls": ("二条市场 居酒屋", "札幌 二条市场"),
    "Nizamuddin Dargah (Thursday qawwali)": ("尼扎姆丁圣陵 卡瓦力", "Nizamuddin Dargah"),
    "Nizamuddin Dargah Qawwali (Thursday evenings)": ("尼扎姆丁圣陵 卡瓦力", "Nizamuddin Dargah"),
    "Nizamuddin Dargah qawwali night": ("尼扎姆丁圣陵 卡瓦力", "Nizamuddin Dargah"),
    "North Island Beer Taproom (Soft Tail Brewing area)": (
        "北岛啤酒 札幌",
        "North Island Beer 札幌",
    ),
    "Otaru Soko No.1 (Otaru Warehouse No.1)": ("小樽仓库No.1", "小樽仓库一号"),
    "Otoboke (おとぼけ)": ("おとぼけ", "札幌 おとぼけ"),
    "Owakudani black eggs": ("大涌谷 黑鸡蛋", "大涌谷 黑玉子"),
    "Pola Museum of Art": ("POLA美术馆", "箱根 POLA美术馆"),
    "Qibao Ancient Town": ("七宝古镇", "上海 七宝"),
    "Ramen Break Beats": ("Ramen Break Beats", "拉面 Break Beats"),
    "Ramen Jiro": ("ラーメン二郎", "拉面二郎"),
    "Ramen Jiro (Mita honten)": ("ラーメン二郎 三田本店", "拉面二郎 三田本店"),
    "Ramen Jiro Mita Honten": ("ラーメン二郎 三田本店", "拉面二郎 三田本店"),
    "Ramen Nagi": ("凪拉面", "ラーメン凪"),
    "Ramen Nagi Golden Gai": ("凪拉面 黄金街", "ラーメン凪 ゴールデン街"),
    "Ramen Nagi Niboshi": ("凪拉面 煮干", "すごい煮干ラーメン凪"),
    "Ramen Yamaguchi": ("拉面山口", "らぁ麺やまぐち"),
    "Ramen Yokocho alley izakaya side streets": ("拉面横丁 居酒屋", "薄野 拉面横丁"),
    "Ramen Yokocho izakaya alleys (Gansō vs. Shin)": ("元祖拉面横丁 新拉面横丁", "薄野 拉面横丁"),
    "Redtory / Yuexiu Park morning culture": ("红砖厂 越秀公园", "越秀公园 早晨"),
    "Redtory / Zhujiang-Party Pier (珠江琶醍)": ("珠江琶醍", "红砖厂"),
    "Rokurinsha": ("六厘舎", "六厘舍"),
    "Ryokucha-kan Fukujuen Kyoto Honten": ("福寿园 京都本店", "绿茶馆 福寿园"),
    "Ryukoen": ("柳桜園茶舗", "柳樱园茶铺"),
    "Ryukoen (柳桜園茶舗)": ("柳桜園茶舗", "柳樱园茶铺"),
    "Ryurikoen (柳桜園茶舗)": ("柳桜園茶舗", "柳樱园茶铺"),
    "Ryurindo": ("柳苑堂", "Ryurindo 京都"),
    "Salon de The François adjacent — Ogawa Coffee + tea side": ("弗朗索瓦咖啡馆", "小川咖啡 京都"),
    "Salon de The Maeda Coffee Myokenji-mae": ("前田咖啡 妙显寺", "Maeda Coffee 京都"),
    "Salon de The Maeda-en": ("前田园", "Maeda-en 京都"),
    "Salon de The Maeda-en / Kyoto Obubu Tea Farms tasting": ("前田园", "京都 Obubu 茶园"),
    "Salon de Thé MAEDA-EN / Maeda Coffee tea menu": ("前田园", "前田咖啡 茶"),
    "Sapporo Beer Garden (Kaitakushi Hall)": ("札幌啤酒园 开拓使馆", "札幌啤酒园 成吉思汗"),
    "Sapporo Beer Garden (Kaitakushikan / Genghis Khan Hall)": (
        "札幌啤酒园 开拓使馆",
        "札幌啤酒园 成吉思汗",
    ),
    "Sapporo Beer Museum tasting room": ("札幌啤酒博物馆 试饮", "札幌啤酒博物馆"),
    "Sapporo Kaitaku Shiyakusho-mae yokocho / Namara Ezo": ("開拓使役所前横丁", "なまら蝦夷"),
    "Shaheng Fen (沙河粉村)": ("沙河粉村", "沙河粉"),
    "Shamian Island": ("沙面岛", "沙面"),
    "Shamian Island (沙面)": ("沙面", "沙面岛"),
    "Shamian Island (沙面岛)": ("沙面岛", "沙面"),
    "Shimogamo Shrine + Saryo Hosen morning combo": ("下鸭神社 宝泉", "茶寮宝泉"),
    "Sidi Ghanem industrial district food spots": ("西迪加奈姆 工业区 餐厅", "Sidi Ghanem 餐厅"),
    "Soranoiro Nippon": ("ソラノイロ NIPPON", "空之色拉面"),
    "Souk Bab Doukkala / Mellah market (Place des Ferblantiers area)": (
        "杜卡拉门 市集",
        "Mellah 市场",
    ),
    "Souk Semmarine & Souk el Attarine": ("Semmarine 市集", "马拉喀什 香料市集"),
    "Souk Semmarine and Souk el-Attarine": ("Semmarine 市集", "马拉喀什 香料市集"),
    "Sundar Nursery": ("桑达尔苗圃", "Sunder Nursery 德里"),
    "Sunder Nursery": ("桑达尔苗圃", "Sunder Nursery 德里"),
    "Tanuki Koji shotengai izakaya alleys": ("狸小路商店街 居酒屋", "狸小路"),
    "Tao Heung Lou (陶陶居)": ("陶陶居",),
    "Tao Tao Ju (陶陶居)": ("陶陶居",),
    "Tenzan Tohji-kyo": ("天山汤治乡", "箱根 天山"),
    "The Bund (Waitan) waterfront promenade": ("外滩", "上海 外滩"),
    "Tianzifang": ("田子坊", "上海 田子坊"),
    "Tomita": ("とみ田", "富田拉面"),
    "Tsujiri Honten": ("辻利总本店", "祇园辻利"),
    "Tsujita": ("つじ田", "辻田拉面"),
    "Tsuki-no-Yu (Setsugetsuka area)": ("月之汤", "雪月花 月之汤"),
    "Tsuta": ("蔦拉面", "Japanese Soba Noodles 蔦"),
    "Uji Tsuen Kyoto-ten": ("通圆 京都店", "宇治通圆"),
    "Ujien Kissako-an": ("宇治园 喫茶去庵", "宇治园 京都"),
    "Wenming Lu congee & late-night street food strip": ("文明路 粥", "文明路 宵夜"),
    "Wukang Mansion area": ("武康大楼", "武康路"),
    "Wukang Road & Wukang Mansion": ("武康路 武康大楼", "武康大楼"),
    "Xintiandi": ("新天地", "上海 新天地"),
    "Yakitori Toriya": ("焼鳥 鳥や", "札幌 烤鸟"),
    "Yan Yan (沿沿) / Huifu East Road food street": ("沿沿", "惠福东路 美食街"),
    "Yide Lu dried seafood & Qingping Market": ("一德路 干货", "清平市场"),
    "Yide Road (一德路) dried seafood & wholesale markets": ("一德路 干货批发", "一德路"),
    "Yide Road dried goods market (一德路)": ("一德路 干货市场", "一德路"),
    "Yong Qi Beef Offal (永记牛杂)": ("永记牛杂",),
    "Yong Qing Fang (永庆坊)": ("永庆坊",),
    "Yongkang Lu": ("永康路 酒吧", "上海 永康路"),
    "Yongkang Road": ("永康路 酒吧", "上海 永康路"),
    "Yongqingfang (永庆坊)": ("永庆坊",),
    "Yu Garden Bazaar": ("豫园 城隍庙", "豫园商城"),
    "Yuexiu Park & Five Rams Statue": ("越秀公园 五羊雕像", "五羊石像"),
    "Yuexiu Park & Five Rams Statue (越秀公园)": ("越秀公园 五羊雕像", "五羊石像"),
    "Yuexiu Park & Zhenhai Tower": ("越秀公园 镇海楼", "镇海楼"),
    "Yuexiu Park & Zhenhai Tower (越秀公园 / 镇海楼)": ("越秀公园 镇海楼", "镇海楼"),
    "Zenkashoin (然花抄院)": ("然花抄院",),
}
XHS_CONTEXTUAL_NAME_ALIASES: dict[str, tuple[str, ...]] = {
    # Query-only expansions for short or ambiguous CJK names. These keep the
    # actual candidate alias in the query while adding the local scene words a
    # XHS user is likely to type.
    "Ippuku-do (一福堂) / Ippuku Chaya at Ninenzaka": (
        "二年坂 一福堂 抹茶",
        "清水寺 一福堂 茶屋",
        "一福茶屋",
        "二年坂 一福茶屋",
        "一福堂 抹茶",
        "一福堂 茶屋",
    ),
    "Ippukudo": (
        "二年坂 一福堂 抹茶",
        "清水寺 一福堂 茶屋",
        "一福茶屋",
        "二年坂 一福茶屋",
        "一福堂 抹茶",
        "一福堂 茶屋",
    ),
    "Ippukudo (一福堂)": (
        "二年坂 一福堂 抹茶",
        "清水寺 一福堂 茶屋",
        "一福茶屋",
        "二年坂 一福茶屋",
        "一福堂 抹茶",
        "一福堂 茶屋",
    ),
    "Ki-Ya Kyoto (喫茶 樹や)": (
        "喫茶 樹や 京都",
        "京都 樹や 咖啡",
        "京都 樹や 喫茶",
        "樹や 京都 咖啡",
    ),
    "Kissa Kaboku": (
        "一保堂 嘉木 喫茶",
        "一保堂茶铺 嘉木",
        "嘉木 京都 抹茶",
        "喫茶 嘉木 抹茶",
    ),
    "Kissa Kaboku side street alternatives: Ocha no Kanbayashi (上林春松本店)": (
        "上林春松本店 抹茶",
        "上林春松本店 茶铺",
        "上林 京都 抹茶",
        "一保堂 嘉木 喫茶",
    ),
    "Ujien Kissako-an": (
        "宇治园 喫茶去庵 抹茶",
        "宇治园 京都 抹茶",
        "宇治园 清水坂",
        "喫茶去庵 京都",
    ),
}
GATE_MARKERS = (
    "public search gate",
    "public search gated",
    # Historical wording from old reports/tests; current strategy calls this a public search gate.
    "login wall",
    "security gate active",
    "account security restriction",
    "登录后查看搜索结果",
    "扫码",
    "安全验证",
    "安全限制",
    "当前账号存在异常",
    "切换账号后重试",
    "请求太频繁",
    "稍后再试",
    "verification required",
    "verify",
    "captcha",
    "website-login/error",
    "error_code=300011",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prewarm XHS query data into tool_cache")
    sub = parser.add_subparsers(dest="command", required=True)

    add_browser_parser(sub)
    add_diagnose_parser(sub)
    add_run_parser(sub)
    add_seed_mvp_parser(sub)
    add_import_parsers(sub)
    add_coverage_parser(sub)
    add_sanitize_parser(sub)
    return parser


def main() -> None:
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    args = build_parser().parse_args()
    if args.command == "open-browser":
        asyncio.run(open_search_browser(args.profile_dir, args.query, args.timeout_s))
    elif args.command == "diagnose-search":
        asyncio.run(diagnose_search(args))
    elif args.command == "seed-mvp":
        seed_mvp_query_file(args)
    elif args.command == "import-local":
        asyncio.run(import_local_cache(args.local_cache_file))
    elif args.command == "import-evidence":
        asyncio.run(import_xhs_evidence(args.local_cache_file))
    elif args.command == "coverage":
        write_coverage_report(args)
    elif args.command in {"sanitize-public-gate", "sanitize-security-gate"}:
        sanitize_public_gate_report(args)
    else:
        asyncio.run(run_prewarm(args))


def add_browser_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    browser = sub.add_parser("open-browser", help="Open a headed public XHS search browser")
    browser.add_argument(
        "--profile-dir", default=None, help="Persistent public browser profile directory"
    )
    browser.add_argument("--query", default=DEFAULT_SEARCH_DIAGNOSTIC_QUERY)
    browser.add_argument("--timeout-s", type=float, default=900.0)


def add_diagnose_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    diagnose = sub.add_parser(
        "diagnose-search", help="Check whether the XHS public search page can return results"
    )
    diagnose.add_argument(
        "--profile-dir", default=None, help="Persistent public browser profile directory"
    )
    diagnose.add_argument("--query", default=DEFAULT_SEARCH_DIAGNOSTIC_QUERY)
    diagnose.add_argument("--timeout-s", type=float, default=15.0)
    diagnose.add_argument("--report-file", type=Path, default=DEFAULT_SEARCH_DIAGNOSTIC_FILE)
    diagnose.add_argument(
        "--screenshot-file", type=Path, default=DEFAULT_SEARCH_DIAGNOSTIC_SCREENSHOT
    )
    diagnose.add_argument("--headed", action="store_true")


def add_run_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    run = sub.add_parser("run", help="Run conservative live XHS prewarm")
    run.add_argument("--query-file", type=Path, default=DEFAULT_QUERY_FILE)
    run.add_argument("--report-file", type=Path, default=DEFAULT_REPORT_FILE)
    run.add_argument("--local-cache-file", type=Path, default=DEFAULT_LOCAL_CACHE_FILE)
    run.add_argument("--limit-candidates", type=int, default=10)
    run.add_argument("--queries-per-candidate", type=int, default=2)
    run.add_argument("--post-limit", type=int, default=8)
    run.add_argument("--images-per-post", type=int, default=3)
    run.add_argument("--timeout-s", type=float, default=12.0)
    run.add_argument("--call-timeout-s", type=float, default=25.0)
    run.add_argument("--max-query-attempts", type=int, default=MAX_QUERY_ATTEMPTS)
    run.add_argument("--min-sleep-s", type=float, default=18.0)
    run.add_argument("--max-sleep-s", type=float, default=45.0)
    run.add_argument("--max-consecutive-failures", type=int, default=3)
    run.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip the optional XHS search preflight.",
    )
    run.add_argument(
        "--allow-text-only",
        action="store_true",
        help="Cache live notes without content images. Default requires at least one image URL.",
    )
    run.add_argument(
        "--public-search",
        action="store_true",
        help="Use the public search page without cookie/storage injection. This is the default.",
    )
    run.add_argument(
        "--use-configured-session",
        action="store_true",
        help="Opt in to legacy profile/storage/cookie reuse for local diagnostics.",
    )
    run.add_argument(
        "--public-profile-dir",
        default=None,
        help="Optional persistent browser profile for public search; cookies/storage config stays ignored.",
    )
    run.add_argument(
        "--public-index-only",
        action="store_true",
        help="Skip the XHS public search page and use public index/detail discovery only.",
    )
    run.add_argument("--resume", action="store_true")
    run.add_argument("--dry-run", action="store_true")


def add_seed_mvp_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    seed_mvp = sub.add_parser(
        "seed-mvp",
        help="Merge Chinese-first MVP city seed candidates into an XHS query file",
    )
    seed_mvp.add_argument("--input-file", type=Path, default=DEFAULT_QUERY_FILE)
    seed_mvp.add_argument("--output-file", type=Path, default=DEFAULT_QUERY_FILE)


def add_import_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    import_local = sub.add_parser(
        "import-local",
        help="Import a local prewarm jsonl file into the configured Postgres tool_cache",
    )
    import_local.add_argument("--local-cache-file", type=Path, default=DEFAULT_LOCAL_CACHE_FILE)

    import_evidence = sub.add_parser(
        "import-evidence",
        help="Import local XHS jsonl facts into structured Postgres evidence tables",
    )
    import_evidence.add_argument("--local-cache-file", type=Path, default=DEFAULT_LOCAL_CACHE_FILE)


def add_coverage_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    coverage = sub.add_parser(
        "coverage",
        help="Summarise candidate-level XHS prewarm coverage and optionally write a gap query file",
    )
    coverage.add_argument("--query-file", type=Path, default=DEFAULT_QUERY_FILE)
    coverage.add_argument("--report-file", type=Path, default=DEFAULT_REPORT_FILE)
    coverage.add_argument(
        "--extra-report-file",
        type=Path,
        action="append",
        default=[],
        help="Additional prewarm report file to include in coverage stats. Can be repeated.",
    )
    coverage.add_argument("--local-cache-file", type=Path, default=DEFAULT_LOCAL_CACHE_FILE)
    coverage.add_argument("--output-file", type=Path, default=DEFAULT_COVERAGE_FILE)
    coverage.add_argument("--gap-query-file", type=Path, default=None)
    coverage.add_argument("--min-posts-per-candidate", type=int, default=2)


def add_sanitize_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    sanitize = sub.add_parser(
        "sanitize-public-gate",
        help="Mark report rows written during a confirmed XHS public search gate as retryable errors",
    )
    add_sanitize_args(sanitize)

    legacy = sub.add_parser("sanitize-security-gate", help=argparse.SUPPRESS)
    add_sanitize_args(legacy)


def add_sanitize_args(sanitize: argparse.ArgumentParser) -> None:
    sanitize.add_argument("--report-file", type=Path, default=DEFAULT_REPORT_FILE)
    sanitize.add_argument("--diagnostic-file", type=Path, default=DEFAULT_SEARCH_DIAGNOSTIC_FILE)
    sanitize.add_argument(
        "--output-file",
        type=Path,
        default=None,
        help="Destination report file. Defaults to updating --report-file in place.",
    )


async def open_search_browser(profile_dir: str | None, query: str, timeout_s: float) -> None:
    """Open the public XHS search page visibly with a reusable browser profile."""
    from playwright.async_api import async_playwright  # noqa: PLC0415

    resolved_profile = resolve_public_profile_dir(profile_dir)
    resolved_profile.mkdir(parents=True, exist_ok=True)
    query_url = "https://www.xiaohongshu.com/search_result?" + urlencode(
        {"keyword": query, "source": "web_search_result_notes"}
    )
    device_profile = _playwright_session._device_profile_for_fetch(str(resolved_profile))
    user_agent = _playwright_session.pick_user_agent(
        os.getenv("XHS_USER_AGENT"),
        device_profile=device_profile,
    )
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            resolved_profile,
            headless=False,
            **_playwright_session._context_kwargs(
                user_agent=user_agent,
                storage_state_path=None,
                device_profile=device_profile,
            ),
        )
        page = await context.new_page()
        await page.goto(query_url, wait_until="domcontentloaded", timeout=30_000)
        print(
            json.dumps(
                {
                    "status": "xhs_browser_open",
                    "profile_dir": str(resolved_profile),
                    "query": query,
                    "url": query_url,
                    "message": "Inspect the public search page, then close the browser window.",
                },
                ensure_ascii=False,
            )
        )
        with contextlib.suppress(Exception):
            await page.wait_for_event("close", timeout=timeout_s * 1000)
        await context.close()


async def diagnose_search(args: argparse.Namespace) -> None:
    report = await build_search_diagnostic(
        profile_dir=args.profile_dir,
        query=args.query,
        timeout_s=args.timeout_s,
        screenshot_file=args.screenshot_file,
        headed=args.headed,
    )
    write_report(args.report_file, report)
    print(json.dumps(report, ensure_ascii=False))


async def build_search_diagnostic(
    *,
    profile_dir: str | None,
    query: str,
    timeout_s: float,
    screenshot_file: Path,
    headed: bool,
) -> dict[str, Any]:
    started_at = now_iso()
    resolved_profile = resolve_public_profile_dir(profile_dir)
    resolved_screenshot = await asyncio.to_thread(screenshot_file.resolve)
    query_url = "https://www.xiaohongshu.com/search_result?" + urlencode(
        {"keyword": query, "source": "web_search_result_notes"}
    )
    report: dict[str, Any] = {
        "started_at": started_at,
        "query": query,
        "query_url": query_url,
        "entry": "home_search",
        "screenshot": str(resolved_screenshot),
        "checks": [],
    }
    check: dict[str, Any] = {
        "profile_dir": str(resolved_profile),
        "exists": resolved_profile.exists(),
        "started_at": started_at,
    }
    resolved_profile.mkdir(parents=True, exist_ok=True)
    check["exists"] = True

    device_profile = _playwright_session._device_profile_for_fetch(str(resolved_profile))
    user_agent = _playwright_session.pick_user_agent(
        os.getenv("XHS_USER_AGENT"),
        device_profile=device_profile,
    )
    context = None
    page = None
    try:
        async with _open_public_diagnostic_context(
            resolved_profile=resolved_profile,
            headed=headed,
            user_agent=user_agent,
            device_profile=device_profile,
        ) as context:
            page = await context.new_page()
            page.set_default_timeout(int(timeout_s * 1000))
            page.set_default_navigation_timeout(int(timeout_s * 1000))
            status = 0
            navigation_error: Exception | None = None
            try:
                status = await _playwright_session._goto_xhs_search(
                    page,
                    query,
                    timeout_s=timeout_s,
                    profile_dir=str(resolved_profile),
                )
            except Exception as exc:
                navigation_error = exc
            with contextlib.suppress(Exception):
                await page.wait_for_timeout(min(max(int(timeout_s * 250), 1000), 4000))
            title = ""
            body_text = ""
            with contextlib.suppress(Exception):
                title = await page.title()
            with contextlib.suppress(Exception):
                body_text = await _playwright_session._page_body_text(page)
            screenshot_file.parent.mkdir(parents=True, exist_ok=True)
            with contextlib.suppress(Exception):
                await page.screenshot(path=screenshot_file, full_page=True)
            selector_counts = await xhs_selector_counts(page)
            cookies = await context.cookies("https://www.xiaohongshu.com/")
            check.update(
                {
                    "ok": navigation_error is None,
                    "http_status": status,
                    "title": title,
                    "url": page.url,
                    "body_excerpt": body_text[:500],
                    "body_length": len(body_text),
                    "selector_counts": selector_counts,
                    "cookie_count": len(cookies),
                    "cookie_names": sorted(str(cookie.get("name") or "") for cookie in cookies),
                }
            )
            check.update(classify_search_diagnostic(check, body_text))
            if navigation_error is not None:
                check.update(
                    {
                        "error_type": type(navigation_error).__name__,
                        "error": str(navigation_error)[:500],
                    }
                )
    except Exception as exc:
        check.update(
            {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
                "classification": "diagnostic_error",
            }
        )
    finally:
        if page is not None:
            with contextlib.suppress(Exception):
                await page.close()
    check["finished_at"] = now_iso()
    report["checks"].append(check)
    report["finished_at"] = now_iso()
    return report


@contextlib.asynccontextmanager
async def _open_public_diagnostic_context(
    *,
    resolved_profile: Path,
    headed: bool,
    user_agent: str,
    device_profile: str,
) -> Any:
    from playwright.async_api import async_playwright  # noqa: PLC0415

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            resolved_profile,
            headless=not headed,
            **_playwright_session._context_kwargs(
                user_agent=user_agent,
                storage_state_path=None,
                device_profile=device_profile,
            ),
        )
        try:
            yield context
        finally:
            with contextlib.suppress(Exception):
                await context.close()


async def xhs_selector_counts(page: Any) -> dict[str, int]:
    selectors = (
        'a[href*="/search_result/"]',
        'a[href*="/explore/"]',
        "section.note-item",
        "section[data-index]",
    )
    counts: dict[str, int] = {}
    for selector in selectors:
        try:
            counts[selector] = await page.locator(selector).count()
        except Exception:
            counts[selector] = 0
    return counts


def classify_search_diagnostic(check: dict[str, Any], body_text: str) -> dict[str, Any]:
    cookie_names = set(check.get("cookie_names") or [])
    selector_counts = check.get("selector_counts") or {}
    page_url = str(check.get("url") or "")
    parsed_url = urlparse(page_url)
    has_web_session_cookie = "web_session" in cookie_names
    has_id_token_cookie = "id_token" in cookie_names
    has_public_search_gate = "登录后查看搜索结果" in body_text
    has_login_ui = "登录" in body_text or "扫码" in body_text
    has_verify = (
        "/website-login/error" in parsed_url.path
        or "/website-login/captcha" in parsed_url.path
        or "/captcha" in parsed_url.path
        or any(
            marker in body_text
            for marker in ("安全验证", "安全限制", "请求太频繁", "稍后再试", "当前账号存在异常")
        )
    )
    has_results = any(int(count or 0) > 0 for count in selector_counts.values())
    if has_public_search_gate:
        classification = "public_search_gated"
    elif has_verify:
        classification = "security_verification"
    elif has_results:
        classification = "usable"
    elif has_web_session_cookie or has_id_token_cookie:
        classification = "session_cookies_no_results"
    elif has_login_ui:
        classification = "public_entry_prompt"
    else:
        classification = "unknown"
    return {
        "has_web_session_cookie": has_web_session_cookie,
        "has_id_token_cookie": has_id_token_cookie,
        "has_public_search_gate": has_public_search_gate,
        "has_login_ui": has_login_ui,
        "has_verify": has_verify,
        "has_results": has_results,
        "classification": classification,
    }


async def run_prewarm(args: argparse.Namespace) -> None:
    items = load_query_items(args.query_file)
    report = load_report(args.report_file) if args.resume else empty_report(args)
    report.pop("stopped_reason", None)
    done = resume_done_queries(report)
    work = prewarm_work_items(
        items, args.limit_candidates, args.queries_per_candidate, done if args.resume else set()
    )
    failures = 0

    print(
        json.dumps(
            {
                "status": "xhs_prewarm_start",
                "queries": len(work),
                "dry_run": args.dry_run,
                "query_file": str(args.query_file),
                "report_file": str(args.report_file),
                "local_cache_file": str(args.local_cache_file),
            },
            ensure_ascii=False,
        )
    )

    if not args.dry_run and not args.skip_preflight and work:
        preflight = await preflight_xhs_search_gate(args)
        report["preflight"] = preflight
        report["updated_at"] = now_iso()
        write_report(args.report_file, report)
        if not preflight["ok"]:
            print(json.dumps({"status": "xhs_preflight_warning", **preflight}, ensure_ascii=False))

    for index, row in enumerate(work, start=1):
        query = row["query"]
        if args.dry_run:
            print(json.dumps({"index": index, "query": query}, ensure_ascii=False))
            continue

        result = await fetch_one(query, row["candidate"], args)
        report["results"].append(result)
        report["updated_at"] = now_iso()
        write_report(args.report_file, report)
        print(
            json.dumps(
                {
                    "index": index,
                    "candidate": row["candidate"],
                    "query": query,
                    "ok": result["ok"],
                    "usable_count": result.get("usable_count", 0),
                    "image_count": result.get("image_count", 0),
                    "skip_reason": result.get("skip_reason"),
                    "error_type": result.get("error_type"),
                    "error": result.get("error"),
                },
                ensure_ascii=False,
            )
        )

        if result["ok"]:
            failures = 0
        else:
            if (
                result.get("skip_reason") in NORMAL_SKIP_REASONS
                or result.get("skip_reason") in TRANSIENT_SKIP_REASONS
            ):
                failures = 0
                await polite_sleep(args.min_sleep_s, args.max_sleep_s)
                continue
            failures += 1
            if is_gate_error(result.get("error", "")):
                failures = 0
                await polite_sleep(args.min_sleep_s, args.max_sleep_s)
                continue
            if failures >= args.max_consecutive_failures:
                report["stopped_reason"] = "max_consecutive_failures"
                write_report(args.report_file, report)
                return

        await polite_sleep(args.min_sleep_s, args.max_sleep_s)

    report["completed_at"] = now_iso()
    write_report(args.report_file, report)


async def preflight_xhs_search_gate(args: argparse.Namespace) -> dict[str, Any]:
    context = None
    page = None
    browser = None
    playwright = None
    profile_dir = xhs_profile_dir(
        public_search=args_public_search(args),
        public_profile_dir=args_public_profile_dir(args),
    )
    resolved_profile = resolve_profile_dir(profile_dir) if profile_dir else None
    try:
        timeout_s = min(float(args.timeout_s), 35.0)
        device_profile = _playwright_session._device_profile_for_fetch(
            str(resolved_profile) if resolved_profile else None
        )
        user_agent = _playwright_session.pick_user_agent(
            os.getenv("XHS_USER_AGENT"),
            device_profile=device_profile,
        )
        context, browser, playwright = await open_preflight_context(
            resolved_profile=resolved_profile,
            user_agent=user_agent,
            device_profile=device_profile,
            storage_state_path=xhs_storage_state_path(public_search=args_public_search(args)),
            cookie=xhs_cookie(public_search=args_public_search(args)),
        )
        page = await context.new_page()
        page.set_default_timeout(int(timeout_s * 1000))
        page.set_default_navigation_timeout(int(timeout_s * 1000))
        status = await asyncio.wait_for(
            _playwright_session._goto_xhs_search(
                page,
                DEFAULT_SEARCH_DIAGNOSTIC_QUERY,
                timeout_s=timeout_s,
                profile_dir=str(resolved_profile) if resolved_profile else None,
            ),
            timeout=min(float(args.call_timeout_s), 45.0),
        )
        body_text = await _playwright_session._page_body_text(page)
        _playwright_session._raise_for_gate_url(page.url)
        _playwright_session._raise_for_gate_text(body_text)
        selector_counts = await xhs_selector_counts(page)
        has_results = any(selector_counts.values())
        return {
            "ok": has_results,
            "query": DEFAULT_SEARCH_DIAGNOSTIC_QUERY,
            "http_status": status,
            "url": page.url,
            "selector_counts": selector_counts,
            "raw_count": sum(selector_counts.values()),
            "error": "xhs search loaded but no result selectors found" if not has_results else "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "query": DEFAULT_SEARCH_DIAGNOSTIC_QUERY,
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }
    finally:
        if page is not None:
            with contextlib.suppress(Exception):
                await page.close()
        if context is not None:
            with contextlib.suppress(Exception):
                await context.close()
        if browser is not None:
            with contextlib.suppress(Exception):
                await browser.close()
        if playwright is not None:
            with contextlib.suppress(Exception):
                await playwright.stop()


async def open_preflight_context(
    *,
    resolved_profile: Path | None,
    user_agent: str,
    device_profile: str,
    storage_state_path: str | None,
    cookie: str | None,
) -> tuple[Any, Any | None, Any]:
    from playwright.async_api import async_playwright  # noqa: PLC0415

    p = await async_playwright().start()
    browser = None
    try:
        if resolved_profile:
            context = await p.chromium.launch_persistent_context(
                resolved_profile,
                **_playwright_session._browser_launch_kwargs(),
                **_playwright_session._context_kwargs(
                    user_agent=user_agent,
                    storage_state_path=None,
                    device_profile=device_profile,
                ),
            )
            return context, None, p
        browser = await p.chromium.launch(**_playwright_session._browser_launch_kwargs())
        context = await browser.new_context(
            **_playwright_session._context_kwargs(
                user_agent=user_agent,
                storage_state_path=storage_state_path,
                device_profile=device_profile,
            )
        )
        if cookie:
            await _playwright_session._inject_cookie(context, cookie)
        return context, browser, p
    except Exception:
        with contextlib.suppress(Exception):
            if browser is not None:
                await browser.close()
        with contextlib.suppress(Exception):
            await p.stop()
        raise


async def import_local_cache(path: Path) -> None:
    imported = 0
    skipped = 0
    lines = read_local_cache_lines(path)
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            source = str(row.get("source") or "xhs")
            query = str(row.get("query") or "")
            key = xhs_cache_key(query) if source == "xhs" and query else str(row["key"])
            payload = row["payload"]
            if not isinstance(payload, list):
                raise ValueError("payload must be a list")
            payload = filter_authentic_xhs_posts(payload)
            candidate = str(row.get("candidate") or "")
            if candidate:
                payload = filter_relevant_posts(payload, candidate, query)
                payload = mark_quality_checked_posts(payload, candidate, query)
            if not payload:
                skipped += 1
                continue
            await put_cached(source, key, payload)
            imported += 1
        except Exception as exc:
            skipped += 1
            print(
                json.dumps(
                    {
                        "status": "import_row_skipped",
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:300],
                    },
                    ensure_ascii=False,
                )
            )
    print(
        json.dumps(
            {
                "status": "import_local_complete",
                "file": str(path),
                "imported": imported,
                "skipped": skipped,
            },
            ensure_ascii=False,
        )
    )


async def import_xhs_evidence(path: Path) -> None:
    from plus_one.scripts.xhs_evidence_import import import_local_cache_file  # noqa: PLC0415

    stats = await import_local_cache_file(path)
    print(
        json.dumps(
            {
                "status": "xhs_evidence_import_complete",
                "file": str(path),
                "posts": stats.posts,
                "images": stats.images,
                "matches": stats.matches,
            },
            ensure_ascii=False,
        )
    )


def write_coverage_report(args: argparse.Namespace) -> None:
    items = load_query_items(args.query_file)
    report = merge_reports(
        [load_report(path) for path in [args.report_file, *args.extra_report_file]]
    )
    cache_rows = load_local_cache_rows(args.local_cache_file)
    candidate_rows = summarise_candidate_coverage(
        items,
        report,
        cache_rows,
        min_posts_per_candidate=args.min_posts_per_candidate,
    )
    summary = coverage_summary(candidate_rows)
    output = {
        "generated_at": now_iso(),
        "query_file": str(args.query_file),
        "report_file": str(args.report_file),
        "extra_report_files": [str(path) for path in args.extra_report_file],
        "local_cache_file": str(args.local_cache_file),
        "min_posts_per_candidate": args.min_posts_per_candidate,
        "summary": summary,
        "candidates": candidate_rows,
    }
    args.output_file.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.gap_query_file:
        raw_gap_rows = [row for row in candidate_rows if row["status"] != "covered"]
        gap_rows = dedupe_gap_candidate_rows(candidate_rows)
        gap_items = [row["query_item"] for row in gap_rows]
        gap_payload = {
            "candidate_count": len(gap_items),
            "candidate_count_before_dedupe": len(raw_gap_rows),
            "deduped_candidate_count": len(raw_gap_rows) - len(gap_items),
            "query_count": sum(len(item.get("queries") or []) for item in gap_items),
            "items": gap_items,
        }
        args.gap_query_file.write_text(
            json.dumps(gap_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    printable = dict(summary)
    printable["status"] = "coverage_written"
    printable["output_file"] = str(args.output_file)
    if args.gap_query_file:
        printable["gap_query_file"] = str(args.gap_query_file)
        printable["gap_candidate_count"] = len(gap_items)
        printable["gap_deduped_candidate_count"] = len(raw_gap_rows) - len(gap_items)
    print(json.dumps(printable, ensure_ascii=False))


def sanitize_public_gate_report(args: argparse.Namespace) -> None:
    report = load_report(args.report_file)
    diagnostic = load_report(args.diagnostic_file)
    cutoff = latest_public_gate_time(diagnostic)
    sanitized, changed_count = sanitize_public_gate_rows(report, cutoff)
    output_file = args.output_file or args.report_file
    write_report(output_file, sanitized)
    print(
        json.dumps(
            {
                "status": "public_gate_report_sanitized",
                "report_file": str(args.report_file),
                "output_file": str(output_file),
                "diagnostic_file": str(args.diagnostic_file),
                "public_gate_time": cutoff,
                "changed_count": changed_count,
            },
            ensure_ascii=False,
        )
    )


def sanitize_security_gate_report(args: argparse.Namespace) -> None:
    sanitize_public_gate_report(args)


def latest_public_gate_time(diagnostic: dict[str, Any]) -> str:
    latest = ""
    for check in diagnostic.get("checks") or []:
        if not isinstance(check, dict):
            continue
        if check.get("classification") not in {"public_search_gated", "security_verification"}:
            continue
        body = str(check.get("body_excerpt") or "")
        url = str(check.get("url") or "")
        if not is_gate_error(" ".join([url, body, str(check.get("error") or "")])):
            continue
        finished_at = str(check.get("finished_at") or check.get("started_at") or "")
        latest = max(latest, finished_at)
    return latest


def latest_security_gate_time(diagnostic: dict[str, Any]) -> str:
    return latest_public_gate_time(diagnostic)


def sanitize_public_gate_rows(report: dict[str, Any], cutoff: str) -> tuple[dict[str, Any], int]:
    sanitized = dict(report)
    sanitize_indexes = public_gate_sanitize_indexes(report.get("results") or [], cutoff)
    results: list[dict[str, Any]] = []
    changed_count = 0
    for index, row in enumerate(report.get("results") or []):
        if not isinstance(row, dict):
            continue
        updated = dict(row)
        if index in sanitize_indexes:
            updated["skip_reason"] = None
            updated["error_type"] = "XHSPublicSearchGate"
            updated["error"] = (
                "xhs public search gate active: retry later or use public index/detail fallback"
            )
            updated["public_gate_sanitized"] = True
            updated.pop("empty_retry_version", None)
            changed_count += 1
        results.append(updated)
    sanitized["results"] = results
    if changed_count:
        sanitized["public_gate_sanitized_at"] = now_iso()
        sanitized["public_gate_sanitized_count"] = changed_count
    return sanitized, changed_count


def sanitize_security_gate_rows(report: dict[str, Any], cutoff: str) -> tuple[dict[str, Any], int]:
    return sanitize_public_gate_rows(report, cutoff)


def public_gate_sanitize_indexes(rows: list[Any], cutoff: str) -> set[int]:
    if not cutoff:
        return set()

    indexes = {
        index
        for index, row in enumerate(rows)
        if isinstance(row, dict)
        and is_public_gate_suspect_row(row)
        and (row_time := report_row_time(row))
        and row_time >= cutoff
    }
    if indexes:
        return indexes

    # Older reports did not record per-row timestamps. In that case only
    # sanitize the contiguous tail written while the confirmed gate was active.
    trailing: set[int] = set()
    for index in range(len(rows) - 1, -1, -1):
        row = rows[index]
        if not isinstance(row, dict) or not is_public_gate_suspect_row(row):
            break
        trailing.add(index)
    return trailing


def security_gate_sanitize_indexes(rows: list[Any], cutoff: str) -> set[int]:
    return public_gate_sanitize_indexes(rows, cutoff)


def report_row_time(row: dict[str, Any]) -> str:
    return str(row.get("finished_at") or row.get("fetched_at") or row.get("created_at") or "")


def is_public_gate_suspect_row(row: dict[str, Any]) -> bool:
    if row.get("ok"):
        return False
    if row.get("skip_reason") != "no_usable_authentic_posts":
        return False
    if int(row.get("raw_count") or 0) != 0:
        return False
    attempts = row.get("attempts") or []
    return all(
        isinstance(attempt, dict) and int(attempt.get("raw_count") or 0) == 0
        for attempt in attempts
    )


def is_security_gate_suspect_row(row: dict[str, Any]) -> bool:
    return is_public_gate_suspect_row(row)


def dedupe_gap_candidate_rows(candidate_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    covered_keys = {
        key
        for row in candidate_rows
        if row.get("status") == "covered" and (key := canonical_gap_key(row))
    }
    best_by_key: dict[str, dict[str, Any]] = {}
    ordered_keys: list[str] = []
    for row in candidate_rows:
        if row.get("status") == "covered":
            continue
        key = canonical_gap_key(row)
        if key and key in covered_keys:
            continue
        if not key:
            key = f"candidate:{row.get('candidate', '')}"
        if key not in best_by_key:
            best_by_key[key] = row
            ordered_keys.append(key)
            continue
        current = best_by_key[key]
        if gap_row_rank(row) < gap_row_rank(current):
            best_by_key[key] = row
    return sorted((best_by_key[key] for key in ordered_keys), key=gap_row_rank)


def gap_row_rank(row: dict[str, Any]) -> tuple[int, int, int, int, int, int, int]:
    status = str(row.get("status") or "")
    candidate = str(row.get("candidate") or "")
    skipped = int(row.get("skipped_query_count") or 0)
    already_partial = status == "partial" and int(row.get("relevant_post_count") or 0) > 0
    return (
        GAP_DEDUPE_STATUS_RANK.get(status, 9),
        int(already_partial and skipped >= STALE_PARTIAL_SKIP_THRESHOLD),
        skipped if already_partial else min(skipped, 3),
        -int(row.get("relevant_post_count") or 0),
        -int(row.get("relevant_image_count") or 0),
        int(row.get("error_count") or 0),
        int(not has_meaningful_cjk_text(candidate)),
    )


def canonical_gap_key(row: dict[str, Any]) -> str:
    query_item = row.get("query_item")
    if not isinstance(query_item, dict):
        return ""
    queries = query_item.get("queries")
    if not isinstance(queries, list) or not queries:
        return ""
    first_query = next((str(query) for query in queries if query), "")
    if not first_query:
        return ""
    return canonical_gap_query_key(first_query)


def canonical_gap_query_key(query: str) -> str:
    parts = query.strip().split(maxsplit=1)
    if not parts:
        return ""
    destination = compact_relevance_text(parts[0])
    entity = parts[1] if len(parts) > 1 else parts[0]
    for intent in QUERY_INTENTS:
        entity = entity.replace(intent, " ")
    compact_entity = compact_relevance_text(entity)
    if not destination or not compact_entity:
        return compact_entity
    return f"{destination}:{compact_entity}"


def read_local_cache_lines(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"local cache file not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        return list(file)


def load_local_cache_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in read_local_cache_lines(path):
        if not line.strip():
            continue
        with contextlib.suppress(json.JSONDecodeError):
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                rows.append(parsed)
    return rows


def summarise_candidate_coverage(
    items: list[dict[str, Any]],
    report: dict[str, Any],
    cache_rows: list[dict[str, Any]],
    *,
    min_posts_per_candidate: int,
) -> list[dict[str, Any]]:
    report_stats = collect_report_stats(report)
    cache_stats = collect_cache_stats(cache_rows)
    return [
        build_candidate_coverage_row(
            item,
            report_stats,
            cache_stats,
            min_posts_per_candidate=min_posts_per_candidate,
        )
        for item in items
    ]


def collect_report_stats(report: dict[str, Any]) -> dict[str, Any]:
    ok_queries_by_candidate: dict[str, set[str]] = {}
    skipped_by_candidate: dict[str, int] = {}
    errors_by_candidate: dict[str, int] = {}
    last_error_by_candidate: dict[str, str] = {}
    for row in report.get("results") or []:
        if not isinstance(row, dict):
            continue
        candidate = str(row.get("candidate") or "")
        query = str(row.get("query") or "")
        if not candidate:
            continue
        if row.get("ok"):
            ok_queries_by_candidate.setdefault(candidate, set()).add(query)
        elif row.get("skip_reason") in NORMAL_SKIP_REASONS:
            skipped_by_candidate[candidate] = skipped_by_candidate.get(candidate, 0) + 1
        elif row.get("skip_reason") in TRANSIENT_SKIP_REASONS or is_gate_error(
            str(row.get("error") or "")
        ):
            continue
        else:
            errors_by_candidate[candidate] = errors_by_candidate.get(candidate, 0) + 1
            last_error_by_candidate[candidate] = str(
                row.get("error") or row.get("error_type") or ""
            )[:300]
    return {
        "ok_queries": ok_queries_by_candidate,
        "skipped": skipped_by_candidate,
        "errors": errors_by_candidate,
        "last_errors": last_error_by_candidate,
    }


def collect_cache_stats(cache_rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    cached_posts_by_candidate: dict[str, int] = {}
    cached_images_by_candidate: dict[str, int] = {}
    relevant_posts_by_candidate: dict[str, int] = {}
    relevant_images_by_candidate: dict[str, int] = {}
    cached_seen_by_candidate: dict[str, set[str]] = {}
    relevant_seen_by_candidate: dict[str, set[str]] = {}
    for row in cache_rows:
        candidate = str(row.get("candidate") or "")
        payload = row.get("payload")
        if not candidate or not isinstance(payload, list):
            continue
        posts = [post for post in payload if isinstance(post, dict)]
        relevant = filter_relevant_posts(posts, candidate, str(row.get("query") or ""))
        cached_unique = unseen_posts_for_candidate(candidate, posts, cached_seen_by_candidate)
        relevant_unique = unseen_posts_for_candidate(
            candidate, relevant, relevant_seen_by_candidate
        )
        cached_posts_by_candidate[candidate] = cached_posts_by_candidate.get(candidate, 0) + len(
            cached_unique
        )
        cached_images_by_candidate[candidate] = cached_images_by_candidate.get(candidate, 0) + sum(
            len(post.get("images") or []) for post in cached_unique
        )
        relevant_posts_by_candidate[candidate] = relevant_posts_by_candidate.get(
            candidate, 0
        ) + len(relevant_unique)
        relevant_images_by_candidate[candidate] = relevant_images_by_candidate.get(
            candidate, 0
        ) + sum(len(post.get("images") or []) for post in relevant_unique)
    return {
        "cached_posts": cached_posts_by_candidate,
        "cached_images": cached_images_by_candidate,
        "relevant_posts": relevant_posts_by_candidate,
        "relevant_images": relevant_images_by_candidate,
    }


def unseen_posts_for_candidate(
    candidate: str,
    posts: list[dict[str, Any]],
    seen_by_candidate: dict[str, set[str]],
) -> list[dict[str, Any]]:
    seen = seen_by_candidate.setdefault(candidate, set())
    unique: list[dict[str, Any]] = []
    for post in posts:
        key = post_identity(post)
        if key in seen:
            continue
        seen.add(key)
        unique.append(post)
    return unique


def post_identity(post: dict[str, Any]) -> str:
    for field in ("id", "url"):
        value = str(post.get(field) or "").strip()
        if value:
            return value
    return compact_relevance_text(
        " ".join(str(post.get(field) or "") for field in ("title", "body", "author"))
    )


def build_candidate_coverage_row(
    item: dict[str, Any],
    report_stats: dict[str, Any],
    cache_stats: dict[str, dict[str, int]],
    *,
    min_posts_per_candidate: int,
) -> dict[str, Any]:
    candidate = str(item.get("candidate") or "")
    ok_queries = sorted(report_stats["ok_queries"].get(candidate, set()))
    relevant_posts = cache_stats["relevant_posts"].get(candidate, 0)
    errors = report_stats["errors"].get(candidate, 0)
    skipped = report_stats["skipped"].get(candidate, 0)
    status = candidate_coverage_status(
        relevant_posts=relevant_posts,
        ok_query_count=len(ok_queries),
        skipped_query_count=skipped,
        error_count=errors,
        min_posts_per_candidate=min_posts_per_candidate,
    )
    query_item = enrich_query_item_for_gaps(item)
    return {
        "candidate": candidate,
        "category": item.get("category"),
        "destinations": item.get("destinations") or [],
        "status": status,
        "ok_query_count": len(ok_queries),
        "skipped_query_count": skipped,
        "error_count": errors,
        "last_error": report_stats["last_errors"].get(candidate),
        "cached_post_count": cache_stats["cached_posts"].get(candidate, 0),
        "cached_image_count": cache_stats["cached_images"].get(candidate, 0),
        "relevant_post_count": relevant_posts,
        "relevant_image_count": cache_stats["relevant_images"].get(candidate, 0),
        "ok_queries": ok_queries[:8],
        "next_queries": query_item.get("queries", [])[:8],
        "query_item": query_item,
    }


def candidate_coverage_status(
    *,
    relevant_posts: int,
    ok_query_count: int,
    skipped_query_count: int,
    error_count: int,
    min_posts_per_candidate: int,
) -> str:
    if relevant_posts >= min_posts_per_candidate:
        return "covered"
    if ok_query_count or relevant_posts:
        return "partial"
    if skipped_query_count:
        return "no_usable_authentic_posts"
    if error_count:
        return "error"
    return "untouched"


def coverage_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "unknown")
        by_status[status] = by_status.get(status, 0) + 1
    return {
        "candidate_count": len(rows),
        "covered": by_status.get("covered", 0),
        "partial": by_status.get("partial", 0),
        "no_usable_authentic_posts": by_status.get("no_usable_authentic_posts", 0),
        "error": by_status.get("error", 0),
        "untouched": by_status.get("untouched", 0),
        "total_relevant_posts": sum(int(row.get("relevant_post_count") or 0) for row in rows),
        "total_relevant_images": sum(int(row.get("relevant_image_count") or 0) for row in rows),
    }


def enrich_query_item_for_gaps(item: dict[str, Any]) -> dict[str, Any]:
    candidate = str(item.get("candidate") or "")
    original_queries = [str(query) for query in item.get("queries") or [] if query]
    explicit_aliases = [str(alias) for alias in item.get("aliases") or [] if alias]
    destinations = [
        str(destination) for destination in item.get("destinations") or [] if destination
    ]
    destination_aliases = destination_aliases_for_item(destinations)
    strip_destination_aliases = all_destination_aliases_for_item(destinations)
    category = str(item.get("category") or "generic")
    queries: list[str] = []
    names = search_candidate_names(candidate, explicit_aliases)
    preferred_names: list[str] = []
    for destination in destination_aliases:
        search_names = search_names_for_destination(names, strip_destination_aliases)
        for name_group in localized_name_groups(search_names):
            preferred_names.extend(name_group)
            for intent in category_query_intents_for_candidate(category, candidate, name_group):
                for search_name in name_group:
                    query = " ".join(
                        part for part in (destination, search_name, intent) if part
                    ).strip()
                    append_query_once(queries, query)
    for query in original_queries:
        if should_keep_original_query(query, preferred_names):
            append_query_once(queries, query)
    enriched = dict(item)
    enriched["queries"] = queries
    return enriched


def append_query_once(queries: list[str], query: str) -> None:
    if query and query not in queries:
        queries.append(query)


def destination_aliases_for_item(destinations: list[str]) -> tuple[str, ...]:
    return preferred_destination_aliases(all_destination_aliases_for_item(destinations))


def all_destination_aliases_for_item(destinations: list[str]) -> tuple[str, ...]:
    if not destinations:
        return ("",)
    destination = destinations[0]
    return DESTINATION_QUERY_ALIASES.get(
        destination, DESTINATION_NAME_ALIASES.get(destination, (destination,))
    )


def preferred_destination_aliases(aliases: tuple[str, ...]) -> tuple[str, ...]:
    unique = tuple(dict.fromkeys(alias for alias in aliases if alias))
    localized = tuple(alias for alias in unique if has_meaningful_cjk_text(alias))
    return localized or unique


def search_candidate_names(candidate: str, explicit_aliases: list[str] | None = None) -> list[str]:
    names: list[str] = []
    for source in (
        explicit_aliases or [],
        XHS_NAME_ALIASES.get(candidate, ()),
        XHS_CONTEXTUAL_NAME_ALIASES.get(candidate, ()),
        cjk_names_from_parentheses(candidate),
    ):
        names.extend(source)
    names.extend(english_fallback_candidate_names(candidate))
    return localized_first_names(names)


def search_names_for_destination(
    names: list[str], destination_aliases: tuple[str, ...]
) -> list[str]:
    stripped = [strip_destination_alias_from_name(name, destination_aliases) for name in names]
    return localized_first_names(stripped)


def localized_name_groups(names: list[str]) -> list[list[str]]:
    localized = [name for name in names if is_localized_search_name(name)]
    latin = [name for name in names if name not in localized]
    if localized:
        return [localized]
    if latin:
        return [latin]
    return []


def should_keep_original_query(query: str, preferred_names: list[str]) -> bool:
    localized_names = [name for name in preferred_names if is_localized_search_name(name)]
    if not localized_names:
        return True
    compact_query = compact_relevance_text(query)
    return any(compact_relevance_text(name) in compact_query for name in localized_names)


def is_localized_search_name(name: str) -> bool:
    if not has_cjk_text(name):
        return False
    if has_meaningful_cjk_text(name):
        return True
    return has_specific_latin_brand_text(name)


def has_specific_latin_brand_text(text: str) -> bool:
    words = re.findall(r"[a-z][a-z0-9]+", text.casefold())
    specific_words = [
        word
        for word in words
        if word not in GENERIC_RELEVANCE_TERMS and len(word) >= MIN_SPECIFIC_LATIN_BRAND_CHARS
    ]
    return bool(specific_words)


def strip_destination_alias_from_name(name: str, destination_aliases: tuple[str, ...]) -> str:
    cleaned = name.strip()
    for raw_alias in sorted(destination_aliases, key=len, reverse=True):
        alias = raw_alias.strip()
        if not alias or cleaned == alias:
            continue
        if cleaned.startswith(f"{alias} "):
            cleaned = cleaned[len(alias) :].strip()
        if cleaned.endswith(f" {alias}"):
            cleaned = cleaned[: -len(alias)].strip()
    return cleaned or name


def category_query_intents(category: str) -> tuple[str, ...]:
    if category == "food":
        return ("美食推荐", "本地人推荐", "真实体验", "值得吃吗", "避雷")
    if category == "drink":
        return ("饮品推荐", "本地人推荐", "真实体验", "氛围", "避雷")
    if category == "attraction":
        return ("本地人必去景点推荐", "小众景点", "真实体验", "值得去吗", "避雷")
    return ("本地人推荐", "真实体验", "小红书推荐", "攻略", "避雷")


def category_query_intents_for_candidate(
    category: str,
    candidate: str,
    names: list[str],
) -> tuple[str, ...]:
    text = intent_detection_text(candidate, names)
    intents = category_query_intents(category)
    if is_ramen_candidate(text):
        intents = (
            "拉面推荐",
            "拉面店推荐",
            "排队拉面",
            "本地人推荐",
            "真实体验",
            "值得吃吗",
            "避雷",
        )
    elif is_tea_candidate(text):
        intents = ("茶室推荐", "本地人推荐", "真实体验", "茶道体验", "避雷")
    elif is_cafe_candidate(text):
        intents = ("咖啡推荐", "本地人推荐", "真实体验", "氛围", "避雷")
    elif is_dessert_candidate(text):
        intents = ("甜品推荐", "本地人推荐", "真实体验", "值得吃吗", "避雷")
    elif is_bar_candidate(text):
        intents = ("酒吧推荐", "居酒屋推荐", "本地人推荐", "真实体验", "氛围", "避雷")
    elif is_street_food_candidate(text):
        intents = ("美食推荐", "街头小吃", "本地人推荐", "真实体验", "值得吃吗", "避雷")
    elif is_food_candidate(text):
        intents = category_query_intents("food")
    return intents


def intent_detection_text(candidate: str, names: list[str]) -> str:
    raw = " ".join([candidate, *names])
    return raw.translate(CJK_NORMALIZATION_TABLE).casefold()


def is_tea_candidate(text: str) -> bool:
    compact = compact_relevance_text(text)
    keywords = (
        "茶",
        "tea",
        "teahouse",
        "tea house",
        "tearoom",
        "tea room",
        "chaya",
        "chaho",
        "saryo",
        "saryou",
        "kissako",
        "ocha",
        "matcha",
        "macha",
        "camellia",
        "fukujuen",
        "ippodo",
        "ryukoen",
        "tsujiri",
        "ujien",
        "marukyu",
        "obubu",
        "kanbayashi",
        "hakuun",
        "amazake",
        "chairo",
        "houraidou",
        "maeda-en",
    )
    return any(
        keyword in text or compact_relevance_text(keyword) in compact for keyword in keywords
    )


def is_cafe_candidate(text: str) -> bool:
    compact = compact_relevance_text(text)
    keywords = ("咖啡", "cafe", "café", "coffee", "kissa", "kissaten", "喫茶")
    return any(
        keyword in text or compact_relevance_text(keyword) in compact for keyword in keywords
    )


def is_dessert_candidate(text: str) -> bool:
    compact = compact_relevance_text(text)
    keywords = ("甜品", "甜点", "dessert", "sweets", "wagashi", "抄院", "然花")
    return any(
        keyword in text or compact_relevance_text(keyword) in compact for keyword in keywords
    )


def is_bar_candidate(text: str) -> bool:
    compact = compact_relevance_text(text)
    keywords = (
        "酒吧",
        "居酒屋",
        "啤酒",
        "bar",
        "beer",
        "brewery",
        "taproom",
        "izakaya",
        "yokocho",
        "横丁",
        "麦酒",
        "薄野",
        "susukino",
    )
    return any(
        keyword in text or compact_relevance_text(keyword) in compact for keyword in keywords
    )


def is_street_food_candidate(text: str) -> bool:
    compact = compact_relevance_text(text)
    keywords = (
        "街头小吃",
        "小吃街",
        "美食街",
        "夜市",
        "早市",
        "宵夜",
        "大排档",
        "路边摊",
        "摊",
        "food walk",
        "food stall",
        "food stalls",
        "street food",
        "night food",
        "night market",
        "morning market",
        "late-night street food",
        "market",
        "souk",
        "spice market",
        "market spice",
        "市集",
        "市场",
        "香料市场",
        "dai pai dong",
        "dai pai dongs",
        "paranthe wali gali",
        "parathe wali gali",
    )
    return any(
        keyword in text or compact_relevance_text(keyword) in compact for keyword in keywords
    )


def is_ramen_candidate(text: str) -> bool:
    compact = compact_relevance_text(text)
    keywords = (
        "拉面",
        "拉麵",
        "らーめん",
        "ラーメン",
        "らぁ麺",
        "麺",
        "タンメン",
        "湯面",
        "汤面",
        "面屋",
        "麺屋",
        "menya",
        "ramen",
        "soba noodles",
    )
    return any(
        keyword in text or compact_relevance_text(keyword) in compact for keyword in keywords
    )


def is_food_candidate(text: str) -> bool:
    compact = compact_relevance_text(text)
    keywords = (
        "美食",
        "餐厅",
        "饭店",
        "海鲜",
        "烤羊",
        "烤肉",
        "烧肉",
        "成吉思汗",
        "牛杂",
        "粥",
        "拉面",
        "荞麦",
        "面家",
        "面店",
        "肠粉",
        "云吞",
        "蜗牛",
        "restaurant",
        "ramen",
        "soba",
        "udon",
        "sushi",
        "seafood",
        "congee",
        "beef",
        "lamb",
        "meat",
        "mechoui",
        "jingisukan",
        "genghis khan",
        "karim",
        "paranthe",
        "parathe",
        "food",
    )
    return any(
        keyword in text or compact_relevance_text(keyword) in compact for keyword in keywords
    )


def prewarm_work_items(
    items: list[dict[str, Any]],
    limit_candidates: int,
    queries_per_candidate: int,
    done: set[tuple[str, str]],
) -> list[dict[str, str]]:
    query_limit = max(0, queries_per_candidate)
    if query_limit == 0:
        return []
    work: list[dict[str, str]] = []
    selected_candidates = 0
    for item in items:
        if 0 < limit_candidates <= selected_candidates:
            break
        candidate = str(item.get("candidate") or "")
        queries = [str(query) for query in item.get("queries") or [] if query]
        pending = [query for query in queries if (candidate, query) not in done]
        if not pending:
            continue
        selected_candidates += 1
        for query in pending[:query_limit]:
            work.append({"candidate": candidate, "query": query})
    return work


def resume_done_queries(report: dict[str, Any]) -> set[tuple[str, str]]:
    done: set[tuple[str, str]] = set()
    for row in report.get("results") or []:
        if not isinstance(row, dict):
            continue
        candidate = str(row.get("candidate") or "")
        query = row.get("query")
        if not candidate or not isinstance(query, str) or not query:
            continue
        if row.get("ok") and row.get("quality_version") == RESULT_QUALITY_VERSION:
            done.add((candidate, query))
            original_query = str(row.get("original_query") or "")
            if original_query:
                done.add((candidate, original_query))
            continue
        if (
            row.get("skip_reason") in NORMAL_SKIP_REASONS
            and row.get("attempts")
            and row.get("empty_retry_version") == EMPTY_RETRY_VERSION
        ):
            done.add((candidate, query))
            for attempt in row.get("attempts") or []:
                if isinstance(attempt, dict) and isinstance(attempt.get("query"), str):
                    done.add((candidate, str(attempt["query"])))
    return done


async def fetch_one(query: str, candidate: str, args: argparse.Namespace) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    last_full_result: dict[str, Any] | None = None
    for attempt_index, attempt_query in enumerate(
        candidate_queries(query, candidate, args.max_query_attempts), start=1
    ):
        print(
            json.dumps(
                {
                    "status": "xhs_attempt_start",
                    "candidate": candidate,
                    "original_query": query,
                    "attempt_index": attempt_index,
                    "attempt_query": attempt_query,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        result = await fetch_query_once(attempt_query, candidate, args)
        last_full_result = result
        attempts.append(
            {
                "query": attempt_query,
                "ok": result.get("ok"),
                "raw_count": result.get("raw_count", 0),
                "usable_count": result.get("usable_count", 0),
                "skip_reason": result.get("skip_reason"),
                "error_type": result.get("error_type"),
                "error": result.get("error"),
            }
        )
        if result.get("ok"):
            if attempt_query != query:
                result["original_query"] = query
                await mirror_cached_payload(query, attempt_query, result)
            result["attempts"] = attempts
            return result
        if result.get("error") and result.get("skip_reason") not in TRANSIENT_SKIP_REASONS:
            if attempt_query != query:
                result["original_query"] = query
            result["attempts"] = attempts
            return result

    result = attempts[-1] if attempts else {"ok": False, "query": query}
    if isinstance(last_full_result, dict) and last_full_result.get("candidate") == candidate:
        result = {**last_full_result, "attempts": attempts}
        result.setdefault("empty_retry_version", EMPTY_RETRY_VERSION)
        result.setdefault("quality_version", RESULT_QUALITY_VERSION)
        result.setdefault("skip_reason", "no_usable_authentic_posts")
        result["query"] = query
        result["key"] = xhs_cache_key(query)
        return result
    return {
        "ok": False,
        "candidate": candidate,
        "query": query,
        "key": xhs_cache_key(query),
        "raw_count": result.get("raw_count", 0),
        "usable_count": 0,
        "promotional_dropped_count": 0,
        "image_count": 0,
        "skip_reason": "no_usable_authentic_posts",
        "empty_retry_version": EMPTY_RETRY_VERSION,
        "quality_version": RESULT_QUALITY_VERSION,
        "attempts": attempts,
    }


async def fetch_query_once(query: str, candidate: str, args: argparse.Namespace) -> dict[str, Any]:
    if bool(getattr(args, "public_index_only", False)):
        try:
            return await fetch_public_index_with_timeout(query, candidate, args)
        except Exception as exc:
            return fetch_error_result(query, candidate, exc)

    try:
        public_search = args_public_search(args)
        scrape = await asyncio.wait_for(
            _playwright_session.fetch(
                query,
                cookie=xhs_cookie(public_search=public_search),
                storage_state_path=xhs_storage_state_path(public_search=public_search),
                profile_dir=xhs_profile_dir(
                    public_search=public_search,
                    public_profile_dir=args_public_profile_dir(args),
                ),
                limit=args.post_limit,
                user_agent=os.getenv("XHS_USER_AGENT"),
                timeout_s=args.timeout_s,
                cache_images=True,
                images_per_post=args.images_per_post,
            ),
            timeout=args.call_timeout_s,
        )
        return await build_fetch_result(
            scrape.posts,
            query,
            candidate,
            args,
            source="live_xhs",
            require_local_images=True,
        )
    except Exception as exc:
        if is_transient_xhs_gate(exc):
            with contextlib.suppress(Exception):
                index_result = await fetch_public_index_with_timeout(query, candidate, args)
                if index_result.get("raw_count") or index_result.get("ok"):
                    return index_result
            index_result = {}
            return {
                "ok": False,
                "candidate": candidate,
                "query": query,
                "key": xhs_cache_key(query),
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
                "skip_reason": "public_search_gated",
            }
        return {
            "ok": False,
            "candidate": candidate,
            "query": query,
            "key": xhs_cache_key(query),
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }


async def fetch_public_index_with_timeout(
    query: str, candidate: str, args: argparse.Namespace
) -> dict[str, Any]:
    return await asyncio.wait_for(
        fetch_public_index_once(query, candidate, args),
        timeout=float(args.call_timeout_s),
    )


def fetch_error_result(query: str, candidate: str, exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "candidate": candidate,
        "query": query,
        "key": xhs_cache_key(query),
        "error_type": type(exc).__name__,
        "error": str(exc)[:500],
    }


async def fetch_public_index_once(
    query: str, candidate: str, args: argparse.Namespace
) -> dict[str, Any]:
    tool = XHSSearchTool()
    indexed = await tool._fetch_from_search_index(query, int(args.post_limit))
    if not indexed:
        return {
            "ok": False,
            "candidate": candidate,
            "query": query,
            "key": xhs_cache_key(query),
            "raw_count": 0,
            "usable_count": 0,
            "image_count": 0,
            "skip_reason": "public_search_gated",
            "source": "public_search_index",
        }
    enriched = await tool._enrich_indexed_posts(
        indexed,
        int(args.post_limit),
        timeout_s=float(args.timeout_s),
        images_per_post=int(args.images_per_post),
    )
    return await build_fetch_result(
        enriched,
        query,
        candidate,
        args,
        source="public_search_index",
        require_local_images=True,
    )


async def build_fetch_result(
    raw_posts: list[dict[str, Any]],
    query: str,
    candidate: str,
    args: argparse.Namespace,
    *,
    source: str,
    require_local_images: bool,
) -> dict[str, Any]:
    text_usable = usable_posts(raw_posts, require_images=False)
    image_usable = [
        post
        for post in text_usable
        if post_has_required_images(post, require_local=require_local_images)
    ]
    authentic_posts = filter_authentic_xhs_posts(text_usable)
    posts = filter_relevant_posts(authentic_posts, candidate, query)
    relevant_text_posts = posts
    if not bool(getattr(args, "allow_text_only", False)):
        posts = [
            post
            for post in posts
            if post_has_required_images(post, require_local=require_local_images)
        ]
    posts = mark_quality_checked_posts(posts, candidate, query)
    key = xhs_cache_key(query)
    if posts:
        await put_cached("xhs", key, posts)
        local_cache_file = getattr(args, "local_cache_file", None)
        if local_cache_file is not None:
            append_local_cache(local_cache_file, query, candidate, posts)
    diagnostics = pipeline_diagnostics(
        raw_posts=raw_posts,
        text_usable=text_usable,
        image_usable=image_usable,
        authentic_posts=authentic_posts,
        relevant_text_posts=relevant_text_posts,
        final_posts=posts,
    )
    return {
        "ok": bool(posts),
        "candidate": candidate,
        "query": query,
        "key": key,
        "source": source,
        "raw_count": len(raw_posts),
        "text_usable_count": len(text_usable),
        "image_usable_count": len(image_usable),
        "authentic_count": len(authentic_posts),
        "relevant_text_count": len(relevant_text_posts),
        "usable_count": len(posts),
        "promotional_dropped_count": len(text_usable) - len(authentic_posts),
        "irrelevant_dropped_count": len(authentic_posts) - len(relevant_text_posts),
        "missing_image_count": len(relevant_text_posts) - len(posts),
        "image_count": sum(len(post.get("images") or []) for post in posts),
        "skip_reason": skip_reason_for_posts(
            text_usable, authentic_posts, relevant_text_posts, posts
        ),
        "quality_version": RESULT_QUALITY_VERSION,
        "sample": preview_post(
            posts[0]
            if posts
            else relevant_text_posts[0]
            if relevant_text_posts
            else raw_posts[0]
            if raw_posts
            else None
        ),
        "diagnostics": diagnostics,
    }


def post_has_required_images(post: dict[str, Any], *, require_local: bool) -> bool:
    images = [image for image in post.get("images") or [] if isinstance(image, str)]
    if not images:
        return False
    if require_local:
        return any(image.startswith("/media/") for image in images)
    return True


def is_transient_xhs_gate(exc: Exception) -> bool:
    return is_gate_error(str(exc))


def is_public_search_gate(exc: Exception) -> bool:
    return is_transient_xhs_gate(exc)


def candidate_queries(
    query: str, candidate: str, max_attempts: int = MAX_QUERY_ATTEMPTS
) -> list[str]:
    queries = [query]
    intent = query_intent(query)
    raw_destination = query_destination(query)
    destination_aliases = destination_aliases_for_query(raw_destination)
    destination = preferred_query_destination(raw_destination, destination_aliases)
    limit = max(1, max_attempts)
    if len(queries) >= limit:
        return queries[:limit]
    names = search_names_for_destination(
        localized_fallback_candidate_names(candidate), destination_aliases
    )
    for name_group in localized_name_groups(names):
        for fallback_intent in fallback_query_intents(intent):
            for search_name in name_group:
                fallback = " ".join(
                    part for part in (destination, search_name, fallback_intent) if part
                ).strip()
                if fallback and fallback not in queries:
                    queries.append(fallback)
                if len(queries) >= limit:
                    return queries[:limit]
    return queries[:limit]


def destination_aliases_for_query(destination: str) -> tuple[str, ...]:
    aliases = [destination]
    for key, values in DESTINATION_QUERY_ALIASES.items():
        if destination == key or destination in values:
            aliases.append(key)
            aliases.extend(values)
    for key, values in DESTINATION_NAME_ALIASES.items():
        if destination == key or destination in values:
            aliases.append(key)
            aliases.extend(values)
    return tuple(dict.fromkeys(alias for alias in aliases if alias))


def preferred_query_destination(destination: str, aliases: tuple[str, ...]) -> str:
    localized = [alias for alias in aliases if has_meaningful_cjk_text(alias)]
    return localized[0] if localized else destination


def fallback_candidate_names(candidate: str) -> list[str]:
    names: list[str] = []
    names.extend(XHS_NAME_ALIASES.get(candidate, ()))
    names.extend(XHS_CONTEXTUAL_NAME_ALIASES.get(candidate, ()))
    names.extend(cjk_names_from_parentheses(candidate))
    names.extend(english_fallback_candidate_names(candidate))
    return localized_first_names(names)


def localized_fallback_candidate_names(candidate: str) -> list[str]:
    names: list[str] = []
    names.extend(XHS_NAME_ALIASES.get(candidate, ()))
    names.extend(XHS_CONTEXTUAL_NAME_ALIASES.get(candidate, ()))
    names.extend(cjk_names_from_parentheses(candidate))
    return [name for name in localized_first_names(names) if is_localized_search_name(name)]


def cjk_names_from_parentheses(candidate: str) -> list[str]:
    names: list[str] = []
    for raw_inner in re.findall(PAREN_CONTENT_RE, candidate):
        inner = clean_candidate_name(raw_inner)
        if inner and has_cjk_text(inner):
            names.append(inner)
    return unique_candidate_names(names)


def english_fallback_candidate_names(candidate: str) -> list[str]:
    names: list[str] = []
    no_parens = clean_candidate_name(re.sub(PAREN_BLOCK_RE, " ", candidate))
    if no_parens:
        names.append(no_parens)

    first_segment = clean_candidate_name(re.split(SEGMENT_SPLIT_RE, no_parens, maxsplit=1)[0])
    if first_segment:
        names.append(first_segment)

    compact = clean_candidate_name(candidate)
    if compact and (not has_cjk_text(compact) or compact == no_parens or not no_parens):
        names.append(compact)
    return unique_candidate_names(names)


def unique_candidate_names(names: list[str]) -> list[str]:
    unique: list[str] = []
    for name in names:
        if name and name not in unique and len(name) <= MAX_FALLBACK_NAME_CHARS:
            unique.append(name)
    return unique


def localized_first_names(names: list[str]) -> list[str]:
    unique = unique_candidate_names(names)
    localized = sorted(
        [name for name in unique if has_meaningful_cjk_text(name)],
        key=localized_name_sort_key,
    )
    latin = [name for name in unique if name not in localized]
    return localized + latin


def localized_name_sort_key(name: str) -> tuple[int, int]:
    # XHS queries should prefer Chinese names when both Chinese and Japanese or
    # Korean aliases exist. Keep original order within the same script bucket.
    if HAN_TEXT_RE.search(name):
        return (0, 0)
    return (1, 0)


def has_cjk_text(text: str) -> bool:
    return bool(CJK_TEXT_RE.search(text))


def has_meaningful_cjk_text(text: str) -> bool:
    for chunk in re.findall(
        r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]+", text.translate(CJK_NORMALIZATION_TABLE)
    ):
        compact = compact_relevance_text(chunk)
        if compact and compact not in GENERIC_CJK_COMPACT_RELEVANCE_TERMS:
            return True
    return False


def filter_relevant_posts(
    posts: list[dict[str, Any]], candidate: str, query: str
) -> list[dict[str, Any]]:
    terms = relevance_terms(candidate, query)
    if not terms:
        return [post for post in posts if not has_destination_title_conflict(post, query)]
    return [
        post
        for post in posts
        if not has_destination_title_conflict(post, query)
        and candidate_relevance_score(post, terms, candidate=candidate, query=query)
        >= MIN_CANDIDATE_RELEVANCE_SCORE
    ]


def has_destination_title_conflict(post: dict[str, Any], query: str) -> bool:
    title = str(post.get("title") or "")
    if not title:
        return False
    target_aliases = destination_aliases_for_query(query_destination(query))
    target_compacts = {compact_relevance_text(alias) for alias in target_aliases if alias}
    title_compact = compact_relevance_text(title)
    if not title_compact or any(alias and alias in title_compact for alias in target_compacts):
        return False
    return any(
        alias_compact in title_compact
        for alias_compact in competing_destination_alias_compacts(target_compacts)
    )


def competing_destination_alias_compacts(target_compacts: set[str]) -> set[str]:
    aliases: set[str] = set()
    for raw_aliases in DESTINATION_QUERY_ALIASES.values():
        aliases.update(compact_relevance_text(alias) for alias in raw_aliases if alias)
    for raw_aliases in DESTINATION_NAME_ALIASES.values():
        aliases.update(compact_relevance_text(alias) for alias in raw_aliases if alias)
    aliases.update(
        compact_relevance_text(alias)
        for alias in (
            "东京",
            "東京",
            "京都",
            "大阪",
            "札幌",
            "上海",
            "广州",
            "廣州",
            "箱根",
            "德里",
            "新德里",
            "马拉喀什",
            "marrakesh",
            "marrakech",
            "tokyo",
            "kyoto",
            "osaka",
            "sapporo",
            "shanghai",
            "guangzhou",
            "hakone",
            "delhi",
            "newdelhi",
        )
    )
    return {alias for alias in aliases if alias and alias not in target_compacts}


def mark_quality_checked_posts(
    posts: list[dict[str, Any]], candidate: str, query: str
) -> list[dict[str, Any]]:
    terms = relevance_terms(candidate, query)
    marked: list[dict[str, Any]] = []
    for post in posts:
        updated = dict(post)
        score, matched_terms = candidate_relevance_match(post, terms)
        updated["xhs_quality_version"] = RESULT_QUALITY_VERSION
        updated["xhs_candidate"] = candidate
        updated["xhs_query"] = query
        updated["xhs_relevance_score"] = score
        updated["xhs_relevance_terms"] = matched_terms[:5]
        marked.append(updated)
    return marked


def candidate_relevance_score(
    post: dict[str, Any],
    terms: list[str],
    *,
    candidate: str | None = None,
    query: str | None = None,
) -> float:
    if candidate and query and post_quality_matches_candidate(post, candidate, query):
        try:
            return float(post.get("xhs_relevance_score") or 0.0)
        except (TypeError, ValueError):
            return 0.0
    score, _matched_terms = candidate_relevance_match(post, terms)
    return score


def post_quality_matches_candidate(post: dict[str, Any], candidate: str, query: str) -> bool:
    if post.get("xhs_quality_version") != RESULT_QUALITY_VERSION:
        return False
    return (
        str(post.get("xhs_candidate") or "") == candidate
        and str(post.get("xhs_query") or "") == query
    )


def candidate_relevance_match(post: dict[str, Any], terms: list[str]) -> tuple[float, list[str]]:
    text = " ".join(
        str(post.get(field) or "") for field in ("title", "body", "author", "url")
    ).casefold()
    compact_text = compact_relevance_text(text)
    best = 0.0
    matched_terms: list[str] = []
    for term in terms:
        folded = term.casefold()
        compact = compact_relevance_text(folded)
        if not folded or not compact:
            continue
        if (
            folded in text
            or compact in compact_text
            or reordered_relevance_match(term, compact_text)
        ):
            best = max(best, relevance_weight(term))
            matched_terms.append(term)
    return best, matched_terms


def reordered_relevance_match(term: str, compact_text: str) -> bool:
    tokens = relevance_match_tokens(term)
    if len(tokens) < MIN_REORDERABLE_RELEVANCE_TOKENS:
        return False
    return all(token in compact_text for token in tokens)


def relevance_match_tokens(term: str) -> list[str]:
    tokens: list[str] = []
    for raw in re.split(r"\s+", term):
        compact = compact_relevance_text(raw)
        if not compact:
            continue
        if any(ord(char) > ASCII_MAX_CODEPOINT for char in raw):
            if len(compact) >= MIN_REORDERABLE_CJK_TOKEN_CHARS:
                tokens.append(compact)
        elif is_specific_relevance_term(raw):
            tokens.append(compact)
    return unique_candidate_names(tokens)


def relevance_terms(candidate: str, query: str) -> list[str]:
    terms: list[str] = []
    terms.extend(fallback_candidate_names(candidate))
    terms.extend(query_entity_terms(query))
    for alias in XHS_NAME_ALIASES.get(
        candidate, ()
    ):  # explicit for readability when aliases are short
        terms.append(alias)
    unique: list[str] = []
    for term in terms:
        cleaned = clean_relevance_term(term)
        if cleaned and cleaned not in unique and is_specific_relevance_term(cleaned):
            unique.append(cleaned)
    return unique


def query_entity_terms(query: str) -> list[str]:
    text = query
    destination = query_destination(query)
    if destination and text.startswith(destination):
        text = text[len(destination) :]
    for intent in QUERY_INTENTS:
        text = text.replace(intent, " ")
    return [text.strip()]


def clean_relevance_term(term: str) -> str:
    cleaned = clean_candidate_name(term)
    cleaned = re.sub(
        r"\b(?:recommend|recommended|review|reviews|guide)\b", " ", cleaned, flags=re.IGNORECASE
    )
    cleaned = cleaned.translate(CJK_NORMALIZATION_TABLE)
    return " ".join(cleaned.split()).strip()


def is_specific_relevance_term(term: str) -> bool:
    compact = compact_relevance_text(term)
    if any(ord(char) > ASCII_MAX_CODEPOINT for char in term):
        if compact in GENERIC_CJK_COMPACT_RELEVANCE_TERMS:
            return False
        return len(compact) >= MIN_CJK_RELEVANCE_CHARS
    words = re.findall(r"[a-z0-9]+", term.casefold())
    specific_words = [
        word
        for word in words
        if word not in GENERIC_RELEVANCE_TERMS and len(word) >= MIN_LATIN_RELEVANCE_WORD_CHARS
    ]
    return bool(
        len("".join(specific_words)) >= MIN_LATIN_JOINED_RELEVANCE_CHARS
        or len(specific_words) >= STRONG_LATIN_RELEVANCE_WORD_COUNT
    )


def relevance_weight(term: str) -> float:
    if any(ord(char) > ASCII_MAX_CODEPOINT for char in term):
        return 1.0
    words = re.findall(r"[a-z0-9]+", term.casefold())
    specific_words = [word for word in words if word not in GENERIC_RELEVANCE_TERMS]
    if len(specific_words) >= STRONG_LATIN_RELEVANCE_WORD_COUNT:
        return 1.0
    if specific_words and len(specific_words[0]) >= MEDIUM_LATIN_RELEVANCE_WORD_CHARS:
        return 0.75
    return 0.5


def compact_relevance_text(text: str) -> str:
    return re.sub(
        r"[\W_]+", "", text.translate(CJK_NORMALIZATION_TABLE), flags=re.UNICODE
    ).casefold()


def skip_reason_for_posts(
    text_usable: list[dict[str, Any]],
    authentic_posts: list[dict[str, Any]],
    relevant_text_posts: list[dict[str, Any]],
    final_posts: list[dict[str, Any]],
) -> str | None:
    if final_posts:
        return None
    if relevant_text_posts:
        return "no_content_images"
    if authentic_posts:
        return "no_relevant_authentic_posts"
    if text_usable:
        return "no_usable_authentic_posts"
    return "no_usable_authentic_posts"


def pipeline_diagnostics(
    *,
    raw_posts: list[dict[str, Any]],
    text_usable: list[dict[str, Any]],
    image_usable: list[dict[str, Any]],
    authentic_posts: list[dict[str, Any]],
    relevant_text_posts: list[dict[str, Any]],
    final_posts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "raw_samples": preview_posts(raw_posts),
        "text_usable_samples": preview_posts(text_usable),
        "image_usable_samples": preview_posts(image_usable),
        "authentic_samples": preview_posts(authentic_posts),
        "relevant_text_samples": preview_posts(relevant_text_posts),
        "final_samples": preview_posts(final_posts),
    }


def clean_candidate_name(raw: str) -> str:
    text = re.sub(PAREN_CHARS_RE, " ", raw)
    text = re.sub(
        r"\b(?:area|site|location|grounds|day trip|temple grounds)\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    return " ".join(text.split()).strip(" -_/,&")


def query_destination(query: str) -> str:
    raw = query.split(" ", 1)[0].strip()
    aliases = DESTINATION_NAME_ALIASES.get(raw)
    return aliases[0] if aliases else raw


async def mirror_cached_payload(
    original_query: str, fetched_query: str, result: dict[str, Any]
) -> None:
    key = result.get("key")
    if not isinstance(key, str) or not key:
        return
    fetched_key = xhs_cache_key(fetched_query)
    if key != fetched_key:
        return
    from plus_one.core.tools._cache_db import get_cached  # noqa: PLC0415

    payload = await get_cached("xhs", fetched_key)
    if payload:
        await put_cached("xhs", xhs_cache_key(original_query), payload)


def query_intent(query: str) -> str:
    for item in QUERY_INTENTS:
        if item in query:
            return item
    return "真实体验"


def fallback_query_intents(intent: str) -> list[str]:
    grounded = [intent]
    if "拉面" in intent or "拉麵" in intent:
        for extra in ("拉面店推荐", "排队拉面", "真实体验", "本地人推荐", "值得吃吗"):
            if extra not in grounded:
                grounded.append(extra)
        return grounded
    for extra in ("真实体验", "本地人推荐"):
        if extra not in grounded:
            grounded.append(extra)
    return grounded


def usable_posts(posts: list[dict[str, Any]], *, require_images: bool) -> list[dict[str, Any]]:
    usable = []
    for post in annotate_xhs_posts(posts):
        title = str(post.get("title") or "").strip()
        body = str(post.get("body") or "").strip()
        url = str(post.get("url") or "")
        images = post.get("images") or []
        if require_images and not images:
            continue
        if "xiaohongshu.com" in url and title and (body or images):
            usable.append(post)
    return usable


def preview_post(post: dict[str, Any] | None) -> dict[str, Any] | None:
    if not post:
        return None
    return {
        "id": post.get("id"),
        "title": str(post.get("title") or "")[:120],
        "body": str(post.get("body") or "")[:180],
        "url": post.get("url"),
        "image_count": len(post.get("images") or []),
    }


def preview_posts(posts: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    return [preview for post in posts[:limit] if (preview := preview_post(post))]


def load_query_items(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError(f"query file missing items list: {path}")
    return [item for item in items if isinstance(item, dict) and item.get("queries")]


def seed_mvp_query_file(args: argparse.Namespace) -> None:
    base_items = load_seed_base_items(args.input_file)
    payload = build_mvp_seed_payload(base_items)
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    printable = {
        "status": "mvp_xhs_seed_written",
        "input_file": str(args.input_file),
        "output_file": str(args.output_file),
        "candidate_count": payload["candidate_count"],
        "query_count": payload["query_count"],
        "target_city_count": len(MVP_XHS_TARGET_CITIES),
        "by_destination": payload["by_destination"],
    }
    print(json.dumps(printable, ensure_ascii=False))


def load_seed_base_items(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError(f"query file missing items list: {path}")
    return [item for item in items if isinstance(item, dict)]


def build_mvp_seed_payload(base_items: list[dict[str, Any]]) -> dict[str, Any]:
    merged_items = merge_mvp_seed_items(base_items, MVP_XHS_QUERY_ITEMS)
    enriched_items = [enrich_query_item_for_gaps(item) for item in merged_items]
    return query_payload(enriched_items)


def merge_mvp_seed_items(
    base_items: list[dict[str, Any]],
    seed_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in [*base_items, *seed_items]:
        key = query_item_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(normalise_query_item(item))
    return merged


def query_item_key(item: dict[str, Any]) -> str:
    candidate = compact_relevance_text(str(item.get("candidate") or ""))
    destinations = item.get("destinations") or []
    destination = compact_relevance_text(str(destinations[0] if destinations else ""))
    if not candidate:
        return ""
    return f"{destination}:{candidate}"


def normalise_query_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate": str(item.get("candidate") or "").strip(),
        "category": str(item.get("category") or "generic").strip() or "generic",
        "destinations": [
            str(destination) for destination in item.get("destinations") or [] if destination
        ],
        "aliases": [str(alias) for alias in item.get("aliases") or [] if alias],
        "queries": [str(query) for query in item.get("queries") or [] if query],
    }


def query_payload(items: list[dict[str, Any]]) -> dict[str, Any]:
    items = [item for item in items if item.get("candidate") and item.get("queries")]
    return {
        "candidate_count": len(items),
        "query_count": sum(len(item.get("queries") or []) for item in items),
        "by_category": count_by_field(items, "category"),
        "by_destination": count_by_destination(items),
        "target_cities": list(MVP_XHS_TARGET_CITIES),
        "items": items,
    }


def count_by_field(items: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(field) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def count_by_destination(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        destinations = item.get("destinations") or []
        destination = display_destination_label(str(destinations[0] if destinations else "unknown"))
        counts[destination] = counts.get(destination, 0) + 1
    return dict(sorted(counts.items()))


def display_destination_label(destination: str) -> str:
    aliases = destination_aliases_for_query(destination)
    for alias in aliases:
        if alias and not alias.isascii():
            return alias
    return destination.strip() or "unknown"


def empty_report(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "started_at": now_iso(),
        "settings": {
            "limit_candidates": args.limit_candidates,
            "queries_per_candidate": args.queries_per_candidate,
            "post_limit": args.post_limit,
            "images_per_post": args.images_per_post,
            "timeout_s": args.timeout_s,
            "call_timeout_s": args.call_timeout_s,
            "max_query_attempts": args.max_query_attempts,
            "min_sleep_s": args.min_sleep_s,
            "max_sleep_s": args.max_sleep_s,
            "skip_preflight": args.skip_preflight,
            "require_images": not args.allow_text_only,
            "public_search": args_public_search(args),
            "public_profile_dir": args_public_profile_dir(args),
            "public_index_only": bool(getattr(args, "public_index_only", False)),
        },
        "results": [],
    }


def load_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"started_at": now_iso(), "settings": {}, "results": []}
    return json.loads(path.read_text(encoding="utf-8"))


def merge_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {"started_at": now_iso(), "settings": {}, "results": []}
    for report in reports:
        if not isinstance(report, dict):
            continue
        if not merged.get("settings") and isinstance(report.get("settings"), dict):
            merged["settings"] = report["settings"]
        results = report.get("results")
        if isinstance(results, list):
            merged["results"].extend(row for row in results if isinstance(row, dict))
    return merged


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def append_local_cache(
    path: Path,
    query: str,
    candidate: str,
    posts: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "source": "xhs",
        "key": xhs_cache_key(query),
        "query": query,
        "candidate": candidate,
        "fetched_at": now_iso(),
        "payload": posts,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
        handle.write("\n")


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def polite_sleep(min_s: float, max_s: float) -> None:
    low = max(0.0, min_s)
    high = max(low, max_s)
    span = high - low
    jitter = secrets.randbelow(10_000) / 10_000 if span else 0.0
    await asyncio.sleep(low + span * jitter)


def resolve_profile_dir(raw: str | None) -> Path:
    value = raw or os.getenv("XHS_PROFILE_DIR") or str(ROOT / ".auth" / "xhs-profile")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def resolve_public_profile_dir(raw: str | None) -> Path:
    value = raw or str(DEFAULT_PUBLIC_BROWSER_PROFILE_DIR)
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def args_public_search(args: argparse.Namespace) -> bool:
    if bool(getattr(args, "public_search", False)):
        return True
    return not xhs_use_configured_session(args)


def xhs_use_configured_session(args: argparse.Namespace | None = None) -> bool:
    if args is not None and bool(getattr(args, "use_configured_session", False)):
        return True
    return os.getenv("XHS_USE_CONFIGURED_SESSION", "0").strip().lower() in {"1", "true", "yes"}


def args_public_profile_dir(args: argparse.Namespace) -> str | None:
    value = str(getattr(args, "public_profile_dir", "") or "").strip()
    return value or None


def xhs_profile_dir(
    *, public_search: bool = False, public_profile_dir: str | None = None
) -> str | None:
    if public_search:
        if public_profile_dir:
            return str(resolve_public_profile_dir(public_profile_dir))
        return None
    value = os.getenv("XHS_PROFILE_DIR")
    if not value:
        return None
    return str(resolve_profile_dir(value))


def xhs_storage_state_path(*, public_search: bool = False) -> str | None:
    if public_search or xhs_profile_dir(public_search=public_search):
        return None
    value = os.getenv("XHS_STORAGE_STATE")
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return str(path.resolve())


def xhs_cookie(*, public_search: bool = False) -> str | None:
    if (
        public_search
        or xhs_profile_dir(public_search=public_search)
        or xhs_storage_state_path(public_search=public_search)
    ):
        return None
    return os.getenv("XHS_COOKIE") or None


def is_gate_error(error: str) -> bool:
    lowered = error.lower()
    return any(marker.lower() in lowered for marker in GATE_MARKERS)


def print_search_gate_hint() -> None:
    print(
        json.dumps(
            {
                "status": "xhs_search_gate",
                "next_command": "uv run python -m plus_one.scripts.xhs_prewarm run --resume",
                "diagnose_command": "uv run python -m plus_one.scripts.xhs_prewarm diagnose-search",
                "message": (
                    "XHS search is currently blocked by a public search gate or safety check. "
                    "Inspect the browser session if needed, then rerun prewarm with --resume."
                ),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
