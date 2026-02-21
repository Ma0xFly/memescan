"""
agents/scanner.py — 扫描者 Agent

封装 MonitorService，负责监听链上 PairCreated 事件。
支持多链并行扫描（ETH + BSC）。
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine

from agents.base import BaseAgent
from services.monitor import MonitorService
from domain.models import Token


class ScannerAgent(BaseAgent):
    """扫描者 Agent — 监听链上新代币事件。

    将 MonitorService 包装为 Agent 接口。
    支持为不同链创建不同的 MonitorService 实例。
    """

    name = "ScannerAgent"

    def __init__(
        self,
        on_new_pair: Callable[[Token], Coroutine],
        chain_name: str = "ethereum",
    ) -> None:
        self._on_new_pair = on_new_pair
        self._chain_name = chain_name
        self._monitor: MonitorService | None = None

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """启动监控。

        task keys:
          action: "start" | "stop"
        """
        action = task.get("action", "start")

        if action == "start":
            self._monitor = MonitorService(on_new_pair=self._on_new_pair)
            self.log(f"启动 {self._chain_name} 链监控")
            await self._monitor.start()
            return {"status": "stopped"}  # start() 阻塞直到 stop

        elif action == "stop":
            if self._monitor:
                self._monitor.stop()
                self.log(f"停止 {self._chain_name} 链监控")
            return {"status": "stopped"}

        return {"status": "unknown_action"}

    def stop(self) -> None:
        """快捷方法: 停止监控。"""
        if self._monitor:
            self._monitor.stop()
