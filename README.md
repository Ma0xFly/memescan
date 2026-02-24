# 🔍 MemeScan V2 — The Rug-Pull Radar (Multi-Agent System)

**基于多智能体协作与 Anvil 分叉仿真的实时 Memecoin 安全分析系统。**

MemeScan V2 已经从单向的工具流水线，升级为了具有自主决策能力的 Multi-Agent 系统。系统支持 Ethereum 主网和 BSC 双链实时监控，并深度集成了大语言模型（LLM）提供智能合约源码审计和交互式分析。

---

## 🌟 V2 核心亮点

- **🤖 多智能体架构**: Coordinator 统一调度，Scanner 负责监控，Sandbox 执行仿真，Auditor 深度分析代码，Reporter 出具报告。
- **🌐 双链支持**: 一键切换 Ethereum (Uniswap V2) 和 BSC (PancakeSwap V2) 的监控与扫描。
- **🧠 智能审计 (LLM)**: 集成七牛云 / 智谱 GLM API。Auditor Agent 可自主获取合约源码喂给大模型分析，揪出隐藏黑名单、增发漏洞。
- **💬 Chat with Contract**: 直接在前端对刚生成的审计报告提问，AI 帮你解答代码风险。
- **🔒 并发防爆锁**: Sandbox 引入进程级协程锁，完美解决并发扫币时的 Anvil 端口冲突问题。
- **⚡ 无缝刷新**: 大盘采用无感刷新技术 (`st_autorefresh`)，后台跑日志，前台不闪烁。
- **⚔️ 攻防演练 (Rug-Pull Replay)**: 突破静态审计局限，基于 Anvil 强大的分叉重放能力，在本地沙盒中扮演“黑客/项目方”角色。直接提权并模拟恶意的提款、增发和拉黑操作，通过动态推演让高级貔貅盘无所遁形。

---

## 🔮 深度解密：可视化“跑路”沙盘推演实现原理

MemeScan V2 不仅仅是“告诉你”代码有漏洞，更是要在本地沙盒中直接“实操”给你看，从而彻底打破复杂貔貅盘（Honeypot）在常规条件下的隐蔽性。其核心基于以下多智能体协同流水线实现：

### 1. 权限劫持与账户伪装 (Impersonation)
- **底层原理**: 依赖 Foundry/Anvil 节点引擎的 `anvil_impersonateAccount` 特权 RPC 接口。
- **Agent 动作**: Sandbox Agent 在本地极速分叉网络（Forked Network）中，**无需提供任何真实私钥**，即可在 EVM 层面强制接管代币合约的 Owner、Deployer 或特权管理员地址，获取最高控制权。

### 2. 自动化恶意提权与攻击向量生成 (Attack Vectors)
- **底层原理**: 结合大模型 (LLM) 静态代码分析与 ABI 编码技术。
- **Agent 动作**: Auditor Agent 初步阅读源码后，若发现诸如 `setTax()`, `pauseTrading()`, `blacklist(address)`, 或隐藏的 `mint()` 函数，会将其提取入“高危函数白名单”。Sandbox Agent 随后根据此名单生成模拟 Payload，自动扮演“准备跑路的邪恶项目方”发起链上调用。

### 3. 交易后置状态断言 (State Verification)
- **底层原理**: 针对 EVM 状态树的实盘交叉比对。
- **Agent 动作**: 当“模拟跑路”交易（如改税率、撤池子）上链后，系统自动再次发起基准的买入/卖出仿真测试。一旦探测到：买入税率突变为 99%、模拟买家因被拉黑导致 `transfer` 报 revert、或流动性池资金归零，系统便获得了“确系资金盘”的物理级实锤证据。

### 4. 前端动态推演时间线 (UI Timeline)
- **底层原理**: Streamlit 实时状态共享（`st_autorefresh` 与模块级共享内存）。
- **界面展示**: 将后台隐晦的节点日志解构重组为极具视觉冲击力的时间线。用户在大盘上可直观看到演练全过程：
  > *“✅ [成功] 锁定 Owner 权限 ➡️ 😈 [执行] 尝试调用 setTaxFee(99, 99) ➡️ 🔴 [实锤] 用户已无法卖出筹码 ➡️ 🚨 判定为蜜罐！”* 
  
  为 Web3 安全分析提供无可辩驳、一目了然的安全预警体验。

---

## 🛠️ 安装与配置

### 1. 环境依赖

