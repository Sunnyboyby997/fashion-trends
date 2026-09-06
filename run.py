"""
启动入口：初始化数据库 → 预填数据 → 启动定时任务 → 启动 Web 服务。

用法：
    python run.py
然后浏览器打开 http://127.0.0.1:8000
"""
from backend import config, db, scheduler, service
from backend.app import app, run


def main():
    # 1. 初始化数据库（幂等）
    db.init_db()

    # 2. 若库为空，用模拟数据预填一期，保证首次打开即有内容
    service.seed_if_empty()

    # 3. 启动定时任务（根据 .env 配置 daily/weekly/off）
    scheduler.start()

    # 4. 启动 Web 服务
    mode = "演示模式（未配置密钥，使用内置模拟数据）" if config.DEMO_MODE else "真实模式（已配置密钥）"
    print("=" * 56)
    print("  TENDANCE · 时尚流行趋势观察站")
    print(f"  运行模式：{mode}")
    print(f"  定时计划：{config.SCHEDULE_MODE} @ {config.SCHEDULE_HOUR:02d}:{config.SCHEDULE_MINUTE:02d}")
    print(f"  访问地址：http://127.0.0.1:{config.PORT}")
    print("=" * 56)
    run()


if __name__ == "__main__":
    main()
