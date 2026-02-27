# 🔍 MemeScan — The Rug-Pull Radar

**基于多智能体（Multi-Agent）协作与 Anvil 分叉仿真的实时 Memecoin 安全分析系统。**

---

## 📖 项目概述

MemeScan 是一款面向 Web3 安全领域的智能合约审计工具。  
它能够**实时监听**链上新发行的 Meme 代币，通过在本地 Anvil 沙盒中进行**买卖仿真交易**来检测蜜罐（Honeypot）和高税率代币，并调用大语言模型（LLM）对开源合约代码进行深度审计，最终生成结构化的安全评估报告。

### 🧠 核心理念

> **"不只是告诉你代码有漏洞，更在沙盒中直接实操给你看。"**

MemeScan 独创的 **Rug-Pull 攻防推演系统**，能够在本地分叉网络中模拟"恶意项目方"角色，尝试执行拉黑、改税率、暂停交易等恶意操作，**用物理级证据判定**一个代币是否为资金盘。

### 🎯 解决的问题

| 问题 | MemeScan 方案 |
|------|-------------|
| 新发代币无审计报告 | 实时监控 + 自动审计流水线 |
| 蜜罐骗局难以识别 | Anvil 沙盒买卖仿真，真实模拟交易 |
| 静态审计无法发现隐藏后门 | 攻防推演：提权 Owner 并重放恶意调用 |
| 合约代码阅读门槛高 | LLM 大模型自动分析源码，输出人类可读报告 |
| 单链局限 | 同时支持 Ethereum 和 BSC 双链 |

---

## 🌟 主要功能

### 1. 🤖 多智能体协作架构
系统由 5 个 Agent 协作完成审计任务，各司其职：

| Agent | 职责 |
|-------|------|
| **CoordinatorAgent** | 编排调度，管理审计流水线，决策是否触发深度分析 |
| **ScannerAgent** | 实时监听 DEX 新交易对（PairCreated 事件） |
| **SandboxAgent** | 在 Anvil 分叉网络中执行买卖仿真和攻防推演 |
| **AuditorAgent** | 基于规则引擎 + LLM 进行代码安全评估 |
| **ReporterAgent** | 生成 Markdown 审计报告，支持 AI 问答 |

### 2. 🌐 双链支持
- **Ethereum 主网** — Uniswap V2 新交易对监控
- **BSC（币安智能链）** — PancakeSwap V2 新交易对监控

### 3. 🧪 Anvil 沙盒仿真
- 使用 Foundry 的 Anvil 在本地极速分叉主网
- 模拟真实的买入/卖出交易，精确计算买卖税率和 Gas 消耗
- 动态端口分配，避免并发仿真冲突

### 4. ⚔️ Rug-Pull 攻防推演
- **权限劫持**：通过 `anvil_impersonateAccount` 接管合约 Owner
- **自动化攻击**：尝试 `setBlacklist`、`setTaxFeePercent(99)`、`pauseTrading` 等恶意调用
- **状态验证**：攻击后再次仿真买卖，确认用户是否无法出售
- **实锤判定**：自动标记蜜罐并附带攻击证据

### 5. 🧠 LLM 智能审计
- 通过 Etherscan/BscScan V2 API 获取合约开源代码
- 调用 GLM 大语言模型进行深度代码分析
- 自动识别隐藏增发、黑名单、权限后门等高危漏洞

### 6. 💬 Chat with Contract
- 对最新审计报告提问，LLM 基于源码数据实时回答
- 示例："这个代币为什么有 HONEYPOT 标签？"

### 7. 📡 实时前端仪表盘
- Streamlit 构建的 Web UI，支持无感自动刷新
- 实时日志流：后台扫描进度同步显示在前端
- 双 Tab 报告展示：实时报告 + 历史报告归档

---

## 🏗️ 技术栈