- **Python 3.11+**
- **Foundry** (Anvil + Cast): 用于本地极速分叉仿真 [getfoundry.sh](https://getfoundry.sh)
- **Node RPC**: 以太坊和 BSC 的 RPC（免费版即可）
- **LLM API Key**: 推荐七牛云（兼容 OpenAI 格式）或智谱直连

### 2. 克隆与安装

```bash
cd MemeScan
python3 -m venv .venv 
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置 .env

复制配置模板：
```bash
cp .env.example .env
```
编辑 `.env` 文件，填入核心配置：

```env
# ── RPC 节点配置 ──
RPC_URL=你的以太坊_RPC_地址 (如 Alchemy/Infura)
BSC_RPC_URL=https://bsc-dataseed.binance.org/

# ── 浏览器 API (获取源码用) ──
ETHERSCAN_API_KEY=你的Etherscan_Key
BSCSCAN_API_KEY=你的BscScan_Key

# ── LLM 配置 (七牛云或智谱) ──
LLM_API_KEY=你的七牛云_API_KEY
LLM_BASE_URL=https://api.qnaigc.com/v1     # 七牛云端点
LLM_MODEL=glm-4.5-air                      # 使用的模型
```

---

## 🚀 使用指南

启动 Streamlit 仪表盘：

```bash
streamlit run app.py
```

打开浏览器访问 `http://localhost:8501`。

### 1. ⚙️ 侧边栏及配置面板
- **RPC 连接状态**: 系统启动时会自动检测你所选链（Ethereum 或 BSC）的 RPC 连通性，并显示连接状态。
- **🔎 实时监控 (Auto-Scan)**:
  - 在下拉菜单选择目标链（Ethereum 或 BSC）。
  - 点击 **▶️ 启动监控**。系统会在后台使用 asyncio 并发监听 DEX (Uniswap V2 / PancakeSwap V2) 的 `PairCreated` 新交易对事件。当探测到新币时，自动执行“沙盒买卖仿真 ➡️ 代码大模型审计”全流程。
- **🎯 手动扫描 (Manual Scan)**:
  - 输入任何已发行的代币合约地址即可强制对其进行深度审计。
  - **进度可视化**: 点击扫描后，下方会出现实时滚动的日志框，将后台 Agent 的动作（如分叉节点、买单/卖单模拟、触发规则、调用 LLM）零延迟同步到前端展示。

> 💡 **手动扫描测试地址（带开源验证合约的经典 Meme 币）**
> 
> **Ethereum 链测试币:**
> - **SHIB (Shiba Inu)**: `0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce` (经典狗狗币)
> - **PEPE**: `0x6982508145454Ce325dDbE47a25d4ec3d2311933` (代码已完全放弃所有权)
> - **FLOKI**: `0xcf0C122c6b73ff809C693CE761CAA2fd6A5A0D51` (带有复杂分红/税率机制)
> - **WBTC**: `0x2260fac5e5542a773aa44fbcfedf7c193bc2c599` (可能触发隐藏增发标签)
>
> **BSC 链测试币:**
> - **BabyDoge**: `0xc748673057861a797275CD8A068AbB95A902e8de` (通缩分红型)
> - **DOGE (Binance-Peg)**: `0xbA2aE424d960c26247Dd6c32edC70B295c744C43`

### 2. 🖥️ 主控台功能
- **📊 实时状态板**: 顶部实时统计“历史报告总数”、“本次运行新增数”、“本次扫出的蜜罐”和“高风险代币”数量。
- **双引擎报告展示**:
  - **📡 实时报告 Tabs**: 默认展示本次运行期间所有扫描产生的报告。点击折叠面板可以查阅买卖税率明细、Gas 消耗、安全标签判定流程，以及大模型针对该代币输出的深度分析文段。
  - **📁 历史报告 Tabs**: 自动读取 `reports/` 目录中的 markdown 存储件，并以日期进行智能归档和降序罗列，即使服务重启数据也不会丢失。
- **💬 Chat with Contract**: 
  - 页面最下方配置了 AI 聊天框。系统会自动读取最近一次扫描的代币源码审计数据作为上下文。
  - 提问范例：“这个代币为什么有 HONEYPOT 标签？” 或 “解释下第 120 行 owner() 权限的影响”
  - LLM 会基于刚拉取的源码数据为你充当私人代码安全顾问。
- **📜 实时事件日志**:
  - 页面底部通过截流 `Loguru`，将所有后台多智能体协作、RPC 报错、API 调用的运行轨迹毫秒级打印在前端终端，供进阶开发者监控服务状态。

---

## 📁 目录结构 (V2)

```
MemeScan/
├── agents/                    # 🤖 V2 核心 Agent 层
│   ├── base.py               # Agent 基类 (提供 run 与 decide 接口)
│   ├── coordinator.py        # 编排调度者 (分发任务,判断是否深度分析)
│   ├── scanner.py            # 封装链上监听
│   ├── sandbox.py            # 封装 Anvil 并发锁仿真
│   ├── auditor.py            # 规则+大模型深度审计
│   └── reporter.py           # 报告构建与 Chat 回答
│
├── services/                  # 🔧 V1 遗留并升级的底层服务
│   ├── monitor.py            # Web3 PairCreated 监听
│   ├── simulator.py          # 包含 Cast / Anvil 命令调用的底层实现
│   ├── analyzer.py           
│   ├── etherscan.py          # 动态匹配 Etherscan / BscScan
│   └── token_info.py         
│
├── core/                      # 基础单例配置与依赖
├── domain/                    # Pydantic 领域强类型定义
├── reports/                   # 自动储存的 .md 单次报告留存库
└── app.py                     # Streamlit 渲染入口
```

## 📜 许可证

MIT
