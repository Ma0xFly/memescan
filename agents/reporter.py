"""
agents/reporter.py — 报告者 Agent

负责生成 Markdown 审计报告和 Chat with Contract 交互。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from agents.base import BaseAgent
from core.config import get_settings
from domain.models import AuditReport


class ReporterAgent(BaseAgent):
    """报告者 Agent — 生成报告 + Chat with Contract。"""

    name = "ReporterAgent"

    def __init__(self) -> None:
        self._settings = get_settings()
        self._llm_client = None

    def _get_llm_client(self):
        """懒加载 LLM 客户端。"""
        if self._llm_client is None and self._settings.llm_api_key:
            from openai import AsyncOpenAI
            self._llm_client = AsyncOpenAI(
                api_key=self._settings.llm_api_key,
                base_url=self._settings.llm_base_url,
            )
        return self._llm_client

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """生成并保存报告。

        task keys:
          report: AuditReport 对象

        返回:
          md_content: str  (Markdown 报告内容)
          file_path: str   (保存路径)
        """
        report: AuditReport = task["report"]

        md = self._generate_markdown(report)
        file_path = self._save_report(report, md)

        self.log(f"报告已生成: {file_path}")

        return {
            "md_content": md,
            "file_path": str(file_path),
        }

    async def chat(self, question: str, report: AuditReport) -> str:
        """Chat with Contract — 用户针对审计结果提问。

        参数:
            question: 用户问题
            report: 当前代币的审计报告

        返回:
            AI 回答
        """
        client = self._get_llm_client()
        if not client:
            return "⚠️ 未配置 LLM API Key，无法使用 Chat 功能。请在 .env 中设置 LLM_API_KEY。"

        flags_str = ", ".join(f.value for f in report.risk_flags)
        sim = report.simulation

        prompt = (
            f"你是 MemeScan AI 助手。以下是代币 {report.token.symbol or '未知'} 的审计数据:\n"
            f"- 代币地址: {report.token.address}\n"
            f"- 风险评分: {report.risk_score:.1f}/100\n"
            f"- 风险标签: [{flags_str}]\n"
            f"- 仿真结果: 可买={sim.can_buy}, 可卖={sim.can_sell}\n"
            f"- 买入税: {sim.buy_tax_pct:.1f}%, 卖出税: {sim.sell_tax_pct:.1f}%\n"
            f"- 蜜罐: {'是' if sim.is_honeypot else '否'}\n"
        )

        if report.llm_summary:
            prompt += f"- AI 审计摘要: {report.llm_summary[:500]}\n"

        prompt += f"\n用户问题: {question}\n请用中文简洁回答。"

        try:
            response = await client.chat.completions.create(
                model=self._settings.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是 MemeScan AI 安全助手，帮助用户理解代币审计结果。"
                            "回答要简洁、专业、易懂。如果代币有风险，要明确警告。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=300,
                temperature=0.5,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            self.log_error(f"Chat 调用失败: {e}")
            return f"⚠️ AI 回答失败: {e}"

    # ── 报告生成 ────────────────────────────────────────────────

    def _generate_markdown(self, report: AuditReport) -> str:
        """生成 Markdown 格式审计报告。"""
        token = report.token
        sim = report.simulation
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 风险等级
        score = report.risk_score
        if score >= 60:
            level = "🔴 高风险"
        elif score >= 30:
            level = "🟡 中风险"
        else:
            level = "🟢 低风险"

        # 风险标签
        if report.risk_flags:
            flags_section = "\n".join(
                f"- ⚠️ **{f.value}**" for f in report.risk_flags
            )
        else:
            flags_section = "- ✅ 未检测到已知风险标签"

        md = f"""# 🔍 代币审计报告 — {token.symbol or '???'}

> 生成时间: {now}
> 由 MemeScan V2 (Multi-Agent System) 自动生成

---

## 📌 基本信息

| 项目 | 值 |
|------|-----|
| **代币符号** | {token.symbol or '???'} |
| **代币地址** | `{token.address}` |
| **交易对地址** | `{token.pair_address}` |
| **所在链** | Ethereum Mainnet |

---

## 🎯 风险评估

| 项目 | 结果 |
|------|------|
| **风险评分** | **{score:.0f} / 100** |
| **风险等级** | {level} |
| **蜜罐检测** | {'🔴 是' if sim.is_honeypot else '✅ 否'} |

### 触发的风险标签

{flags_section}

---

## 🧪 仿真结果

| 项目 | 结果 |
|------|------|
| **可买入** | {'✅ 是' if sim.can_buy else '❌ 否'} |
| **可卖出** | {'✅ 是' if sim.can_sell else '❌ 否'} |
| **买入税率** | {sim.buy_tax_pct:.2f}% |
| **卖出税率** | {sim.sell_tax_pct:.2f}% |
| **买入 Gas** | {sim.buy_gas:,} |
| **卖出 Gas** | {sim.sell_gas:,} |

---

## 📝 分析摘要

{report.llm_summary}

---

## ⚙️ 仿真参数

- 仿真引擎: Foundry Anvil (主网分叉)
- 买入金额: 0.1 ETH
- DEX: Uniswap V2 Router
- 分析引擎: MemeScan V2 Multi-Agent
- 仿真时间: {now}

---

*本报告由 MemeScan V2 多智能体系统自动生成，仅供参考，不构成投资建议。*
"""
        return md

    def _save_report(self, report: AuditReport, md_content: str) -> Path:
        """保存报告到 reports/ 目录。"""
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)

        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        symbol = report.token.symbol or "???"
        addr_short = report.token.address[:10]
        filename = f"{now}_{symbol}_{addr_short}.md"
        filepath = reports_dir / filename

        filepath.write_text(md_content, encoding="utf-8")
        return filepath
