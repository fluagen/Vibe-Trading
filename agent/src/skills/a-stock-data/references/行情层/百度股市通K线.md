# 百度股市通 K线 — 自带 MA5/MA10/MA20

> **Vibe-Trading 内置：** K线数据已由 Vibe-Trading 的 `get_market_data` 工具覆盖（通过 mootdx 通达信 TCP 协议，不封 IP）。此端点适用于需要**返回时自带均线数据**（MA5/MA10/MA20 均价，无需本地计算）的特殊场景。

## 概览

- **端点：** `https://finance.pae.baidu.com/selfselect/getstockquotation`
- **协议：** HTTP GET，JSON 返回
- **核心价值：** 返回时自带 `ma5avgprice`、`ma10avgprice`、`ma20avgprice` 均价字段，无需本地计算均线
- **封 IP 风险：** 低
- **鉴权：** 需带 `Accept: application/vnd.finance-web.v1+json` 和 `Referer` 头

## 参数

| 参数 | 说明 | 取值 |
|------|------|------|
| `all` | 全量数据 | `"1"` |
| `isStock` | 个股模式 | `"true"` |
| `isIndex` | 指数模式 | `"false"` |
| `group` | K线分组 | `"quotation_kline_ab"` |
| `code` | 股票代码 | 如 `"600519"` |
| `ktype` | K线周期 | `"1"`（日K） |
| `start_time` | 起始时间 | `""`（全量）或时间戳 |
| `finClientType` | 客户端类型 | `"pc"` |

## 返回字段

`keys` 数组包含以下关键字段：

| 字段 | 含义 |
|------|------|
| `time` | 日期 |
| `open` | 开盘价 |
| `close` | 收盘价 |
| `high` | 最高价 |
| `low` | 最低价 |
| `volume` | 成交量 |
| `amount` | 成交额 |
| **`ma5avgprice`** | **MA5 均价**（无需本地计算） |
| **`ma10avgprice`** | **MA10 均价** |
| **`ma20avgprice`** | **MA20 均价** |

## 代码示例

```python
import requests

def baidu_kline_with_ma(code: str, start_time: str = "") -> dict:
    """百度股市通K线 — 独有能力: 返回时自带 ma5/ma10/ma20 均价"""
    url = "https://finance.pae.baidu.com/selfselect/getstockquotation"
    params = {
        "all": "1", "isIndex": "false", "isBk": "false", "isBlock": "false",
        "isFutures": "false", "isStock": "true", "newFormat": "1",
        "group": "quotation_kline_ab", "finClientType": "pc",
        "code": code, "start_time": start_time, "ktype": "1",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/vnd.finance-web.v1+json",
        "Origin": "https://gushitong.baidu.com",
        "Referer": "https://gushitong.baidu.com/",
    }
    r = requests.get(url, params=params, headers=headers, timeout=10)
    d = r.json()
    result = d.get("Result", {})
    md = result.get("newMarketData", {})
    keys = md.get("keys", [])       # 包含: ma5avgprice, ma10avgprice, ma20avgprice
    rows = md.get("marketData", "").split(";")
    return {"keys": keys, "rows": rows}

# 用法
data = baidu_kline_with_ma("600519")
print("字段:", data["keys"][:10])
print("最近5根K线:", data["rows"][-5:])
```
