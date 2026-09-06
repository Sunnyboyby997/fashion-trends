"""
核心服务编排：多源真实信号采集 → 融合 → 编辑部内容 → 配图 → 入库 → 派生视图。

一条完整的更新流水线：
  1. fusion.collect_all 并行抓取三个真实来源的信号：
       - Google Trends（搜索热度，pytrends）
       - Reddit 时尚社区（讨论热度，公开 JSON）
       - 电商（Amazon 搜索联想，购物需求）
  2. fusion.fuse 融合多源 → 热度 heat / 动量 change_pct / status / 起飞预警 alert；
  3. 编辑部内容（名称、标签、色值、总结）优先交给大模型生成，否则用内置模板；
  4. 用融合结果覆盖每条趋势的 heat / status / change_pct，并附上每源明细 signals；
  5. 用 stock_search_keyword 去 Unsplash 检索实拍图片（失败则用示例图）；
  6. 写入 SQLite（自动计算环比），记录数据来源是「实时多源」还是「离线样例」。
"""
from __future__ import annotations

import threading
from datetime import datetime

from . import config, db, fusion, llm, mock_data, palette, trends_source, unsplash

# 防止定时任务与手动刷新并发执行（非阻塞：拿不到锁就直接跳过）
_LOCK = threading.Lock()

# 最近一次更新结果（供 /api/status 展示）
_LAST_RESULT: dict = {
    "running": False,
    "last_run": None,
    "count": 0,
    "source": "offline",   # multi | offline
    "sources": {},         # {google_trends: ok, reddit: ok, ecommerce: ok}
    "editorial": "template",
    "error": None,
}


def _attach_images(trends: list[dict]) -> None:
    """为每条趋势检索并挂载图片 + 版权署名信息。"""
    for i, trend in enumerate(trends):
        keyword = trend.get("stock_search_keyword", "")
        img = unsplash.search_image(keyword) if keyword else None
        if img is None:
            img = mock_data.get_mock_image(trend, i)
        trend["image_url"] = img["url"]
        trend["image_thumb"] = img.get("thumb", img["url"])
        trend["image_credit"] = img["credit"]
        trend["is_demo_image"] = bool(img.get("is_demo"))


def _keyword_hints(templates: list[dict], fused: dict) -> list[dict]:
    """构造给大模型的关键词提示（携带融合后的真实热度/涨跌）。"""
    hints = []
    for t in templates:
        f = fused.get(t["keyword"])
        hints.append(
            {
                "keyword": t["keyword"],
                "heat_hint": f["heat"] if f else t["default_heat"],
                "status_hint": f["status"] if f else t["default_status"],
                "change_pct": (f.get("change_pct") if f else None),
                "hint": t["name"],
            }
        )
    return hints


def _confidence(signals: dict | None) -> int:
    """从每源明细里统计存活（真实数据）来源数。"""
    if not signals:
        return 0
    return sum(1 for s in signals.values() if isinstance(s, dict) and s.get("ok"))


def run_update() -> dict:
    """执行一次完整的多源趋势更新（定时任务与手动刷新共用）。"""
    if not _LOCK.acquire(blocking=False):
        return {"running": True, "skipped": True}

    _LAST_RESULT["running"] = True
    _LAST_RESULT["error"] = None
    try:
        templates = trends_source.get_templates()
        keywords = trends_source.get_keywords()

        # 1. 采集三源真实信号 + 融合
        collected = fusion.collect_all(keywords)
        fused = fusion.fuse(keywords, collected)

        # 记录每源是否存活（供前端数据来源面板展示）
        sources_ok = {
            "google_trends": collected["google_trends"] is not None,
            "reddit": bool(collected["reddit"]),
            "ecommerce": bool(collected["ecommerce"]),
        }
        any_real = any(sources_ok.values())
        data_source = "multi" if any_real else "offline"

        # 2. 编辑部内容：优先大模型，其次模板
        editorial = None
        if config.LLM_ENABLED:
            editorial = llm.generate_trends(_keyword_hints(templates, fused))
        editorial_source = "llm" if editorial is not None else "template"

        # 3. 合并：模板/LLM 内容 + 融合信号覆盖 + 每源明细
        trends = []
        for i, tpl in enumerate(templates):
            if editorial is not None and i < len(editorial):
                base = editorial[i]
            else:
                base = {k: v for k, v in tpl.items() if k not in ("keyword", "default_heat", "default_status")}
                base["heat"] = tpl["default_heat"]
                base["status"] = tpl["default_status"]

            f = fused.get(tpl["keyword"])
            if f and f.get("is_real"):
                base["heat"] = f["heat"]
                base["status"] = f["status"]
                base["change_pct"] = f["change_pct"]
                base["is_real"] = True
                base["signals"] = f["signals"]
                base["alert"] = f["alert"]
            else:
                base["change_pct"] = None
                base["is_real"] = False
                base["signals"] = {}
                base["alert"] = "steady"
            trends.append(base)

        _attach_images(trends)

        period = datetime.now().strftime("%Y-%m-%d")
        count = db.insert_trends(period, trends)

        _LAST_RESULT.update(
            {
                "running": False,
                "last_run": datetime.now().isoformat(timespec="seconds"),
                "count": count,
                "source": data_source,
                "sources": sources_ok,
                "editorial": editorial_source,
                "period": period,
                "error": None,
            }
        )
        return dict(_LAST_RESULT)
    except Exception as exc:  # 任何异常都不应让后台任务崩溃
        _LAST_RESULT.update({"running": False, "error": str(exc)})
        return dict(_LAST_RESULT)
    finally:
        _LAST_RESULT["running"] = False
        _LOCK.release()


