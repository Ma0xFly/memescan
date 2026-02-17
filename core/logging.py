"""
core/logging.py — 基于 Loguru 的结构化日志配置

设置双输出通道：
  1. 人类可读的彩色输出 → stderr
  2. 结构化 JSON 日志 → 文件（按天轮转）

在应用启动时调用 `setup_logging()` 一次即可。
"""

from __future__ import annotations

import sys

from loguru import logger

from core.config import get_settings


def setup_logging() -> None:
    """配置 Loguru 日志输出通道。"""
    settings = get_settings()
    log_dir = settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    # 移除默认输出通道。
    logger.remove()

    # 通道 1：人类可读格式 → stderr
    logger.add(
        sys.stderr,
        level="INFO",
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # 通道 2：JSON 格式 → 按天轮转的日志文件
    logger.add(
        log_dir / "memescan_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        format="{message}",
        serialize=True,  # JSON 结构化输出
        rotation="00:00",  # 午夜创建新文件
        retention="7 days",
        compression="gz",
        enqueue=True,  # 线程安全
    )

    logger.info("日志系统初始化完成", log_dir=str(log_dir))
