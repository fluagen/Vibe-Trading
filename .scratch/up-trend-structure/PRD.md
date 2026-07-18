# 上涨结构交易策略 v2

**Status:** ready-for-agent | **Updated:** 2026-07-13 | **Author:** fluagen

## 核心设计

策略基于三层架构：**指标**描述K线形态 → **状态机**判断结构阶段 → **信号引擎**输出仓位决策。

### 概念定义

| 概念 | 定义 |
|------|------|
| 价涨量增 | `close > prev_close` AND `volume > prev_volume` |
| 价跌量缩 | `close < prev_close` AND `volume < prev_volume` |
| 量价背离 | `(close↑ AND volume↓)` OR `(volume↑ AND close↓)` |
| 补量（修复） | `close > 触发日close` AND `volume > 触发日volume` |
| 起涨点 | forming bar 的最低价 |
| 止跌K | 三种：① 倒垂：D0阴线→倒锤子(上影≥inv_hammer_shadow_ratio×实体、下影<实体)+最高价>D0中点+放量; ② 反包线：D0阴线→当日收阳+收盘>threshold(默认D0中点)+放量; ③ 两日筑底：D0阴→D1阳(非倒垂、非反包线)→D2阳+放量+C>D0中点，D2为止跌K |
| 证伪K | 止跌K次日，阳线 OR close>止跌K close |
| 上涨结构 | forming → up_phase → pullback → pullback_end 的完整生命周期 |

### 指标体系

策略所有指标均从日线 OHLCV（open/high/low/close/volume）衍生，不依赖外部数据源。分四个层级：

#### 一、K线形态指标

| 指标 | 计算方式 | 用途 |
|------|----------|------|
| **实体 (body)** | `abs(close - open)` | 判断K线阴阳及实体大小 |
| **振幅 (range)** | `high - low` | 当日波动区间 |
| **上影线 (upper_shadow)** | `high - max(open, close)` | 倒锤子线检测 |
| **下影线 (lower_shadow)** | `min(open, close) - low` | 锤子线检测 |
| **前日实体中点 (prev_mid)** | `(prev_open + prev_close) / 2` | 止跌K收盘位判断基准 |

**止跌K（三种形态，优先级：倒垂 > 反包线 > 两日筑底）**：

| 形态 | 条件 |
|------|------|
| **形态一：倒垂** | 前日阴线 + 倒锤子(上影≥`inv_hammer_shadow_ratio`×实体、下影<实体) + 最高价>`prev_mid` + 放量>前日×`volume_surge_ratio` |
| **形态二：反包线** | 前日阴线 + 当日收阳 + 收盘>`prev_close + (prev_open-prev_close)×close_above_prev_mid` + 放量>前日×`volume_surge_ratio` |
| **形态三：两日筑底** | D0阴线 → D1阳线(非倒垂、非反包线) → D2阳线放量+收盘>D0中点，D2为止跌K |

> `prev_mid = (prev_open + prev_close) / 2`，即前日实体中点。倒垂使用 `high > prev_mid`（硬编码），反包线使用 `close > threshold`（受 `close_above_prev_mid` 控制，默认 0.5 时 threshold = prev_mid）。v3 移除 v2 中 D1 放量要求。

**证伪K**：前日止跌K + 当日(收阳 或 close>前日close)

#### 二、量价关系指标

| 指标 | 定义 | 方向信号 |
|------|------|----------|
| **价涨量增 (price_up_volume_up)** | `close > prev_close` AND `volume > prev_volume` | 多头确认，驱动 forming→up_phase |
| **价跌量缩 (price_volume_down)** | `close < prev_close` AND `volume < prev_volume` | 回调信号，在 up_phase 中触发挂起退出 |
| **量价背离 (divergence)** | (价涨量缩) OR (量涨价跌) | 预警信号，在 up_phase 中触发挂起退出 |
| **补量修复 (repair)** | `close > 触发日close` AND `volume > 触发日volume` | 解除挂起，延续 up_phase |

