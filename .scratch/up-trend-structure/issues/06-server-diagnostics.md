# 06 — 新服务器环境回测数据为空诊断文档

**Status:** ready-for-agent

## Parent

[PRD v2](../PRD.md)

## What to build

新服务器上 `pip install -e ".[dev]"` 后回测个股数据为空是常见问题。需要在 SKILL.md 中添加 Troubleshooting 小节，指导用户快速定位原因。

诊断覆盖四个维度：
1. conda 环境是否存在
2. mootdx 是否已安装
3. 通达信服务器是否连通
4. fallback chain 中是否有可用加载器

诊断命令：

```bash
# 1. conda 环境
conda env list | grep vibe-trading

# 2. mootdx 安装状态
conda run -n vibe-trading python -c "import mootdx; print(mootdx.__version__)"

# 3. 通达信服务器连通性
conda run -n vibe-trading python -c "
from mootdx.quotes import Quotes
c = Quotes.factory(market='std')
df = c.get_k_data(code='000001', start_date='2026-07-15', end_date='2026-07-19')
print('OK:', len(df), 'rows') if df is not None else print('FAILED')
"

# 4. 所有加载器可用状态
conda run -n vibe-trading python -c "
import sys; sys.path.insert(0, 'agent')
from backtest.loaders.registry import _ensure_registered, LOADER_REGISTRY
_ensure_registered()
for name in ['mootdx','baostock','eastmoney','akshare','tushare']:
    cls = LOADER_REGISTRY.get(name)
    if cls is None: print(f'{name}: NOT REGISTERED'); continue
    try:
        inst = cls(); print(f'{name}: {\"OK\" if inst.is_available() else \"N/A\"}')
    except Exception as e: print(f'{name}: ERROR - {e}')
"
```

## Acceptance criteria

- [ ] 诊断命令添加到 SKILL.md 的 Troubleshooting 小节
- [ ] 覆盖四种常见失败原因：环境缺失、mootdx 未安装、网络不通、无可用加载器
- [ ] 每条命令给出正常输出和异常输出的解读说明

## Blocked by

None — can start immediately.
