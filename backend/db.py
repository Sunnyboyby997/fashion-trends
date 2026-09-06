"""
SQLite 存储层：保存每一期趋势快照，并自动计算热度环比（本期 vs 上期）。

设计要点：
- 每次更新生成一个「期次 period」（取更新当天的日期字符串，如 "2026-09-06"）；
- 趋势以 name 作为跨期对齐主键，插入本期数据时自动查找上期同名校，
  计算热度环比 mom = (本期 heat - 上期 heat) / 上期 heat * 100（百分数）。
"""
import json
import sqlite3
import threading
from datetime import datetime

from . import config

# 数组/对象类型的字段，入库时序列化为 JSON 文本
_JSON_FIELDS = ("style_tags", "hex_colors", "elements", "fabrics", "image_credit", "signals")

# SQLite 在 Flask 主线程与 APScheduler 后台线程同时访问，这里用一把锁保护写入
_LOCK = threading.Lock()


def _get_conn():
    """返回一个数据库连接（每处独立连接，避免跨线程共享连接对象）。"""
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """建表（幂等）。"""
    conn = _get_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trends (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                period          TEXT    NOT NULL,
                name            TEXT    NOT NULL,
                status          TEXT    NOT NULL,
                heat            REAL    NOT NULL,
                style_tags      TEXT    NOT NULL,
                hex_colors      TEXT    NOT NULL,
                silhouette      TEXT,
                elements        TEXT    NOT NULL,
                fabrics         TEXT    NOT NULL,
                summary         TEXT,
                stock_keyword   TEXT,
                image_url       TEXT,
                image_thumb     TEXT,
                image_credit    TEXT,
                signals         TEXT,
                is_demo_image   INTEGER DEFAULT 0,
                is_real         INTEGER DEFAULT 0,
                change_pct      REAL,
                alert           TEXT    DEFAULT 'steady',
                mom             REAL    DEFAULT 0,
                created_at      TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trends_period ON trends(period)")

        # 迁移：为已存在的旧库补充新增列（幂等）
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(trends)")}
        if "is_real" not in cols:
            conn.execute("ALTER TABLE trends ADD COLUMN is_real INTEGER DEFAULT 0")
        if "change_pct" not in cols:
            conn.execute("ALTER TABLE trends ADD COLUMN change_pct REAL")
        if "signals" not in cols:
            conn.execute("ALTER TABLE trends ADD COLUMN signals TEXT")
        if "alert" not in cols:
            conn.execute("ALTER TABLE trends ADD COLUMN alert TEXT DEFAULT 'steady'")
        conn.commit()
    finally:
        conn.close()


def _row_to_trend(row) -> dict:
    """把数据库行转成前端友好的 dict，并反序列化 JSON 字段。"""
    d = dict(row)
    for field in _JSON_FIELDS:
        raw = d.get(field)
        if isinstance(raw, str):
            try:
                d[field] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                d[field] = {} if field == "image_credit" else []
    d["is_demo_image"] = bool(d.get("is_demo_image"))
    d["is_real"] = bool(d.get("is_real"))
    return d


def latest_period() -> str | None:
    """返回最近一个期次字符串，无数据时返回 None。"""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT period FROM trends ORDER BY period DESC, id DESC LIMIT 1"
        ).fetchone()
        return row["period"] if row else None
    finally:
        conn.close()


def get_latest_trends() -> list[dict]:
    """读取最近一期的全部趋势。"""
    period = latest_period()
    if not period:
        return []
    return get_trends_by_period(period)


def get_trends_by_period(period: str) -> list[dict]:
    """读取指定期次的全部趋势。"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM trends WHERE period = ? ORDER BY heat DESC", (period,)
        ).fetchall()
        return [_row_to_trend(r) for r in rows]
    finally:
        conn.close()


def _previous_period(period: str) -> str | None:
    """返回严格早于指定期次的最近一个期次。"""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT DISTINCT period FROM trends WHERE period < ? ORDER BY period DESC LIMIT 1",
            (period,),
        ).fetchone()
        return row["period"] if row else None
    finally:
        conn.close()


def insert_trends(period: str, trends: list[dict]) -> int:
    """
    写入一整期趋势（含环比计算）。

    幂等：若同一天已有数据，先清空该期次再写入，避免手动刷新产生重复行。

    :param period: 期次字符串，如 "2026-09-06"
    :param trends: 趋势对象列表（已包含 image_url / image_credit 等完整字段）
    :return: 写入的条数
    """
    # 取上一期（严格早于本期）的数据用于环比
    prev_period = _previous_period(period)
    prev_by_name = {}
    if prev_period:
        prev_by_name = {t["name"]: t for t in get_trends_by_period(prev_period)}

    created_at = datetime.now().isoformat(timespec="seconds")

    with _LOCK:
        conn = _get_conn()
        try:
            # 幂等：清空本期的旧数据
            conn.execute("DELETE FROM trends WHERE period = ?", (period,))
            for t in trends:
                heat = float(t.get("heat", 0))
                prev = prev_by_name.get(t["name"])
                if prev and prev.get("heat"):
                    mom = round((heat - prev["heat"]) / prev["heat"] * 100, 1)
                else:
                    mom = 0.0

                conn.execute(
                    """
                    INSERT INTO trends (
                        period, name, status, heat, style_tags, hex_colors,
                        silhouette, elements, fabrics, summary, stock_keyword,
                        image_url, image_thumb, image_credit, signals, is_demo_image,
                        is_real, change_pct, alert, mom, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        period,
                        t.get("name"),
                        t.get("status", "stable"),
                        heat,
                        json.dumps(t.get("style_tags", []), ensure_ascii=False),
                        json.dumps(t.get("hex_colors", []), ensure_ascii=False),
                        t.get("silhouette", ""),
                        json.dumps(t.get("elements", []), ensure_ascii=False),
                        json.dumps(t.get("fabrics", []), ensure_ascii=False),
                        t.get("summary", ""),
                        t.get("stock_search_keyword", ""),
                        t.get("image_url", ""),
                        t.get("image_thumb", ""),
                        json.dumps(t.get("image_credit", {}), ensure_ascii=False),
                        json.dumps(t.get("signals", {}), ensure_ascii=False),
                        1 if t.get("is_demo_image") else 0,
                        1 if t.get("is_real") else 0,
                        t.get("change_pct"),
                        t.get("alert", "steady"),
                        mom,
                        created_at,
                    ),
                )
            conn.commit()
            return len(trends)
        finally:
            conn.close()


def count_trends() -> int:
    """当前数据库中的趋势总条数。"""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM trends").fetchone()
        return row["c"]
    finally:
        conn.close()
