# 腾讯财经 API — 实时行情

> **Vibe-Trading 内置：** 行情数据（实时价、PE、PB、市值、换手率）已由 Vibe-Trading 的 `get_market_data` 工具覆盖。此端点适用于需要精确控制字段、零鉴权直连、或不受 Vibe-Trading 限流策略约束的批量场景。

## 概览

- **端点：** `https://qt.gtimg.cn/q=<prefixes>`
- **协议：** HTTP GET，GBK 编码
- **分隔符：** `~` 分隔 88 个字段
- **封 IP 风险：** 无（腾讯财经不封 IP）
- **支持标的：** A 股个股、指数（上证/深证/创业板）、ETF

## 参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `sh<code>` | 沪市/科创板（6/9 开头） | `sh688017`, `sh600519` |
| `sz<code>` | 深市（0/3 开头） | `sz002463`, `sz300476` |
| `bj<code>` | 北交所（8 开头） | `bj838402` |
| `sh000001` | 上证指数 | — |
| `sh000300` | 沪深300 | — |
| `sz399006` | 创业板指 | — |
| `sh510050` | 上证50 ETF | — |

## 字段索引速查（实测校准 2026-05-03）

| 索引 | 含义 | 示例 |
|------|------|------|
| 1 | 名称 | 绿的谐波 |
| 3 | 当前价 | 224.12 |
| 4 | 昨收 | 215.01 |
| 5 | 今开 | 214.10 |
| 9-18 | 买一~买五（价+量） | |
| 19-28 | 卖一~卖五（价+量） | |
| 31 | 涨跌额 | 9.11 |
| 32 | 涨跌幅% | 4.24 |
| 33 | 最高 | 229.62 |
| 34 | 最低 | 214.10 |
| 37 | 成交额（万） | 187040 |
| 38 | 换手率% | 4.55 |
| **39** | **PE（TTM）** | 300.45 |
| **43** | **振幅%（不是PB！）** | 7.22 |
| **44** | **总市值（亿）** | 410.88 |
| **45** | **流通市值（亿）** | 410.88 |
| **46** | **PB（市净率）** | 11.51 |
| **47** | **涨停价** | 258.01 |
| **48** | **跌停价** | 172.01 |
| 49 | 量比 | 1.20 |
| **52** | **PE（静）** | 314.76 |

> **踩坑提醒：** 网上很多教程把索引 43 写成 PB，实测是振幅%。PB 在索引 46。

## 代码示例

```python
import urllib.request

def tencent_quote(codes: list[str]) -> dict[str, dict]:
    """
    批量拉取腾讯财经实时行情。
    codes: ["688017", "300476", "002463"]
    也支持指数: ["000001", "000300", "399006"]
    也支持ETF: ["510050", "510300"]
    返回: {code: {name, price, pe_ttm, pb, mcap, ...}}
    """
    prefixed = []
    for c in codes:
        if c.startswith(("6", "9")):
            prefixed.append(f"sh{c}")
        elif c.startswith("8"):
            prefixed.append(f"bj{c}")
        else:
            prefixed.append(f"sz{c}")

    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")

    result = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        code = key[2:]
        result[code] = {
            "name":         vals[1],
            "price":        float(vals[3]) if vals[3] else 0,
            "last_close":   float(vals[4]) if vals[4] else 0,
            "open":         float(vals[5]) if vals[5] else 0,
            "change_amt":   float(vals[31]) if vals[31] else 0,
            "change_pct":   float(vals[32]) if vals[32] else 0,
            "high":         float(vals[33]) if vals[33] else 0,
            "low":          float(vals[34]) if vals[34] else 0,
            "amount_wan":   float(vals[37]) if vals[37] else 0,
            "turnover_pct": float(vals[38]) if vals[38] else 0,
            "pe_ttm":       float(vals[39]) if vals[39] else 0,
            "amplitude_pct":float(vals[43]) if vals[43] else 0,
            "mcap_yi":      float(vals[44]) if vals[44] else 0,
            "float_mcap_yi":float(vals[45]) if vals[45] else 0,
            "pb":           float(vals[46]) if vals[46] else 0,
            "limit_up":     float(vals[47]) if vals[47] else 0,
            "limit_down":   float(vals[48]) if vals[48] else 0,
            "vol_ratio":    float(vals[49]) if vals[49] else 0,
            "pe_static":    float(vals[52]) if vals[52] else 0,
        }
    return result

# 用法: 个股
quotes = tencent_quote(["688017", "300476", "002463"])
for code, q in quotes.items():
    print(f"{q['name']}({code}): {q['price']}元 PE={q['pe_ttm']} PB={q['pb']} 市值={q['mcap_yi']}亿")

# 用法: 指数
index_quotes = tencent_quote(["000001", "000300", "399006"])

# 用法: ETF
etf_quotes = tencent_quote(["510050", "510300"])
```
