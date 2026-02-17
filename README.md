# 🔍 MemeScan — The Rug-Pull Radar

**基于 Anvil 分叉仿真的实时 Memecoin 安全扫描器。**

监控 DEX 交易对创建事件，分叉以太坊主网，仿真买卖交易，并生成包含蜜罐检测和税率分析的结构化审计报告。

## 系统架构

```
接口层 (Interface)    → app.py (Streamlit 仪表盘)
服务层 (Service)      → monitor.py | simulator.py | analyzer.py
领域层 (Domain)       → models.py (Pydantic V2) | db_models.py (SQLAlchemy 2.0)
基础设施层 (Infra)    → config.py | db.py | web3_provider.py | logging.py
```

## 快速开始

### 环境依赖

- **Python 3.11+**
- **Foundry** (Anvil + Cast): [getfoundry.sh](https://getfoundry.sh)
- 以太坊 RPC 端点 (Alchemy / Infura / QuickNode)

### 安装步骤

```bash
# 进入项目目录
cd MemeScan

# 创建虚拟环境
python -m venv .venv && source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 RPC URL 和 API 密钥

# 启动仪表盘
streamlit run app.py
```

## 项目结构

```
MemeScan/
├── app.py                 # Streamlit 入口
├── core/
│   ├── config.py          # pydantic-settings 配置单例
│   ├── db.py              # 异步 SQLAlchemy 引擎
│   ├── web3_provider.py   # AsyncWeb3 Provider
│   └── logging.py         # Loguru 日志配置
├── domain/
│   ├── models.py          # Pydantic V2 领域模型
│   └── db_models.py       # SQLAlchemy ORM 模型
├── services/
│   ├── monitor.py         # PairCreated 事件监听器
│   ├── simulator.py       # Anvil 生命周期 + Cast 执行
│   └── analyzer.py        # 风险分析引擎
└── tests/
    └── ...
```

## 核心功能

- **实时监控**：轮询 Uniswap V2 Factory 的新建交易对事件
- **分叉仿真**：启动 Anvil 分叉以测试买卖交易
- **蜜罐检测**：识别阻止卖出操作的代币
- **税率分析**：测量买入/卖出税率百分比
- **风险评分**：0-100 分制评分，附带分类风险标签
- **Streamlit 仪表盘**：实时 UI，包含指标概览和审计报告

## 技术栈

| 组件 | 技术方案 |
|------|---------|
| 编程语言 | Python 3.11+（严格类型提示） |
| Web3 | web3.py (AsyncHTTPProvider) |
| 仿真引擎 | Foundry (Anvil + Cast) |
| 前端框架 | Streamlit |
| 数据库 | SQLite + SQLAlchemy 2.0 异步 |
| 数据校验 | Pydantic V2 |
| 日志系统 | Loguru |
| 配置管理 | pydantic-settings |

## 许可证

MIT
