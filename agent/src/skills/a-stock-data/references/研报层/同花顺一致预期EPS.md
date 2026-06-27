# 同花顺一致预期 EPS

> **Vibe-Trading 内置：** 此功能暂无内置工具覆盖。适用于获取机构一致预期 EPS（预测机构数、最小值、均值、最大值），是估值分析（PE 消化、PEG 估算）的关键输入。

## 概览

- **端点：** `https://basic.10jqka.com.cn/new/{code}/worth.html`
- **协议：** HTTP GET，GBK 编码 HTML 页面
- **解析方式：** `pandas.read_html()` 解析 HTML 表格
- **封 IP 风险：** 低
- **鉴权：** 无需 API Key，需正常 UA + Referer

## 参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `code` | 6 位股票代码 | `"688017"`, `"600519"` |

## 返回字段

从 HTML 表格中解析，包含「每股收益」相关列：

| 字段 | 含义 | 说明 |
|------|------|------|
| 年度 | 预测年度 | 如 2026E、2027E、2028E |
| 预测机构数 | 给出预测的机构数量 | **< 3 的要谨慎** |
| **最小值** | 机构预测 EPS 最小值 | — |
| **均值** | **机构一致预期 EPS** | 核心字段 |
| **最大值** | 机构预测 EPS 最大值 | — |

## 代码示例

```python
import requests
import pandas as pd
from io import StringIO

def ths_eps_forecast(code: str) -> pd.DataFrame:
    """
    同花顺机构一致预期EPS。
    直连 basic.10jqka.com.cn，解析HTML表格。
    返回 DataFrame: 年度, 预测机构数, 最小值, 均值, 最大值
    "均值" = 机构一致预期EPS
    """
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://basic.10jqka.com.cn/",
    }
    r = requests.get(url, headers=headers, timeout=15)
    r.encoding = "gbk"
    dfs = pd.read_html(StringIO(r.text))
    # 找含"每股收益"的表格
    for df in dfs:
        cols = [str(c) for c in df.columns]
        if any("每股收益" in c or "均值" in c for c in cols):
            return df
    # fallback: 返回第一个表
    return dfs[0] if dfs else pd.DataFrame()

# 用法
df = ths_eps_forecast("688017")
print(df)
# "预测机构数" < 3 的要谨慎
```