| 类别 | 技术 |
|------|------|
| **编程语言** | Python 3.10+ |
| **Web3 交互** | web3.py (AsyncWeb3, AsyncHTTPProvider) |
| **分叉仿真** | Foundry (Anvil + Cast) |
| **前端** | Streamlit + st_autorefresh |
| **数据模型** | Pydantic V2 + pydantic-settings |
| **数据库** | SQLAlchemy 2.0 + aiosqlite (SQLite) |
| **HTTP 客户端** | httpx (Etherscan API), aiohttp (Web3) |
| **LLM 集成** | OpenAI SDK (兼容 GLM / DeepSeek / GPT) |
| **日志系统** | Loguru |
| **异步框架** | asyncio + threading (后台循环) |
| **区块链浏览器** | Etherscan V2 API / BscScan V2 API |

---

## 🛠️ 安装与运行

### 1. 环境要求

- **Python 3.10+**  
- **Foundry**（包含 Anvil 和 Cast）：[安装 Foundry](https://getfoundry.sh)
  ```bash
  curl -L https://foundry.paradigm.xyz | bash
  foundryup
  ```
- **RPC 节点**：Alchemy / Infura / QuickNode 等（免费版即可）
- **LLM API Key**：七牛云 / 智谱 GLM / OpenAI 等兼容 OpenAI 格式的 API

### 2. 克隆与安装依赖

```bash
git clone https://github.com/Ma0xFly/memescan.git
cd MemeScan
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置环境变量

复制配置模板并编辑：

```bash
cp .env.example .env
```

打开 `.env` 文件，填入以下**必填**配置：

```env
# ── RPC 节点 (必填) ──────────────────────────────────────────
RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_ALCHEMY_KEY
BSC_RPC_URL=https://bsc-dataseed.binance.org/

# ── 区块链浏览器 API Key (推荐填写，用于获取合约源码) ─────────
ETHERSCAN_API_KEY=你的_Etherscan_API_Key
BSCSCAN_API_KEY=你的_BscScan_API_Key

# ── LLM 大模型 (必填，用于智能审计和 Chat) ───────────────────
LLM_API_KEY=你的_LLM_API_Key
LLM_BASE_URL=https://api.qnaigc.com/v1          # 七牛云端点
LLM_MODEL=glm-4.5-air                           # 模型名称
```

> **免费 API Key 获取方式：**
> - Alchemy RPC：[alchemy.com](https://www.alchemy.com/) 注册即获免费 Key
> - Etherscan API：[etherscan.io/myapikey](https://etherscan.io/myapikey) 注册即获免费 Key
> - BscScan API：[bscscan.com/myapikey](https://bscscan.com/myapikey) 注册即获免费 Key

### 4. 启动应用

```bash
streamlit run app.py
```

启动后，打开浏览器访问 `http://localhost:8501` 即可使用。

---

## 🚀 使用指南

### 实时监控模式

1. 在左侧边栏 **"🔎 实时监控"** 下拉选择目标链（Ethereum / BSC）
2. 点击 **▶️ 启动监控**
3. 系统会自动监听链上新交易对，发现新代币后自动执行完整审计流程
4. 结果会实时显示在右侧 **📡 实时报告** 标签页中

### 手动扫描模式

1. 在左侧边栏 **"🎯 手动扫描"** 区域选择目标链
2. 在输入框中粘贴代币合约地址
3. 点击 **🔬 扫描代币**
4. 状态框中会实时滚动显示扫描进度

### � 测试用代币地址

以下代币均已在链上开源验证，适合用来测试系统功能：

**Ethereum 主网：**

| 代币 | 合约地址 | 特点 |
|------|---------|------|
| SHIB | `0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce` | 标准 ERC20，经典 Meme 币 |
| PEPE | `0x6982508145454Ce325dDbE47a25d4ec3d2311933` | 已放弃所有权 (Renounced) |
| FLOKI | `0xcf0C122c6b73ff809C693CE761CAA2fd6A5A0D51` | 含有分红和税率机制 |
| WBTC | `0x2260fac5e5542a773aa44fbcfedf7c193bc2c599` | 可能触发隐藏增发标签 |

**BSC 链：**

| 代币 | 合约地址 | 特点 |
|------|---------|------|
| BabyDoge | `0xc748673057861a797275CD8A068AbB95A902e8de` | 通缩机制 + 自动分红 |
| DOGE (Peg) | `0xbA2aE424d960c26247Dd6c32edC70B295c744C43` | Binance 锚定版 DOGE |

---

## 📁 项目结构

```
MemeScan/
├── app.py                     # �️ Streamlit 前端入口
│
├── agents/                    # 🤖 Multi-Agent 层
│   ├── base.py               # Agent 基类 (run / decide / log)
│   ├── coordinator.py        # 编排调度 Agent
│   ├── scanner.py            # 链上监听 Agent
│   ├── sandbox.py            # Anvil 仿真 + 攻防推演 Agent
│   ├── auditor.py            # 规则引擎 + LLM 审计 Agent
│   └── reporter.py           # 报告生成 + Chat Agent
│
├── services/                  # 🔧 底层服务层
│   ├── monitor.py            # Web3 PairCreated 事件轮询
│   ├── simulator.py          # Anvil/Cast 仿真引擎
│   ├── analyzer.py           # 规则引擎分析器
│   ├── etherscan.py          # Etherscan/BscScan V2 API 客户端
│   └── token_info.py         # 代币元数据查询
│
├── core/                      # ⚙️ 基础设施层
│   ├── config.py             # pydantic-settings 配置单例
│   ├── web3_provider.py      # AsyncWeb3 Provider 工厂
│   ├── logging.py            # Loguru 日志配置
│   └── db.py                 # SQLAlchemy 异步数据库引擎
│
├── domain/                    # 📦 领域模型层
│   └── models.py             # Token, SimulationResult, AuditReport
│
├── reports/                   # 📄 审计报告存储 (Markdown)
├── .env.example               # 环境变量配置模板
├── requirements.txt           # Python 依赖列表
└── README.md                  # 本文档
```

---

## 🔮 系统架构

```
┌──────────────────────────────────────────────────────────┐
│                    Streamlit Frontend                     │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌────────┐  │
│  │ 状态面板  │  │ 实时报告  │  │ 历史报告   │  │ AI Chat│  │
│  └──────────┘  └──────────┘  └───────────┘  └────────┘  │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│              CoordinatorAgent (编排调度)                   │
│         ┌────────────┼────────────┐                      │
│         ▼            ▼            ▼                      │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐                │
│  │ Sandbox │  │ Auditor  │  │ Reporter │                │
│  │  Agent  │  │  Agent   │  │  Agent   │                │
│  └────┬────┘  └────┬─────┘  └──────────┘                │
│       │            │                                     │
│       ▼            ▼                                     │
│ ┌──────────┐ ┌───────────┐ ┌──────────┐                 │
│ │Simulator │ │ Analyzer  │ │Etherscan │                  │
│ │ Service  │ │  Service  │ │ Service  │                  │
│ │(Anvil)   │ │(Rules)    │ │(V2 API)  │                  │
│ └──────────┘ └───────────┘ └──────────┘                  │
└──────────────────────────────────────────────────────────┘
```

---

## 🔐 安全与隐私

- 前端日志自动脱敏，不会泄露 RPC Key 和本地路径
- 所有仿真交易均在本地 Anvil 分叉网络中执行，**不会**发送任何真实链上交易
- 敏感配置通过 `.env` 文件管理，已加入 `.gitignore`

---

## 📊 部署说明

### 本地开发部署

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 安装 Foundry
curl -L https://foundry.paradigm.xyz | bash && foundryup

# 3. 配置 .env
cp .env.example .env   # 编辑填入你的 API Key

# 4. 启动
python3 -m streamlit run app.py
```

### 生产部署建议

- 使用 **systemd** 或 **Docker** 保持服务常驻
- 配置 **Nginx** 反向代理 Streamlit 的 8501 端口
- 推荐使用付费 RPC 节点以获得更高频率的轮询支持
- 定期清理 `reports/` 目录中的历史报告文件

---

## 📜 许可证

本项目采用 [MIT License](https://opensource.org/licenses/MIT) 开源许可证。

```
MIT License

Copyright (c) 2026 MemeScan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
```
