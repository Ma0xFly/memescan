"""
agents/base.py — Agent 基类

所有 Agent 继承此基类。与普通 Service 的核心区别:
  - run()  执行任务
  - decide()  自主决策下一步动作（这是 Agent 的灵魂）
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from loguru import logger


class BaseAgent(ABC):
    """MemeScan Agent 基类。

    每个 Agent 都有:
      name   — 人类可读的名称，用于日志和 UI 显示
      run()  — 执行一个任务，返回结构化结果
      decide() — 根据上下文自主决策下一步动作
    """

    name: str = "BaseAgent"

    @abstractmethod
    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """执行任务。

        参数:
            task: 任务上下文字典，具体 key 由各子类定义。

        返回:
            结果字典，具体 key 由各子类定义。
        """

    async def decide(self, context: dict[str, Any]) -> str:
        """根据当前上下文自主决策下一步动作。

        默认返回 "done"（不需要追加操作）。
        子类可覆盖此方法以实现更复杂的决策逻辑。

        返回:
            动作名称字符串，如:
              - "done"           — 任务完成
              - "need_deep_analysis" — 需要追加 LLM 源码分析
              - "skip"           — 跳过当前代币
        """
        return "done"

    def log(self, message: str, **kwargs: Any) -> None:
        """统一日志格式: [AgentName] message"""
        logger.info(f"[{self.name}] {message}", **kwargs)

    def log_error(self, message: str, **kwargs: Any) -> None:
        """统一错误日志"""
        logger.error(f"[{self.name}] {message}", **kwargs)
