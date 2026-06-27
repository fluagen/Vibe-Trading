---
name: a-stock-data
category: data-source
description: A股全栈数据工具包 — 7层架构(行情/研报/信号/资金面/新闻/基础数据/公告)，28端点覆盖13数据源，零API Key(mootdx/腾讯/东财/同花顺/百度/新浪/巨潮)。与Vibe-Trading现有mootdx/eastmoney/tushare/akshare技能互补，含估值公式(PEG/PE消化)和完整调研流程。基于 simonlin1212/a-stock-data (Apache 2.0, 4900+ stars)。
---

# A股全栈数据工具包

七层数据架构，28 个端点覆盖主板/中小板/科创板/ST。本项目基于开源项目 [simonlin1212/a-stock-data](https://github.com/simonlin1212/a-stock-data) (V3.2.3, Apache 2.0, ~4900 stars) 改编为 Vibe-Trading 技能。

> **核心原则：能用通达信(mootdx)/腾讯就别用东财。** mootdx 走 TCP 7709 二进制协议，腾讯财经走 HTTP，两者实测不封 IP。东财仅用于其独有且别处拿不到的数据，所有东财请求已在 Vibe-Trading 内置限流层保护。

```
行情层（实时，不封IP）
├── mootdx        → K线 + 五档盘口 + 逐笔成交 (TCP 7709)
├── 腾讯财经 API   → PE/PB/市值/换手率/涨跌停/指数/ETF (HTTP)
└── 百度股市通     → K线带MA5/10/20 (HTTP)

研报层
├── 东财 reportapi → 个股研报 + 行业研报 + PDF下载 + 评级 + 三年EPS
├── 同花顺 THS     → 一致预期EPS (直连 basic.10jqka.com.cn)
└── iwencai        → NL语义搜索研报 (唯一能力，需API Key)

信号层
├── 同花顺热点     → 当日强势股 + 题材归因 reason tags (零鉴权 73ms)
├── 同花顺北向     → hgt/sgt 分钟资金流向 + 本地自缓存历史
├── 东财 slist     → 个股所属板块/概念归属
├── 东财 push2     → 个股资金流向 分钟级
├── 龙虎榜席位     → 上榜记录 + 买卖席位 TOP5 + 机构动向
├── 全市场龙虎榜   → 每日全市场上榜股票 + 净买额排名
├── 限售解禁日历   → 历史解禁 + 未来90天待解禁
└── 行业板块排名   → 东财行业涨跌/上涨下跌家数

资金面 / 筹码层
├── 融资融券明细   → 日级融资余额/买入/偿还 + 融券
├── 大宗交易       → 成交价/量 + 买卖方营业部
├── 股东户数变化   → 季度股东户数 + 环比变化
├── 分红送转       → 历史每股派息/送股/转增
└── 个股资金流120日 → 主力/大单/中单/小单 日级净流入

新闻层
├── 东财个股新闻   → 个股相关新闻 (search-api-web JSONP)
└── 东财全球资讯   → 7×24 财经快讯 (np-weblist)

基础数据层
├── mootdx finance → 季报快照 (37字段, EPS/ROE/净利)
├── mootdx F10     → 公司资料 (9大类文本)
├── 东财个股信息   → 行业/总股本/流通股/市值/上市日期
└── 新浪财报三表   → 资产负债表/利润表/现金流量表

公告层
├── 巨潮 cninfo    → 公告全文检索+下载
└── mootdx F10     → 最新公告摘要
```

---

## 激活条件

以下场景自动激活本技能：
- A 股个股估值（一致预期 / PE / PEG / PE消化）
- 实时行情（价格 / 五档盘口 / K线 / 涨跌停价）
- 研报搜索（按主题 / 按标的 / 按行业 / 下载PDF）
- **当日强势股 / 题材归因 / 概念热点**
- **北向资金动向**（沪股通/深股通分钟流向）
- **概念板块归属**（行业/概念/地域）
- **个股资金流向**（主力/散户/超大单/大单分钟级）
- **龙虎榜席位**（营业部 + 机构买卖）
- **全市场龙虎榜**（当日所有上榜股票 + 净买额排名）
- **限售解禁日历**（历史解禁 + 未来待解禁）
- **行业横向对比**（涨跌排名 / 资金流入 / 领涨股）
- **融资融券 / 两融数据**（融资余额 + 融券余额）
- **大宗交易**（成交价/量 + 买卖方营业部）
- **股东户数变化**（筹码集中度）
- **分红送转历史**（每股派息 + 送股 + 转增）
- 指数/ETF行情、新闻资讯、公告全文检索、产业链调研、批量横向对比
- 关键词：估值、一致预期、市盈率、PEG、市值、研报、产业链、强势股、题材、热点、北向资金、龙虎榜、席位、解禁、融资融券、大宗交易、股东户数、筹码集中、分红、指数、ETF

---

## 环境准备

```bash
pip install mootdx requests pandas stockstats
```

| 依赖 | 用途 |
|------|------|
| mootdx >= 0.10 | TCP行情+财务+F10（唯一非HTTP依赖） |
| requests | 所有HTTP API直连 |
| pandas | 数据处理+HTML表格解析 |
| stockstats | 技术指标计算 |

> 仅 iwencai 语义搜索需要 API Key（`IWENCAI_API_KEY` 环境变量）。其余12个数据源全部免费零 key。

---

## Vibe-Trading 覆盖映射

本技能与 Vibe-Trading 现有技能/工具/loader 的关系：

| 数据层 | a-stock-data 端点 | Vibe-Trading 内置覆盖 | 何时用本技能直接代码 |
|--------|-------------------|----------------------|---------------------|
| 行情 | mootdx K线/盘口 | `mootdx` 技能 + `mootdx_loader` | 内置覆盖完整，优先走内置 |
| 行情 | 腾讯财经 PE/PB/市值 | `tencent_loader`（无独立技能）| 直接使用本技能代码模式 |
| 行情 | 百度股市通 K线+MA | **无内置覆盖** | 使用本技能代码模式 |
| 研报 | 东财研报列表/PDF | `eastmoney` 技能 `get_research_reports` | 优先走内置工具 |
| 研报 | 同花顺一致预期EPS | **无内置覆盖** | 使用本技能代码模式 |
| 研报 | iwencai NL语义搜索 | **无内置覆盖** | 使用本技能代码模式 |
| 信号 | 同花顺热点题材归因 | **无内置覆盖** | 使用本技能代码模式 |
| 信号 | 同花顺北向资金 | **无内置覆盖** | 使用本技能代码模式 |
| 信号 | 概念板块归属 | `eastmoney` 技能 `get_sector_info` | 优先走内置工具 |
| 信号 | 个股资金流分钟级 | `eastmoney` 技能 `get_fund_flow` | 优先走内置工具 |
| 信号 | 龙虎榜 | `eastmoney` 技能 `get_dragon_tiger` | 优先走内置工具 |
| 信号 | 限售解禁 | `eastmoney` 技能 `get_lockup_expiry` | 优先走内置工具 |
| 信号 | 行业板块排名 | `eastmoney` 技能 `get_sector_info` | 优先走内置工具 |
| 资金面 | 融资融券 | `eastmoney` 技能 `get_margin_trading` | 优先走内置工具 |
| 资金面 | 大宗交易 | `eastmoney` 技能 `get_block_trades` | 优先走内置工具 |
| 资金面 | 股东户数 | `eastmoney` 技能 `get_shareholder_count` | 优先走内置工具 |
| 资金面 | 分红送转 | 无独立工具 | 使用本技能代码模式 |
| 资金面 | 个股资金流120日 | `eastmoney` 技能 `get_fund_flow` (days=120) | 优先走内置工具 |
| 新闻 | 东财个股/全球新闻 | `eastmoney` 技能 `get_stock_news` | 优先走内置工具 |
| 基础数据 | mootdx 财务快照/F10 | `mootdx` 技能 | 内置覆盖完整 |
| 基础数据 | 新浪财报三表 | **无内置覆盖** | 使用本技能代码模式 |
| 公告 | 巨潮公告 | **无内置覆盖** | 使用本技能代码模式 |

> **原则**：Vibe-Trading 内置工具覆盖的先走内置（享受统一限流/错误处理）。无内置覆盖的（同花顺热点/北向/一致预期、百度K线、iwencai、新浪财报、巨潮公告、分红送转）使用本技能的直接 HTTP 代码模式。

---

## 快速上手（代码模板）

### 行情：腾讯财经（无内置技能，推荐直接用）

```python
import urllib.request

def tencent_quote(codes: list[str]) -> dict:
    """腾讯财经实时行情 — PE/PB/市值/换手率/涨跌停，不封IP。返回 {code: {price,pe_ttm,pb,mcap_yi,...}}"""
    prefix_map = {"6": "sh", "9": "sh", "8": "bj"}
    prefixed = [f"{prefix_map.get(c[0], 'sz')}{c}" for c in codes]
    url = f"https://qt.gtimg.cn/q={','.join(prefixed)}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")
    results = {}
    for line in data.strip().split("\n"):
        if '="' not in line:
            continue
        raw = line.split('="')[1].rstrip('";\n')
        vals = raw.split("~")
        code = vals[2]
        results[code] = {
            "name": vals[1], "price": float(vals[3]), "change_pct": float(vals[32]),
            "pe_ttm": float(vals[39]) if vals[39] else 0, "pb": float(vals[46]) if vals[46] else 0,
            "mcap_yi": float(vals[44]), "turnover_rate": float(vals[38]),
            "high": float(vals[33]), "low": float(vals[34]),
        }
    return results
```

> 字段索引详见 [腾讯财经API](a-stock-data/references/行情层/腾讯财经API.md)

### 研报：同花顺一致预期EPS（独家，无内置覆盖）

```python
import pandas as pd

def ths_eps_forecast(code: str) -> pd.DataFrame:
    """同花顺一致预期EPS。返回 DataFrame，包含预测年度/EPS/机构数。"""
    url = f"https://basic.10jqka.com.cn/{code}/worth.html"
    headers = {"User-Agent": "Mozilla/5.0"}
    tables = pd.read_html(url, header=0, storage_options=headers)
    # 通常第3个table是一致预期数据
    for t in tables:
        if t.shape[1] >= 3 and "预测" in str(t.iloc[0, 0]):
            return t
    return pd.DataFrame()
```

> 详见 [同花顺一致预期EPS](a-stock-data/references/研报层/同花顺一致预期EPS.md)

### 信号：同花顺热点（独家，零鉴权）

```python
import requests

def ths_hot_stocks():
    """当日强势股 + 题材归因，零鉴权 73ms"""
    url = "https://eq.10jqka.com.cn/open/api/v1/hot/hotStock"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=10)
    data = resp.json()
    items = []
    for item in data.get("data", {}).get("stockList", []):
        items.append({
            "code": item.get("code", ""), "name": item.get("name", ""),
            "change_pct": item.get("changePct", 0), "reason": item.get("reasonTags", []),
        })
    return items
```

> 详见 [同花顺热点题材归因](a-stock-data/references/信号层/同花顺热点题材归因.md)

### 信号：同花顺北向资金（独家，零鉴权）

```python
import requests, csv, os

def _hsgt_cache_path():
    return os.path.expanduser("~/.vibe-trading/hsgt_cache.csv")

def ths_hsgt_flow(market: str = "hgt"):
    """北向资金分钟级流向。market: hgt(沪股通)/sgt(深股通)。自动本地缓存历史数据。"""
    url = f"https://hsgt.10jqka.com.cn/dataapi/{market}/getList"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=10)
    items = resp.json().get("data", [])
    # 缓存写入
    cache_path = _hsgt_cache_path()
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "a", newline="") as f:
        writer = csv.writer(f)
        for item in items:
            writer.writerow([item.get("time"), item.get("netIn"), item.get("balance")])
    return items
```

> 详见 [同花顺北向资金](a-stock-data/references/信号层/同花顺北向资金.md)

### 公告：巨潮公告检索（独家，无内置覆盖）

```python
import requests

def cninfo_announcements(code: str, keyword: str = "", page_size: int = 20):
    """巨潮公告全文检索。code=纯6位数字。关键词可选。"""
    import json, re
    # 查 orgId
    org_url = f"https://www.cninfo.com.cn/new/information/getOrgs?stockCode={code}&pageSize=50"
    resp = requests.get(org_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    orgs = resp.json()
    org_id = orgs[0]["orgId"] if orgs else f"gssz000{code}" if code.startswith(("0","3")) else f"gssh0{code}"
    # 搜公告
    url = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
    payload = {"pageNum": 1, "pageSize": page_size, "stock": f"{code},{org_id}", "column": "szse", "tabName": "fulltext", "seDate": ""}
    headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post(url, data=payload, headers=headers, timeout=15)
    return r.json()
```

> 详见 [巨潮公告](a-stock-data/references/公告层/巨潮公告.md)

---

## 估值框架

### 核心公式

```python
import math

def forward_pe(price: float, eps_forecast: float) -> float:
    """前向PE = 当前股价 / 未来年度一致预期EPS"""
    return price / eps_forecast if eps_forecast > 0 else float("inf")

def pe_digestion(current_pe: float, cagr: float, target_pe: float = 30) -> float:
    """当前PE消化到目标PE(30x)需要的年数。cagr = 下一年EPS/当年EPS - 1"""
    if current_pe <= target_pe:
        return 0.0
    if cagr <= 0:
        return float("inf")
    return math.log(current_pe / target_pe) / math.log(1 + cagr)

def calc_peg(pe: float, cagr: float) -> float:
    """PEG = 前向PE / (CAGR * 100)。<1便宜, 1-1.5合理, >1.5贵"""
    return pe / (cagr * 100) if cagr > 0 else float("inf")
```

### 投资框架速查

```
壁垒 → 增速 → PE消化 → PEG校验

1. 有壁垒吗？(tech_moat / capacity_moat) → 没有则排除
2. 增速多少？(CAGR > 30% 才有意义)
3. PE多久消化到30x？(< 2年合理, > 4年太贵)
4. PEG多少？(< 1 便宜, 1-1.5 合理, > 1.5 贵)

30x PE 锚点: A股成长股的合理估值重力线，所有行业统一用30x。
```

---

## 完整调研流程

```python
# 单票完整估值 (30秒)
def full_valuation(code: str) -> dict:
    """组合腾讯行情 + 同花顺一致预期 → 完整估值报告"""
    import urllib.request, math, pandas as pd

    # 1. 腾讯实时行情
    prefix = "sh" if code.startswith(("6","9")) else ("bj" if code.startswith("8") else "sz")
    url = f"https://qt.gtimg.cn/q/{prefix}{code}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    vals = resp.read().decode("gbk").split('"')[1].split("~")
    price, mcap = float(vals[3]), float(vals[44])
    pe_ttm = float(vals[39]) if vals[39] else 0
    pb = float(vals[46]) if vals[46] else 0

    # 2. 同花顺一致预期
    eps_cur = eps_next = analyst_count = None
    try:
        df = ths_eps_forecast(code)
        if not df.empty:
            eps_cur = float(df.iloc[0, 2]) if pd.notna(df.iloc[0, 2]) else None
            eps_next = float(df.iloc[1, 2]) if len(df) > 1 and pd.notna(df.iloc[1, 2]) else None
            analyst_count = int(df.iloc[0, 1]) if pd.notna(df.iloc[0, 1]) else 0
    except Exception:
        pass

    # 3. 估值计算
    pe_fwd = price / eps_cur if eps_cur else float("inf")
    cagr = (eps_next / eps_cur - 1) if (eps_cur and eps_next) else 0
    peg = pe_fwd / (cagr * 100) if cagr > 0 else float("inf")
    digest = math.log(pe_fwd / 30) / math.log(1 + cagr) if pe_fwd > 30 and cagr > 0 else 0

    return {"name": vals[1], "price": price, "mcap_yi": mcap, "pe_ttm": pe_ttm, "pb": pb,
            "eps_cur": eps_cur, "eps_next": eps_next, "pe_fwd": round(pe_fwd, 1) if eps_cur else None,
            "cagr_pct": round(cagr * 100, 0) if cagr else None,
            "peg": round(peg, 2) if peg != float("inf") else None,
            "digest_years": round(digest, 1), "analyst_count": analyst_count}
```

> 完整可运行版见 [scripts/full_valuation.py](a-stock-data/scripts/full_valuation.py)

---

## 数据源优先级

| 优先级 | 数据源 | 协议 | 封IP风险 | 覆盖 |
|--------|--------|------|---------|------|
| **1（首选）** | **mootdx（通达信）** | TCP 7709 | **不封IP** | K线、五档盘口、逐笔成交、财务快照、F10 |
| **2** | **腾讯财经** | HTTP GBK | **不封IP** | 实时价、PE/PB/市值/换手率/涨跌停、指数、ETF |
| 3 | 新浪/巨潮/同花顺 | HTTP | 低 | 财报三表、公告、一致预期/热点 |
| **4（仅独有数据）** | **东财 eastmoney** | HTTP | **有风控** | 研报/龙虎榜/解禁/融资融券/大宗交易/股东户数/分红/资金流 |

### 东财防封铁律

- Vibe-Trading 内置限流：所有东财工具经 `backtest.loaders._http` 共享节流层（`VIBE_TRADING_EASTMONEY_MIN_INTERVAL`，默认 1.0 秒）。
- 直接调用时走统一 helper `em_get()`（串行限流 + 随机抖动 + Keep-Alive 会话复用），详见 [东财防封限流](a-stock-data/references/东财防封限流.md)。
- 风控阈值（社区实测）：每秒 >5 / 并发 ≥10 / 1分钟 ≥200 → 临时封 IP。

---

## FAQ

### Q: 与 Vibe-Trading 现有 mootdx/eastmoney 技能有什么区别？
A: 互补关系。本技能提供 7 层统一架构视图 + Vibe-Trading 未覆盖的独家端点（同花顺热点/北向/一致预期、百度K线、iwencai、新浪财报、巨潮公告、分红送转）。Vibe-Trading 已覆盖的部分（mootdx K线、东财龙虎榜/解禁/融资融券等）优先走内置工具。

### Q: mootdx 和腾讯有什么区别？
A: mootdx = 交易层（价格+盘口+K线），腾讯 = 估值层（PE/PB/市值/换手率/涨跌停价）。两者都不封IP。

### Q: 哪些数据源需要 API Key？
A: 只有 iwencai 需要。mootdx/腾讯/东财/同花顺/百度股市通/新浪/巨潮全部免费无 key。

### Q: 同花顺热点接口需要 cookie 吗？
A: 不需要。仅 User-Agent 即可，零鉴权 73ms 拿到当日强势股。

### Q: 腾讯 API 返回乱码？
A: 编码是 GBK，必须 `decode("gbk")`。

### Q: 腾讯 API 字段 43 是 PB 吗？
A: 不是！43=振幅%，46=PB。网上很多教程写错了。

### Q: 海外服务器 mootdx 超时？
A: mootdx TCP 直连通达信行情服务器，需国内 IP。海外走腾讯财经和百度股市通不受影响。

### Q: 东财 PDF 下载 403？
A: 必须带 `Referer: https://data.eastmoney.com/` header。

---

## 参考文档

- [腾讯财经API](a-stock-data/references/行情层/腾讯财经API.md)
- [百度股市通K线](a-stock-data/references/行情层/百度股市通K线.md)
- [同花顺一致预期EPS](a-stock-data/references/研报层/同花顺一致预期EPS.md)
- [iwencai语义搜索](a-stock-data/references/研报层/iwencai语义搜索.md)
- [同花顺热点题材归因](a-stock-data/references/信号层/同花顺热点题材归因.md)
- [同花顺北向资金](a-stock-data/references/信号层/同花顺北向资金.md)
- [概念板块归属](a-stock-data/references/信号层/概念板块归属.md)
- [限售解禁日历](a-stock-data/references/信号层/限售解禁日历.md)
- [融资融券明细](a-stock-data/references/资金面筹码层/融资融券明细.md)
- [大宗交易](a-stock-data/references/资金面筹码层/大宗交易.md)
- [股东户数变化](a-stock-data/references/资金面筹码层/股东户数变化.md)
- [分红送转](a-stock-data/references/资金面筹码层/分红送转.md)
- [个股资金流120日](a-stock-data/references/资金面筹码层/个股资金流120日.md)
- [新浪财报三表](a-stock-data/references/基础数据层/新浪财报三表.md)
- [巨潮公告](a-stock-data/references/公告层/巨潮公告.md)
- [东财防封限流](a-stock-data/references/东财防封限流.md)

## 脚本示例

- [单票完整估值](a-stock-data/scripts/full_valuation.py)
- [强势股+题材归因](a-stock-data/scripts/hot_stocks_research.py)
- [北向资金监控](a-stock-data/scripts/northbound_flow.py)
- [一致预期研究](a-stock-data/scripts/consensus_research.py)
- [巨潮公告搜索](a-stock-data/scripts/announcement_search.py)
