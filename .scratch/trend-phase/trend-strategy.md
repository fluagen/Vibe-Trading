# 趋势判定策略：粘合、发散、排列

> 综合来源: [1.md](1.md) + [ma-sticky.md](ma-sticky.md) + 600498 反向推导

---

## 一、三个核心概念

| 概念 | 定义 | 判定公式 |
|------|------|---------|
| **粘合** | 三条均线纠缠在一起 | `(max−min)/close < 2%` |
| **发散** | 均线间距拉开（非粘合） | `(max−min)/close ≥ 2%` |
| **排列** | 均线的高低顺序 | 多头: MA5>MA10>MA20 / 空头: MA20>MA10>MA5 / 交叉: 其他 |

三个概念的关系：

```
                         ┌─ 多头排列(MA5>MA10>MA20) → 上涨
          ┌─ 发散 ───────┤
          │              ├─ 空头排列(MA20>MA10>MA5) → 下跌
均线状态 ─┤              └─ 交叉排列 → MA20>MA5? 跌:涨
          │
          └─ 粘合(极差比<2%) → 盘整
```

---

## 二、趋势判定规则

```python
# 1. 粘合判定
ma_range = max(MA5, MA10, MA20) - min(MA5, MA10, MA20)
is_sticky = (ma_range / close) < 0.02

# 2. 排列判定
is_bull_align = MA5 > MA10 > MA20   # 多头排列
is_bear_align = MA20 > MA10 > MA5   # 空头排列

# 3. 趋势判定
if is_sticky:
    trend = "盘整"
elif is_bull_align:
    trend = "上涨"          # 发散 + 多头排列
elif is_bear_align:
    trend = "下跌"          # 发散 + 空头排列
elif MA20 > MA5:
    trend = "下跌"          # 发散 + 交叉(偏空)
else:
    trend = "上涨"          # 发散 + 交叉(偏多)
```

### 600498 数据验证

| 排列 | 总天数 | 上涨占比 | 下跌占比 | 盘整占比 |
|------|--------|---------|---------|---------|
| 多头排列 | 76 | **96%** | 0% | 4% |
| 空头排列 | 51 | 0% | **98%** | 2% |
| 交叉排列 | 75 | 37% | 47% | 16% |

> 多头/空头排列几乎 100% 对应上涨/下跌。交叉排列用 MA20 vs MA5 补判。

---

## 三、各趋势状态的操作

### 上涨趋势

特征：发散 + MA5 > MA20（多头排列或偏多交叉）

```
入场（模式 B — 回踩支撑）:
  prev_low ≤ prev_MA20 × 1.02   # 触及 MA20
  AND prev_close > prev_MA20     # 支撑确认
  AND close > open               # 收阳
  → pivot = 回踩日最低价

离场（以 close 为准，优先级递减）:
  close < MA5                    → MA5 止盈
  close < MA10                   → MA10 止盈
  close < MA20 AND close < pivot → 结构性破位
```

### 下跌趋势

特征：发散 + MA20 > MA5（空头排列或偏空交叉）

```
入场（模式 A — 上穿反转）:
  (low < MA20 AND high > MA20)           # 穿越均线
  OR (prev_close < prev_MA20 AND high > MA20)  # 跳空高开
  AND volume > prev_volume               # 放量确认
  → pivot = 建仓日最低价

离场: 同上（MA5/MA10/结构性破位）
```

### 盘整

特征：均线粘合，方向不明

```
操作: 维持当前仓位，不新开仓，等发散后跟随方向
```

---

## 四、趋势转换

```
        上穿MA20+放量          跌破MA20+pivot
  下跌 ──────────────→ 上涨 ──────────────→ 下跌
    ↑                    ↓                    ↑
    └──── 粘合(维持) ────┘                    │
    ↑                                        │
    └──────────── 发散确认方向 ───────────────┘
```

---

## 五、与 1.md 六阶段的关系

| 本策略 | 1.md 对应 | 分工 |
|--------|----------|------|
| 盘整 | ②/⑤ 粘合期 | 过滤噪音 |
| 下跌 | ④⑤⑥ | 趋势定性 |
| 上涨 | ①②⑥ | 趋势定性 |
| — | BIAS/μ/σ 仓位 | 由 1.md 负责量化 |

**分工**: 本策略做趋势方向（定性），1.md 做仓位大小（定量）。

---

## 六、伪代码

```python
def determine_trend(df):
    ma5, ma10, ma20 = df['c'].rolling(5).mean(), ...

    # 粘合
    ma_range = np.max([ma5,ma10,ma20], axis=0) - np.min([ma5,ma10,ma20], axis=0)
    sticky = (ma_range / df['c']) < 0.02

    # 排列
    bull_align = (ma5 > ma10) & (ma10 > ma20)
    bear_align = (ma20 > ma10) & (ma10 > ma5)

    # 趋势
    if sticky:          return '盘整'
    elif bull_align:    return '上涨'
    elif bear_align:    return '下跌'
    elif ma20 > ma5:    return '下跌'
    else:               return '上涨'

def entry_signal(df, trend):
    if trend == '下跌':
        cross = ((low<ma20)&(high>ma20)) | ((prev_c<prev_ma20)&(high>ma20))
        if cross and vol > prev_vol:
            return 'A-反转买入', low         # signal, pivot
    elif trend == '上涨':
        pullback = (prev_low <= prev_ma20*1.02) & (prev_c > prev_ma20) & (c>o)
        if pullback:
            return 'B-支撑买入', prev_low
    return None, None
```
