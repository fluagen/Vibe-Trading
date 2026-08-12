# 节点交易策略 (Node Trading Strategy)

基于均线极差比的五阶段生命周期模型，只在健康趋势期重仓出击的节点交易策略。

## 核心原理

走势遵循 "蓄势 → 萌芽 → 健康趋势 → 加速 → 极端" 五阶段生命周期。核心：只在 S3 健康趋势期重仓，S2 轻仓试错，S4/S5 只卖不买，S1 空仓观望。

## 指标体系

- **极差比 R** = (max(MA5,MA10,MA20) - min) / mean × 100% — 趋势能量
- **变异系数 CV** = std / mean — 发散均匀度
- **极差比斜率 RS** = R / R_5d_ago — 加速速度

## 五阶段判定（自上而下）

| 阶段 | 条件 |
|------|------|
| S5 极端 | R > 9% 且 CV > 0.4 |
| S4 加速 | R > 6% 或 RS ≥ 1.1 |
| S3 健康 | 均线排列 + 4% < R ≤ 6% + RS < 1.1 + CV < 0.3 |
| S2 萌芽 | 均线排列 + 2% < R ≤ 4% |
| S1 蓄势 | 其余情况 |

## 四种节点

| 节点 | 阶段 | 条件 |
|------|------|------|
| 常规反转 | S2, S3 | 上穿MA20 + 放量 |
| 下跌终结 | 下跌阶段 | 上穿MA20 + 显著放量(×1.2) |
| 支撑 | S3 | 回踩MA20收阳 |
| 粘合爆发 | S1 | Close>MA20 + 放量(×1.5) |

## 使用方式

```python
from src.skills.node_trading.signal_engine import SignalEngine
engine = SignalEngine()  # PRD 默认参数
signals = engine.generate({"600498": df})
```

## 单标回测

```bash
python -m src.skills.node_trading.run_backtest --code 600498 --start 2025-10-01
```
