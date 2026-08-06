# 趋势阶段量化交易策略实现计划

## Context

基于 `.scratch/trend-phase/1.md`（乖离率与斜率对走势各阶段的量化 V2）实现完整的 A 股趋势阶段交易策略。该策略使用 BIAS 乖离率、均线方向和标准差阈值对走势进行六阶段分类，并通过三层优先级风控体系管理仓位。

**目标**：创建可被 backtest runner 直接调用的 SignalEngine 技能包，支持单股独立回测。

## 关键决策

| 决策点 | 选择 |
|--------|------|
| 交易市场 | A股（沪深） |
| 实现范围 | 全部规则（8个章节） |
| 组织方式 | 完整技能包 `agent/src/skills/trend-phase/` |
| 回测模式 | 单股独立回测 |
| 大盘共振过滤 | 不做（跳过沪深300 MA60过滤） |
| 特殊保护规则 | 硬止损（-5%）+ 时间止损（10天），跳过复牌跳空保护 |

## 文件清单

### 1. `agent/src/skills/trend-phase/signal_engine.py` — 主策略文件

**SignalEngine 类签名：**
```python
class SignalEngine:
    def __init__(self, ...所有参数带默认值...):
    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
```

**配置参数（__init__ 全部带默认值）：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ma_short` | 5 | 短期均线周期（MA5） |
| `ma_mid` | 20 | 中期均线周期（MA20） |
| `ma_long` | 60 | 长期均线周期（MA60） |
| `mu_window` | 60 | μ/σ 计算窗口 |
| `mu_update_freq` | 20 | μ/σ 滚动更新频率（交易日） |
| `k_smooth` | 3 | K 斜率平滑周期 |
| `k_lag` | 5 | K 斜率滞后天数 |
| `ma60_dir_lag` | 5 | MA60 方向计算滞后 |
| `ma20_dir_lag` | 3 | MA20 方向计算滞后 |
| `sigma_upper` | 2.0 | 上轨 σ 倍数（μ + 2σ） |
| `sigma_lower` | 1.0 | 中轨 σ 倍数（μ + 1σ） |
| `sigma_extreme` | 2.5 | 极端超跌 σ 倍数 |
| `dynamic_tight` | 1.5 | 动态阈值收紧倍数 |
| `dynamic_wide` | 2.5 | 动态阈值放宽倍数 |
| `sticky_threshold` | 0.015 | 均线粘合阈值（1.5%） |
| `tier2_max_position` | 0.10 | 极端抢反弹最大仓位 |
| `tier2_max_days` | 3 | 极端抢反弹最大持仓天数 |
| `tier2_tp_pct` | 0.05 | 极端抢反弹止盈 |
| `hard_stop_pct` | 0.05 | 硬止损底线 |
| `time_stop_days` | 10 | 时间止损天数 |

**指标计算（在 generate 内部）：**
1. **MA5/MA20/MA60** — `df['close'].rolling(n).mean()`
2. **BIAS** = `(MA5 - MA20) / MA20 * 100`
3. **μ** = BIAS 60日滚动均值，每20日更新一次
4. **σ** = BIAS 60日滚动标准差，每20日更新一次
5. **K 平滑斜率** = `BIAS_ma3 - BIAS_ma3.shift(5)`（先3日均值再差分）
6. **MA60 方向** = `MA60 - MA60.shift(5)` (>0 向上)
7. **MA20 方向** = `MA20 - MA20.shift(3)` (>0 向上)
8. **动态阈值**：计算60日 σ 中位数，极端行情收紧/低迷行情放宽
9. **背离检测**：顶背离（股价新高 BIAS 未新高）、底背离（股价新低 BIAS 未新低）

**核心逻辑流程（每 bar 迭代）：**

```
for each bar i:
    1. 检查硬止损（已持仓，亏损 ≥ 5%）→ -1.0 强制平仓
    2. 检查时间止损（已持仓 ≥ 10天，未触及目标）→ -1.0 强制平仓
    3. 计算动态阈值调整后的 σ 值
    4. 三层优先级判定:
       ├─ Tier 1: MA60↓ 且 BIAS ≥ μ - 2.5σ
       │   → 禁止买入，已有仓位清仓（0%）
       ├─ Tier 2: MA60↓ 且 BIAS < μ - 2.5σ（极端超跌）
       │   → 允许最多10%仓位，3天限制，±5%止盈止损
       └─ Tier 3: MA60↑ → 标准六阶段策略
           ├─ 均线粘合检查（|MA20-MA60|/MA60 < 1.5%）→ 维持当前仓位
           ├─ 趋势-仓位双层引擎:
           │   ├─ MA20↑ → 仓位上限 100%，允许买入
           │   └─ MA20↓ → 仓位上限 50%，禁止新开仓
           ├─ 六阶段判定:
           │   ├─ ① 主升浪: BIAS > μ+2σ, K>0 → 100%
           │   ├─ ② 高位盘整: μ+σ < BIAS < μ+2σ, K转负 → 50%
           │   ├─ ③ 高位筑顶: BIAS < μ+σ, K持续负 → 20%（跌破μ清仓）
           │   └─ ⑥ 低位筑底: BIAS > μ-σ, K转正, MA20转向上 → 50%
           ├─ 背离信号处理:
           │   ├─ 顶背离（MA60↑）→ 允许提前减仓
           │   └─ 底背离（MA60↑）→ 允许提前加仓
           └─ 陷阱识别:
               ├─ ⑥→① 诱多反弹: MA60↓时 BIAS反弹 → Tier 1拦截
               └─ ②→③ 诱空杀跌: MA60↑时 BIAS急跌 → 不割肉，回踩加仓
