"""
Flask 应用：提供前端静态页面与趋势数据 API。

API 一览：
  GET  /              → 前端首页
  GET  /api/status    → 应用状态（演示模式、定时计划、最近更新）
  GET  /api/trends    → 最近一期趋势列表
  GET  /api/colors    → 整套流行配色
  GET  /api/elements  → 元素热度排行（三栏）
  GET  /api/report    → Markdown 完整趋势报告文本
  POST /api/refresh   → 手动触发一次全自动更新
"""
from __future__ import annotations

import os
import threading

from flask import Flask, Response, jsonify, request, send_from_directory

from . import config, db, service

_FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend"
)

app = Flask(__name__, static_folder=_FRONTEND_DIR, static_url_path="/static")


@app.route("/")
def index():
    """返回前端首页。"""
    return send_from_directory(_FRONTEND_DIR, "index.html")


@app.get("/api/status")
def api_status():
    return jsonify(service.get_status())


@app.get("/api/trends")
def api_trends():
    return jsonify(service.get_trends())


@app.get("/api/colors")
def api_colors():
    return jsonify(service.get_colors())


@app.get("/api/elements")
def api_elements():
    return jsonify(service.get_elements())


@app.get("/api/forecast")
def api_forecast():
    """早期预警 / 趋势预测：按动量排序 + 预警等级 + 多源置信度。"""
    return jsonify(service.get_forecast())


@app.get("/api/feed")
def api_feed():
    """业务可直接消费的结构化趋势信号流（JSON）。"""
    return jsonify(service.get_feed())


@app.get("/api/feed.csv")
def api_feed_csv():
    """业务数据流 CSV 导出。"""
    csv_text = service.build_feed_csv()
    return Response(
        csv_text,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="fashion-feed.csv"'},
    )


@app.get("/api/report")
def api_report():
    """返回 Markdown 报告文本，供前端一键导出 .md 文件。"""
    md = service.build_report()
    return Response(md, mimetype="text/markdown; charset=utf-8")


@app.post("/api/refresh")
def api_refresh():
    """
    手动触发一次全自动更新。

    更新在后台线程异步执行，立即返回「已启动」；
    若已有更新在跑，则返回 409 提示前端稍后再试。
    前端轮询 /api/status 直到 running=false 再刷新页面数据。
    """
    if service.is_running():
        return jsonify({"running": True, "skipped": True}), 409
    threading.Thread(target=service.run_update, daemon=True).start()
    return jsonify({"started": True, "running": True})


def run(host: str = "0.0.0.0", port: int | None = None):
    """启动 HTTP 服务。"""
    app.run(host=host, port=port or config.PORT, threaded=True, debug=False)
