# ETH 永续合约多周期K线分析

用直连交易所 API 抓取 ETH/USDT 永续合约的 K 线与盘口数据，计算技术指标后生成的自包含 HTML 分析报告。每个 HTML 文件都是独立的，样式、图表、数据全部内联，双击即可在浏览器打开，不依赖任何外部资源。

## 目录结构

```
.
├── ETH永续合约_多周期K线分析.html       # 主报告（最新）
├── ETH永续合约_多周期K线分析_1501.html  # 15:01 快照
├── ETH永续合约_多周期K线分析_1601.html  # 16:01 快照
├── ETH永续合约_多周期K线分析_2301.html  # 23:01 快照
├── analysis/                           # 招标标书相关的文本抽取与生成脚本
│   ├── gen_plans.py                    # 方案生成
│   ├── gen_training_v2.py              # 培训文档生成
│   ├── bid_extract.txt                 # 招标文件抽取的原始文本
│   └── criteria_pages.txt              # 评分标准页文本
├── scripts/                            # 行情抓取与分析脚本
│   ├── check_prices.py                 # ETH/ZEC 现价快查
│   ├── eth_timeline.py                 # 4h/1h 时间线
│   ├── fetch_all.py                    # 全量抓取 -> klines.json
│   ├── compute.py                      # 指标与策略引擎 -> summary.json
│   ├── build_html.py                   # 组装自包含报告
│   └── report_template.html            # 报告模板
├── .trae/rules/project_rules.md        # 项目规则（数据源/风控/输出结构）
└── .trae-html-share-packages/          # HTML 分享包缓存
```

## 行情脚本

```bash
pip install requests
python scripts/check_prices.py
python scripts/eth_timeline.py
# 需要重出报告时：
python scripts/fetch_all.py && python scripts/compute.py && python scripts/build_html.py
```

脚本使用相对路径并自动切换到自身目录，在任意工作目录执行都可以。`klines.json` / `summary.json` 是运行产物，已加入 `.gitignore`。

## 项目约定

数据源、账户风控、输出格式等硬性约定见 [.trae/rules/project_rules.md](.trae/rules/project_rules.md)。该文件随仓库分发，新工作区打开后自动生效。

## 本地运行

需要 Node.js 18 及以上。

```bash
npm install
npm start
```

打开 http://localhost:3000 查看报告首页列表。也可以用任意静态服务器，或者直接双击 HTML 文件。

## 环境变量

无。所有数据在生成 HTML 时已经写死，运行时不需要访问交易所接口。

## 说明

- `analysis/` 下的脚本需要在有网络的环境执行，会直连 Gate.io / 币安 / OKX 拉取行情。
- 报告仅用于技术面复盘，不构成投资建议。
