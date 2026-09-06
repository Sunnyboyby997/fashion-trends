"""
Reddit 时尚社区数据源（真实、公开、可验证）。

原理：
- 使用 Reddit 的公开 JSON 接口（无需登录、无需密钥、无官方 API 门槛），
  对每个时尚关键词做全站搜索，统计「相关帖子数」与「总点赞数」，
  得到真实的社区讨论热度。
- 时间维度用 `t=month`（近一月热帖）度量当前热度 heat；
  用 `t=week`（近一周热帖）相对月均的强度估算 momentum（涨跌），
  从而得到 change_pct 与 rising/stable/falling。

诚实说明：
- Reddit 在中国大陆无法直连，需代理；
- 免费未认证接口有速率限制（约 1 req/s），故按关键词逐个、带退避地抓取；
- 任何一步失败都返回 None，由 service 层标注该源「不可用」，绝不冒充数据。
"""
from __future__ import annotations

import time

import requests

from . import config

# 统一请求头（Reddit 要求描述性的 User-Agent，否则会被拒）
_HEADERS = {
    "User-Agent": "fashion-trends-research/1.0 (trend signal analysis; contact: dev@example.com)",
}

_TIMEOUT = (8, 18)


def _proxies() -> dict | None:
    if config.TRENDS_PROXY:
        return {"http": config.TRENDS_PROXY, "https": config.TRENDS_PROXY}
    return None


def _search_score(keyword: str, window: str) -> tuple[int, int] | None:
    """返回 (总赞数, 帖子数)。window 为 Reddit 的 t 参数：week / month / year。"""
    url = "https://www.reddit.com/search.json"
    params = {
        "q": keyword,
        "sort": "top",
        "t": window,
        "limit": 100,
        "restrict_sr": "0",  # 全站搜索（关键词本身就是时尚术语，自然命中时尚社区）
    }
    resp = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT, proxies=_proxies())
    resp.raise_for_status()
    data = resp.json()
    children = (data.get("data") or {}).get("children") or []
    if not children:
        return 0, 0
    total_score = sum(int(c.get("data", {}).get("score", 0)) for c in children)
    return total_score, len(children)


def fetch_signal(keyword: str) -> dict | None:
    """
    抓取单个关键词的 Reddit 社区信号。

    返回统一信号结构，失败返回 None：
      {"source": "reddit", "keyword": kw, "heat": 0-100, "change_pct": float|None,
       "status": "rising|stable|falling", "ok": True, "error": None, "detail": {...}}
    """
    try:
        month_score, month_posts = _search_score(keyword, "month")
        time.sleep(0.6)  # 退避，避免触发速率限制
        week_score, week_posts = _search_score(keyword, "week")
    except Exception as exc:  # 网络失败 / 被墙 / 被限流
        print(f"[reddit] '{keyword}' 抓取失败（该源将标记为不可用）：{exc}")
        return None

    # 近一月热度信号：帖子数 + 总赞数（帖子数放大权重，避免单条爆款主导）
    raw_heat = month_posts * 50 + month_score
    if raw_heat <= 0:
        return None

    # 动量：近一周热度 vs 月均周热度（month/4.3），>0 表示近期在升温
    avg_week_month = (month_posts * 50 + month_score) / 4.3
    week_raw = week_posts * 50 + week_score
    if avg_week_month > 0:
        change_pct = round((week_raw - avg_week_month) / avg_week_month * 100, 1)
    else:
        change_pct = None

    return {
        "source": "reddit",
        "keyword": keyword,
        "heat": 0,  # 占位：跨关键词归一化由 fusion 层统一完成
        "_raw_heat": raw_heat,
        "change_pct": change_pct,
        "status": _status_of(change_pct),
        "ok": True,
        "error": None,
        "detail": {
            "month_posts": month_posts,
            "month_score": month_score,
            "week_posts": week_posts,
            "week_score": week_score,
            "endpoint": "https://www.reddit.com/search.json",
        },
    }


def _status_of(change_pct: float | None) -> str:
    if change_pct is None:
        return "stable"
    if change_pct >= 6:
        return "rising"
    if change_pct <= -6:
        return "falling"
    return "stable"


def fetch_all(keywords: list[str]) -> dict[str, dict]:
    """抓取一批关键词的 Reddit 信号，返回 {keyword: signal}。失败的关键词不含在内。"""
    out: dict[str, dict] = {}
    for kw in keywords:
        sig = fetch_signal(kw)
        if sig is not None:
            out[kw] = sig
    return out
