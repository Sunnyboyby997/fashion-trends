"""
定时任务：使用 APScheduler 在后台按计划自动执行趋势更新。

- SCHEDULE_MODE=daily   → 每天在 SCHEDULE_TIME 执行一次；
- SCHEDULE_MODE=weekly  → 每周 SCHEDULE_WEEKDAY 在 SCHEDULE_TIME 执行；
- SCHEDULE_MODE=off     → 关闭定时（仍可手动刷新）。
"""
from __future__ import annotations

import os

from apscheduler.schedulers.background import BackgroundScheduler

from . import config, service

_scheduler: BackgroundScheduler | None = None


def start() -> BackgroundScheduler | None:
    """启动后台调度器（幂等，重复调用不会创建多个实例）。"""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    if config.SCHEDULE_MODE == "off":
        return None

    # 默认按中国时区（UTC+8）排程，可用 SCHEDULE_TZ 覆盖
    tz = os.getenv("SCHEDULE_TZ", "Asia/Shanghai")
    _scheduler = BackgroundScheduler(timezone=tz)

    if config.SCHEDULE_MODE == "weekly":
        _scheduler.add_job(
            service.run_update,
            "cron",
            day_of_week=config.SCHEDULE_WEEKDAY,
            hour=config.SCHEDULE_HOUR,
            minute=config.SCHEDULE_MINUTE,
            id="fashion_trend_update",
            misfire_grace_time=3600,
        )
    else:  # daily
        _scheduler.add_job(
            service.run_update,
            "cron",
            hour=config.SCHEDULE_HOUR,
            minute=config.SCHEDULE_MINUTE,
            id="fashion_trend_update",
            misfire_grace_time=3600,
        )

    _scheduler.start()
    return _scheduler