#### 三、均线指标

| 指标 | 计算 | 默认周期 | 用途 |
|------|------|----------|------|
| **MA(short)** | `close.rolling(ma_short).mean()` | 5 | 第二档止盈：收盘跌破 → 减仓一半 |
| **MA(mid)** | `close.rolling(ma_mid).mean()` | 10 | 第三档止盈：收盘跌破 → 全部清仓 |

#### 四、状态机衍生指标

`UpTrendStructure.compute()` 输出 DataFrame 包含以下列：

| 列名 | 类型 | 说明 |
|------|------|------|
| `state` | `str` | 当前状态：`no_structure` / `forming` / `up_phase` / `pullback` / `pullback_end` / `breakdown` |
| `bottom_signal_k` | `bool` | 当日为止跌K |
| `confirm_k` | `bool` | 当日为证伪K |
| `divergence` | `bool` | 当日量价背离 |
| `price_up_volume_up` | `bool` | 当日价涨量增 |
| `price_volume_down` | `bool` | 当日价跌量缩 |
| `pivot_low` | `float` | 当前结构的起涨点最低价（止损基准） |
| `pullback_depth_pct` | `float` | 回调深度百分比 |

### 状态机

6 个状态，14 条转移规则。**pivot_low 仅在进入 `up_phase` 时设置**：`forming → up_phase` 时取 forming bar 的 low，`pullback_end → up_phase` 时取止跌K 的 low。

| 当前状态 | 条件 | 新状态 | 动作 |
|----------|------|--------|------|
| `no_structure` | 价涨量增 | `forming` | 记录 forming_low=当前low |
| `forming` | 价涨量增 | `up_phase` | pivot = forming_low |
| `forming` | 非价涨量增 | `no_structure` | — |
| `up_phase` | 背离 or 价跌量缩 | (挂起) | 记录触发日close/vol |
| `up_phase` | 挂起次日 + 补量成功 | `up_phase` | 延续 |
| `up_phase` | 挂起次日 + 补量失败 | `pullback` | 上涨阶段结束 |
| `up_phase` | 价涨量增 | `up_phase` | 延续 |
| `pullback` | 止跌K | `pullback_end` | 记录 pullback_end_low=止跌K low, pullback_end_close=止跌K close |
| `pullback_end` | 证伪K（条件1：止跌K次日 + 收阳或close>止跌K close） | `up_phase` | pivot = pullback_end_low |
| `pullback_end` | 条件2：持续期间 收阳 + close > pullback_end_close | `up_phase` | pivot = pullback_end_low |
| `pullback_end` | `low < pullback_end_low` | `pullback` | 止跌K 低点被跌破 |
| `pullback_end` | 其他 | `pullback_end` | 继续等待 |
| `*` (除no_structure) | `low < pivot` | `breakdown` | — |
| `breakdown` | 立即 | `no_structure` | — |

### 信号规则

入场仅限 pullback 重启路径。止损/止盈按优先级从高到低依次检查，**命中即执行、不再检查后续条件**。

#### 止损（强制全平，-1.0）

| 优先级 | 条件 | 代码逻辑 | 说明 |
|--------|------|------|------|
| 1 | **跌破 pivot** | `low < pivot_low` | 结构破位，立即清仓 |
| 2 | **浮动亏损超限** | `(close - avg_entry) / avg_entry < -stop_loss_pct` | 默认 -3%，独立于 pivot |
| 3 | **进入 pullback** | `state == pullback` 且 prev 为 `up_phase` | up_phase 中背离/价跌量缩未修复 → 状态转 pullback → 平仓 |

> 止损条件 3 仅适用于从 up_phase 进入 pullback（背离/价跌量缩补量失败）。`pullback_end` 状态不会因"非证伪K"回到 pullback — 只有 `low < pullback_end_low` 才退回 pullback，且不触发此退出。

#### 止盈（阶梯减仓）