```

**仓位流转总结：**
- MA60↑ + BIAS > μ+2σ → 1.0 (100%)
- MA60↑ + μ+σ < BIAS < μ+2σ → 0.5 (50%)
- MA60↑ + BIAS < μ+σ → 0.2 (20%)
- MA60↑ + BIAS < μ → 0.0 (清仓)
- MA60↓ + BIAS < μ-2.5σ → 0.1 (10% 限时)
- MA60↓ + BIAS ≥ μ-2.5σ → 0.0 (一票否决)

**信号输出规范：**
- 正值 = 做多仓位比例（0.0, 0.1, 0.2, 0.5, 1.0）
- 0.0 = 空仓
- -1.0 = 强制平仓（已有仓位全部卖出）
- A股不做空，所有负值仅表示平仓

### 2. `agent/src/skills/trend-phase/SKILL.md` — 技能文档

包含：策略概述、核心指标公式、三层优先级逻辑、六阶段判定、仓位管理表、参数说明、使用示例。

### 3. `agent/src/skills/trend-phase/config.example.json` — 示例回测配置

```json
{
  "source": "auto",
  "codes": ["000001.SZ"],
  "start_date": "2019-01-01",
  "end_date": "2024-12-31",
  "interval": "1D",
  "initial_cash": 1000000,
  "engine": "daily"
}
```

## 实现顺序

1. **指标计算函数**（BIAS、μ、σ、K、MA方向、动态阈值、背离检测）
2. **三层优先级框架** + 仓位状态追踪（entry_prices, entry_date, position_size）
3. **Tier 3 六阶段分类** + 趋势-仓位双层引擎
4. **背离信号**（顶背离/底背离的检测与提前触发）
5. **陷阱识别**（诱多反弹、诱空杀跌的量化过滤）
6. **硬止损 + 时间止损**
7. **SKILL.md 文档** 和 `config.example.json`
8. **回测验证**

## 关键设计说明

### 为什么用逐 bar 迭代而不是向量化？
策略需要追踪持仓状态（entry_prices、entry_date、position_size），这些状态依赖前一 bar 的决策结果，类似状态机。参考 `agent/src/skills/up_trend_structure/signal_engine.py` 的模式。向量化计算指标（MA、BIAS、σ 等），逐 bar 判断信号。

### μ 和 σ 的"每20日更新"策略
文档要求每 20 个交易日滚动更新 μ 和 σ。实现方式：在更新日（bar_index % 20 == 0）用当前可见的最近 60 日 BIAS 计算，非更新日沿用上次计算值。初始 warmup 需要至少 60 个 bar。

### 动态阈值自适应
先计算过去 60 日 σ 的中位数，再比较当前 σ：
- 当前 σ > 2×中位数 → 阈值缩至 μ ± 1.5σ
- 当前 σ < 0.5×中位数 → 阈值放宽至 μ ± 2.5σ
- 否则 → 标准 μ ± 2σ

### A股特殊约束
- ChinaAEngine 自动处理 T+1、涨跌停、100股整数倍
- 策略无需也不能做空，负信号 = 平仓
- 信号值直接映射仓位比例（引擎会 L1 归一化，单股时等于实际比例）

## 验证方法

1. **代码检查**：`python -m py_compile agent/src/skills/trend-phase/signal_engine.py`
2. **回测运行**：创建临时 run_dir，copy signal_engine.py + config.json，运行 `python -m backtest.runner <run_dir>`
3. **人工抽样验证**：选取 000001.SZ 某段行情，手动计算 BIAS/μ/σ/K/阶段，对比策略输出
4. **边界测试**：warmup 期（前60 bar 应为 0）、极端行情（σ 极大时的动态阈值）、MA60 拐点
5. **Lint**：`ruff check agent/src/skills/trend-phase/`