def seed_if_empty() -> None:
    """首次启动时若无数据，用离线模板预填一期，保证页面打开即有内容。"""
    if db.count_trends() > 0:
        return
    trends = trends_source.build_offline_trends()
    for t in trends:
        t.setdefault("signals", {})
        t.setdefault("alert", "steady")
    _attach_images(trends)
    db.insert_trends(datetime.now().strftime("%Y-%m-%d"), trends)


def _db_source_status() -> dict:
    """跨进程重启后，从最近一期入库数据的 signals 反推各源是否存活。"""
    sources = {"google_trends": False, "reddit": False, "ecommerce": False}
    for t in db.get_latest_trends():
        for src, sig in (t.get("signals") or {}).items():
            if isinstance(sig, dict) and sig.get("ok"):
                sources[src] = True
    return sources


def last_result() -> dict:
    """
    最近一次更新结果。`_LAST_RESULT` 是内存态，进程重启即丢失；
    若本进程尚未运行过更新（sources 为空），则从数据库反推来源存活状态，
    避免重启后前端数据来源面板 / 报告头被误标为「离线」。
    """
    result = dict(_LAST_RESULT)
    if not result.get("sources"):
        db_sources = _db_source_status()
        if any(db_sources.values()):
            result["sources"] = db_sources
            result["source"] = "multi"
    return result


def is_running() -> bool:
    """是否有更新任务正在执行（供手动刷新判断是否并发）。"""
    return _LOCK.locked()


def get_status() -> dict:
    """应用状态：演示模式开关、密钥配置、定时计划、数据来源、最近更新。"""
    return {
        "demo": config.DEMO_MODE,
        "llm_enabled": config.LLM_ENABLED,
        "unsplash_enabled": config.UNSPLASH_ENABLED,
        "trends_proxy": bool(config.TRENDS_PROXY),
        "schedule": {
            "mode": config.SCHEDULE_MODE,
            "time": f"{config.SCHEDULE_HOUR:02d}:{config.SCHEDULE_MINUTE:02d}",
            "weekday": config.SCHEDULE_WEEKDAY,
        },
        "last_update": db.latest_period(),
        "last_result": last_result(),
    }


def get_trends() -> dict:
    """返回最近一期趋势数据（含更新时间与数据来源）。"""
    trends = db.get_latest_trends()
    if not trends:
        return {"period": None, "updated_at": None, "demo": config.DEMO_MODE, "trends": []}
    updated_at = max(t.get("created_at", "") for t in trends)
    return {
        "period": trends[0].get("period"),
        "updated_at": updated_at,
        "demo": config.DEMO_MODE,
        "data_source": last_result().get("source", "offline"),
        "trends": trends,
    }


def get_colors() -> dict:
    """整套流行配色：去重统计 + 颜色名 + 适配场景。"""
    order: list[str] = []
    counter: dict[str, int] = {}
    for t in db.get_latest_trends():
        for h in t.get("hex_colors", []):
            h = str(h).strip().upper()
            if not h:
                continue
            if h not in counter:
                counter[h] = 0
                order.append(h)
            counter[h] += 1

    colors = []
    for h in order:
        d = palette.describe_color(h)
        colors.append(
            {"hex": h, "name": d["name"], "scene": d["scene"], "count": counter[h]}
        )
    return {"colors": colors}


def get_elements() -> dict:
    """元素热度排行：按父趋势的状态分三栏（rising/stable/falling）。"""
    buckets: dict[str, dict] = {"rising": {}, "stable": {}, "falling": {}}
    for t in db.get_latest_trends():
        status = t.get("status", "stable")
        bucket = buckets.get(status, buckets["stable"])
        for e in t.get("elements", []):
            e = str(e).strip()
            if not e:
                continue
            if e not in bucket:
                bucket[e] = {"name": e, "heat": 0, "trend": t.get("name", "")}
            bucket[e]["heat"] = max(bucket[e]["heat"], int(t.get("heat", 0)))

    result = {}
    for key, items in buckets.items():
        ordered = sorted(items.values(), key=lambda x: -x["heat"])
        result[key] = ordered
    return result


