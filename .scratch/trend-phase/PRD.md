# PRD: 趋势阶段量化交易策略

Status: ready-for-agent

## Problem Statement

交易者需要一个系统化的、量化的 A 股趋势阶段识别和仓位管理策略。传统技术分析依赖主观判断（"看起来像主升浪"），缺乏可回测、可复现的量化标准。该策略通过 BIAS 乖离率、均线方向和标准差阈值，将走势客观分类为六个阶段，配合三层优先级风控体系，实现从"什么时候买、买多少、什么时候卖"的全量化决策。

## Solution

基于 BIAS（MA5 与 MA20 的乖离率）及其统计特征（μ 均值、σ 标准差）和平滑斜率 K，构建包含三层优先级执行体系、六阶段分类、趋势-仓位双层引擎、背离信号处理、陷阱识别、动态阈值自适应和仓位管理的完整交易策略。

策略以 SignalEngine 技能包形态存在，可被 backtest runner 直接调用进行单股 A 股回测。

## User Stories

1. As a 量化策略研究员, I want to 用历史数据回测趋势阶段策略，so that 评估策略在不同市场环境下的表现
2. As a 策略开发者, I want SignalEngine 的所有参数都有默认值并可配置，so that 可以快速调整参数进行优化
3. As a 回测系统使用者, I want 策略输出标准化的信号序列（0.0-1.0），so that backtest runner 可以正确解析并执行交易
4. As a 策略审查者, I want 策略代码遵循项目的 AST 安全约束（无顶层可执行代码、无装饰器、无非字面量默认值），so that 策略可以安全地在 subprocess 中运行
5. As a AI agent 用户, I want 策略附带 SKILL.md 文档，so that AI agent 可以理解策略逻辑并正确调用
6. As a 策略使用者, I want 极端行情（MA60 向下）时策略自动禁止买入，so that 不在熊市中逆势开仓
7. As a 策略使用者, I want 极端超跌时（BIAS 低于 μ−2.5σ）允许 10% 小仓位抢反弹，so that 不错失极端情绪反转机会
8. As a 策略使用者, I want 主升浪阶段（BIAS > μ+2σ）满仓持有直到 K 斜率转负，so that 充分把握趋势行情
9. As a 策略使用者, I want 高位盘整时自动降至 50% 仓位并禁止新开仓，so that 防止诱空洗盘
10. As a 策略使用者, I want 高位筑顶时降至 20% 仓位、跌破均值清仓，so that 保护利润不被大幅回吐
11. As a 策略使用者, I want 背离信号（股价新高但 BIAS 未新高）触发提前减仓，so that 在顶部信号出现时更快反应
12. As a 策略使用者, I want 硬止损（−5%）和时间止损（10 天）自动触发，so that 策略不会陷入深度亏损或长期无效持仓
13. As a 策略使用者, I want 动态阈值根据市场波动率自适应调整，so that 在不同波动环境下保持合理敏感度
14. As a 策略使用者, I want 诱多反弹和诱空杀跌能被量化识别和过滤，so that 减少假信号导致的错误交易
15. As a 回测验证者, I want 策略在 warmup 期（前 60 bar）输出全零信号，so that 避免因数据不足产生错误信号

## Implementation Decisions

### 架构

- 采用 **Hybrid Vectorized + Per-Bar State Machine** 模式：指标计算全部向量化（pandas rolling），仓位决策逐 bar 迭代（需要状态追踪）
- 参考 `up_trend_structure/signal_engine.py` 的状态机模式：逐 bar 追踪 entry_price、entry_bar、bars_held、phase、K streak 等状态
- 参考 `technical-basic/example_signal_engine.py` 的向量化指标计算模式

### 文件结构

- `agent/src/skills/trend-phase/signal_engine.py` — SignalEngine 类（约 350-450 行）
- `agent/src/skills/trend-phase/SKILL.md` — AI agent 技能文档
- `agent/src/skills/trend-phase/config.example.json` — 示例回测配置

### 核心指标

- **BIAS** = (MA5 − MA20) / MA20 × 100%
- **μ** = BIAS 的 60 日滚动均值，每 20 个交易日更新一次（用 mask + ffill 实现冻结）
- **σ** = BIAS 的 60 日滚动标准差，每 20 个交易日更新一次
- **K** = BIAS 3 日均值 − BIAS 3 日均值的 5 日前值（平滑斜率）
- **MA60 方向** = MA60 − MA60.shift(5) > 0
- **MA20 方向** = MA20 − MA20.shift(3) > 0

### 三层优先级执行（逐 bar，从高到低）

| 层级 | 触发条件 | 执行动作 |
|------|---------|---------|
| Tier 1（终极风控） | MA60↓ 且 BIAS ≥ μ−2.5σ | 禁止一切买入，已有仓位清仓 |
| Tier 2（极端抢反弹） | MA60↓ 且 BIAS < μ−2.5σ | 允许 ≤10% 仓位，3 天限制，±5% 止盈止损 |
| Tier 3（标准策略） | MA60↑ | 六阶段 + 趋势-仓位双层引擎 |

Tier 3 内部的趋势-仓位双层引擎：

| MA60 | MA20 | 仓位上限 | 允许操作 |
|------|------|---------|---------|
| ↑ | ↑ | 100% | 满仓买入/持有 |
| ↑ | ↓ | 50% | 仅持有或卖出，禁止新开仓 |

均线粘合（｜MA20−MA60｜/MA60 < 1.5%）时维持当前仓位不变。

### 六阶段判定与仓位（Tier 3 内部）