| 优先级 | 条件 | 信号值 | 代码逻辑 | 说明 |
|--------|------|--------|------|------|
| 4 | **盈利 ≥ 30%** | `pos/2` | `(close - avg_entry) / avg_entry >= take_profit_pct` | 卖一半，仅触发一次 |
| 5 | **收盘 < MA(short)** | `pos/2` | `close < ma_s` | 短线走弱减半仓，仅触发一次 |
| 6 | **收盘 < MA(mid)** | `-1.0` | `close < ma_m` | 中线破位全清 |

> 止盈为递进关系：先 30% 止盈卖半 → 再破 5MA 卖半 → 最后破 10MA 全平。每档仅触发一次。

#### 入场

| 信号值 | 触发条件 | 说明 |
|--------|------|------|
| 0.33 | 止跌K + `pullback→pullback_end` + 空仓 | 试仓 1/3 |
| 0.67 | 证伪K + `pullback_end→up_phase` + 已有 0.33 | 确认加至 2/3（上限） |

信号值为**仓位目标**：正数 = 目标仓位，`pos/2` = 当前仓位减半，`-1.0` = 清仓。

### 指标 → 状态 → 信号 关系

```
指标                  状态转移               信号
─────────────────────────────────────────────────────
价涨量增 ────→ no_structure → forming
价涨量增(2nd) → forming → up_phase
背离/价跌量缩  → up_phase → pullback ────→ -1.0
  (补量失败)
止跌K ───────→ pullback → pullback_end ──→ 0.33
证伪K ───────→ pullback_end → up_phase ──→ 0.67
pivot_low ───→ breakdown ──────────────→ -1.0
盈利≥30% ─────────────────────────────→ ×0.5
close<MA(5) ───────────────────────────→ ×0.5
close<MA(10) ──────────────────────────→ -1.0
```

## 可调参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `up_phase_min_bars` | 2 | 价涨量增连续天数要求 |
| `volume_surge_ratio` | 1.2 | 止跌K 成交量放大倍数 |
| `inv_hammer_shadow_ratio` | 1.1 | 倒垂线上影/实体倍数（形态一） |
| `big_bull_body_ratio` | 0.6 | 保留参数，当前止跌K未使用，后续可能新增形态 |
| `close_above_prev_mid` | 0.5 | 反包线收盘阈值：`threshold = prev_close + (prev_open-prev_close) × 该值`（形态二），默认 0.5 等价于前日实体中点 |
| `stop_loss_pct` | 0.03 | 无条件止损比例 |
| `take_profit_pct` | 0.30 | 第一档止盈盈利比例 |
| `ma_short` | 5 | 第二档止盈均线周期 |
| `ma_mid` | 10 | 第三档清仓均线周期 |
| `divergence_repair_bars` | 1 | 背离修复窗口（天） |

## Testing

测试策略：只测 external behavior（K线序列 → 状态/信号输出），不测内部实现。

| Level | Seam | 覆盖 |
|-------|------|------|
| 状态机 | 合成OHLCV → `UpTrendStructure.compute()` | 所有转移规则 |
| 信号引擎 | OHLCV + 状态 → `SignalEngine.generate()` | 入场/止盈/止损 |
| 编译 | `py_compile` | 语法 |

关键测试场景：
- 连续2天价涨量增 → forming → up_phase
- 背离 + 补量成功/失败
- pullback → 止跌K → 证伪K → 新up_phase
- 三档止盈级联触发
- 止损优先级

Prior art: `agent/tests/test_up_trend_structure.py`, `agent/tests/test_structure_signal_engine.py`

## Out of Scope

- 多股票组合仓位管理
- `watch_pool_runner.py` / `screen_bottom_k.py` 适配
- 前端 UI 变更

## 总结
该策略是一个纯量价+均线的状态机策略，不依赖任何宏观/基本面/资金流指标。 核心逻辑是把价格行为归纳为"无结构→形成→上涨→回调→回调结束"的状态流转，通过 止跌K 和 证伪K 触发入场，通过 pivot 止损和三档阶梯止盈（30%利润、MA5、MA10）来管理出场。