# ---------------------------------------------------------------------------
# 业务侧输出：起飞预警 / 数据流 / CSV
# ---------------------------------------------------------------------------
ALERT_LABELS = {
    "takeoff": "🚀 起飞",
    "hot": "🔥 火热",
    "watch": "👀 观察",
    "steady": "📌 平稳",
    "cooling": "📉 降温",
}


def get_forecast() -> dict:
    """
    早期预警 / 趋势预测视图：按融合动量降序排列，
    标注每条趋势的预警等级与多源置信度（可验证程度）。
    """
    items = []
    for t in db.get_latest_trends():
        alert = t.get("alert", "steady")
        items.append(
            {
                "name": t.get("name"),
                "heat": t.get("heat"),
                "change_pct": t.get("change_pct"),
                "momentum": t.get("change_pct") or 0.0,
                "alert": alert,
                "alert_label": ALERT_LABELS.get(alert, "平稳"),
                "confidence": _confidence(t.get("signals")),
                "status": t.get("status"),
                "summary": t.get("summary"),
            }
        )
    items.sort(key=lambda x: -x["momentum"])
    return {"forecast": items, "alerts": ALERT_LABELS}


def get_feed() -> dict:
    """业务可直接消费的结构化趋势信号流（JSON）。"""
    trends = db.get_latest_trends()
    feed = []
    for t in trends:
        feed.append(
            {
                "name": t.get("name"),
                "heat": t.get("heat"),
                "status": t.get("status"),
                "change_pct": t.get("change_pct"),
                "alert": t.get("alert", "steady"),
                "confidence": _confidence(t.get("signals")),
                "style_tags": t.get("style_tags", []),
                "hex_colors": t.get("hex_colors", []),
                "elements": t.get("elements", []),
                "fabrics": t.get("fabrics", []),
                "summary": t.get("summary"),
                "stock_search_keyword": t.get("stock_search_keyword"),
                "image_url": t.get("image_url"),
                "period": t.get("period"),
            }
        )
    return {"period": db.latest_period(), "trends": feed}


def build_feed_csv() -> str:
    """业务数据流 CSV 导出。"""
    import csv
    import io

    feed = get_feed()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "name", "heat", "status", "change_pct", "alert", "confidence",
            "style_tags", "elements", "fabrics", "summary", "stock_search_keyword",
        ]
    )
    for t in feed["trends"]:
        w.writerow(
            [
                t["name"],
                t["heat"],
                t["status"],
                t["change_pct"] if t["change_pct"] is not None else "",
                t["alert"],
                t["confidence"],
                "、".join(t["style_tags"]),
                "、".join(t["elements"]),
                "、".join(t["fabrics"]),
                t["summary"],
                t["stock_search_keyword"],
            ]
        )
    return buf.getvalue()


def build_report() -> str:
    """把最近一期趋势拼装成完整 Markdown 报告文本。"""
    data = get_trends()
    trends = data["trends"]
    period = data["period"] or "——"
    updated = data["updated_at"] or "——"
    if data.get("data_source") == "multi":
        source_label = "多源实时（Google Trends + Reddit + 电商）"
    elif data.get("data_source") == "google_trends":
        source_label = "Google Trends 实时搜索量"
    else:
        source_label = "离线样例（尚未连通任何实时来源）"

    status_label = {"rising": "🔥 上升 Rising", "stable": "📌 平稳 Stable", "falling": "📉 衰退 Falling"}
    lines = [
        "# 时尚流行趋势报告",
        "",
        f"> 期次：`{period}`　|　更新时间：`{updated}`　|　数据来源：{source_label} + Unsplash 图库",
        "",
    ]

    for t in trends:
        lines.append(f"## {t['name']} — {status_label.get(t['status'], t['status'])}")
        lines.append("")
        if t.get("image_url"):
            lines.append(f"![{t['name']}]({t['image_url']})")
            lines.append("")
        alert = t.get("alert", "steady")
        lines.append(f"- **预警等级**：{ALERT_LABELS.get(alert, alert)}（置信源 {_confidence(t.get('signals'))}/3）")
        if t.get("summary"):
            lines.append(t["summary"])
            lines.append("")
        if t.get("heat"):
            change = t.get("change_pct")
            change_text = f"　（近月涨跌 {change:+.1f}%）" if change is not None else ""
            lines.append(f"- **热度指数**：{t['heat']} / 100{change_text}")
        if t.get("style_tags"):
            lines.append(f"- **风格标签**：{'、'.join(t['style_tags'])}")
        if t.get("hex_colors"):
            lines.append(f"- **代表色**：{' '.join(t['hex_colors'])}")
        if t.get("silhouette"):
            lines.append(f"- **廓形**：{t['silhouette']}")
        if t.get("elements"):
            lines.append(f"- **流行元素**：{'、'.join(t['elements'])}")
        if t.get("fabrics"):
            lines.append(f"- **面料**：{'、'.join(t['fabrics'])}")
        credit = t.get("image_credit") or {}
        if credit.get("name"):
            lines.append(f"- **图片来源**：[{credit.get('name')}]({credit.get('link', 'https://unsplash.com')}) / Unsplash")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)