| 阶段 | BIAS 条件 | K 条件 | 仓位 | 备注 |
|------|----------|-------|------|------|
| ① 主升浪 | > μ+2σ | K>0 | 100% | 持有至 K 转负 |
| ② 高位盘整 | μ+σ ~ μ+2σ | K 由正转负 | 50% | 禁止新开仓 |
| ③ 高位筑顶 | < μ+σ | K 持续为负 | 20% | 跌破 μ 清仓 |
| ④ 主跌浪 | MA60↓ | — | 0% | 被 Tier 1 拦截 |
| ⑤ 低位盘整 | MA60↓ | — | 0% | 被 Tier 1 拦截 |
| ⑥ 低位筑底 | > μ−σ | K 由负转正 | 0→50% | 等 MA20 转向上 |

### 背离信号

- 顶背离（股价新高、BIAS 未新高）→ MA60↑ 时允许提前减仓 100%→50%
- 底背离（股价新低、BIAS 未新低）→ MA60↑ 时允许提前加仓 20%→50%
- MA60↓ 时的底背离 → 仅用于确认 Tier 2 抢反弹机会

### 陷阱识别

- **诱多反弹**：BIAS 从极负反弹 + K 正，但 MA60 仍向下 → Tier 1 拦截。若持 Tier 2 仓位，BIAS 到 μ−0.5σ 且 K 转负时清仓
- **诱空杀跌**：BIAS 从极高急跌 + K 负，但 MA60 仍向上 → 不割肉。等 BIAS 回踩 μ+σ 且 K 转正时加回满仓

### 动态阈值自适应

- 计算 60 日 σ 中位数
- σ > 2×中位数 → 阈值缩至 μ±1.5σ
- σ < 0.5×中位数 → 阈值放宽至 μ±2.5σ
- 否则 → 标准 μ±2σ/μ±1σ

### 执行保护

- **硬止损**：任何持仓亏损 ≥5% → 无条件离场（最高优先级）
- **时间止损**：标准开仓 10 日内未触及目标位 → 第 11 日强制平仓
- **Warmup**：前 60 bar 输出全零信号（滚动窗口数据不足）

### 信号输出约定

- 1.0 / 0.5 / 0.2 / 0.1 / 0.0 = 目标仓位比例
- −1.0 = 强制平仓（硬止损、时间止损）
- A 股不做空，负值仅表示平仓

### 可配置参数（所有带默认值）

MA 周期类：`ma_short=5`, `ma_mid=20`, `ma_long=60`
μ/σ 类：`mu_window=60`, `mu_recalc_days=20`, `sigma_window=60`
K 斜率类：`k_ma_period=3`, `k_lag=5`
MA 方向类：`ma60_dir_lag=5`, `ma20_dir_lag=3`
阈值倍数类：`upper_extreme_sigma=2.0`, `upper_consolidate_sigma=1.0`, `lower_bottoming_sigma=1.0`, `lower_extreme_sigma=2.5`
动态阈值类：`enable_dynamic_threshold=True`, `tighten_sigma_ratio=2.0`, `widen_sigma_ratio=0.5`, `tighten_multiplier=1.5`, `widen_multiplier=2.5`
均线粘合：`sticky_threshold=0.015`
Tier 2 类：`tier2_max_hold_days=3`, `tier2_take_profit_pct=0.05`, `tier2_stop_loss_pct=0.05`
止损类：`hard_stop_loss_pct=0.05`, `enable_time_stop=True`, `time_stop_days=10`
背离类：`enable_divergence=True`, `divergence_lookback=20`, `enable_early_reduce=True`, `enable_early_add=True`
陷阱类：`enable_trap_detection=True`
大盘共振：`market_resonance_enabled=False`（默认关闭），`index_ma60_up: Optional[bool] = None`

## Testing Decisions

### 测试 Seams

1. **回测集成测试**（最高层）：创建 run_dir，运行 `python -m backtest.runner`，验证 runner 加载成功、信号生成无错误、产生 artifacts（equity.csv, trades.csv, metrics.csv）
2. **指标计算测试**（中层）：用合成 OHLCV 数据验证 BIAS、μ、σ、K、MA60/MA20 方向与手工计算一致
3. **仓位逻辑测试**（中层）：同合成数据验证 warmup 期全零、Tier 1 拦截、阶段切换仓位变化
4. **编译检查**（最底层）：`python -m py_compile` 验证语法正确、`ruff check` 验证代码风格

### 好测试的标准

- 只测试外部行为（信号输出值），不测试内部实现细节
- 边界条件：warmup 期、NaN 处理、零 σ、数据不足（<80 bar）
- 参考 `up_trend_structure/` 和 `candlestick/` 的测试模式

### 边界条件

- 数据不足 80 bar → 全部输出 0
- σ = 0 时阈值比较不崩溃
- 均线粘合时维持仓位不变化
- K 在零轴附近振荡时不被误判为阶段切换
- 停牌后首日跳过（gap 检测）

## Out of Scope

- 沪深 300 大盘共振过滤（文档第七条第 4 点）：SignalEngine 默认不启用，保留参数接口供后续扩展
- 复牌/除权跳空保护（文档第七条第 3 点）：跳过，仅实现日期 gap 检测
- 多股组合回测：仅支持单股独立回测
- Strategy Research API 注册（不加入 STRATEGY_MAP）
- 做空逻辑：A 股不允许融券做空，所有负信号仅表示平仓

## Further Notes

- 策略逻辑完全基于 `.scratch/trend-phase/1.md`（乖离率与斜率对走势各阶段的量化 V2）
- A 股引擎（ChinaAEngine）自动处理 T+1、涨跌停、100 股整数倍等市场规则，SignalEngine 无需处理
- μ 和 σ 的"每 20 日更新"通过 `np.where(mask).ffill()` 模式实现，非更新日沿用上次计算值
- 指标计算全向量化（pandas rolling），仅仓位决策逐 bar 迭代，性能足够（日线数据 ~5000 bar 在毫秒级完成）
