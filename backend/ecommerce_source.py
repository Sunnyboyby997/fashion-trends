"""
电商数据源（真实、公开、可验证，best-effort）。

信号：Amazon 搜索联想（需求侧 / 购物者搜索热度）
    https://completion.amazon.com/api/2017/suggestions?mid=ATVPDKIKX0DER&alias=aps&prefix={kw}

这是干净可靠的 JSON 接口，可直接在浏览器打开对账。通过两条可解释的信号衡量
「购物需求是否真实、是否有产品生态」：

1. 精确匹配排名（exact_rank）：联想词里有没有正好等于关键词的项，排第几。
   排得越靠前，说明购物者越直接、越确定地在搜这个趋势（而非拼写近邻）。
2. 长尾深度（extension_count）：包含关键词作为修饰词扩展的联想条数
   （如 "balletcore dress" / "balletcore tops"），越多说明该趋势有真实的产品长尾。

原始热度 = 长尾深度 × 7 + 精确排名加分（rank0=30，越靠后越低）。

诚实说明：
- 该接口仅反映「当前购物搜索需求」，无历史曲线，故 change_pct 恒为 None，
  涨跌动量由 Google Trends / Reddit 提供；
- Zara 站内搜索是纯前端 SPA（商品数据经未公开 JS 接口异步加载、无可解析的
  内嵌 JSON），无法稳定可验证地统计商品数，故**已移除**，电商信号仅用 Amazon；
- 关键词无任何联想命中（需求为零）时返回 None，该关键词电商侧视为无信号。
"""
from __future__ import annotations

import requests

from . import config

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

_TIMEOUT = (8, 18)


def _proxies() -> dict | None:
    if config.TRENDS_PROXY:
        return {"http": config.TRENDS_PROXY, "https": config.TRENDS_PROXY}
    return None


def _amazon_suggestions(keyword: str) -> list[str] | None:
    url = "https://completion.amazon.com/api/2017/suggestions"
    params = {
        "mid": "ATVPDKIKX0DER",   # 美国站 marketplace id
        "alias": "aps",           # 全品类
        "prefix": keyword,
        "limit": 10,
    }
    resp = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT, proxies=_proxies())
    resp.raise_for_status()
    data = resp.json()
    suggs = data.get("suggestions") or []
    return [s.get("value", "") for s in suggs if isinstance(s, dict)]


def _amazon_raw_heat(suggs: list[str], keyword: str) -> tuple[float, dict]:
    """把联想词转成可解释的原始热度 + 明细（用于对账）。"""
    lowered = keyword.lower()

    exact_rank = None
    for i, s in enumerate(suggs):
        if s.strip().lower() == lowered:
            exact_rank = i
            break

    extension_count = sum(1 for s in suggs if lowered in s.lower())

    # 精确排名加分：rank0=30、rank1=27、…，越靠后越低（未命中为 0）
    rank_bonus = max(0, 10 - exact_rank) * 3.0 if exact_rank is not None else 0.0
    raw = extension_count * 7.0 + rank_bonus

    detail = {
        "exact_rank": exact_rank,
        "extension_count": extension_count,
        "suggestions": suggs,
    }
    return raw, detail


def fetch_signal(keyword: str) -> dict | None:
    """
    抓取单个关键词的电商信号。返回统一信号结构，失败返回 None。

    关键词无任何联想命中（购物需求为零）时返回 None，该关键词电商侧视为无信号。
    """
    try:
        suggs = _amazon_suggestions(keyword)
    except Exception as exc:
        print(f"[ecommerce] '{keyword}' Amazon 联想失败：{exc}")
        return None

    if not suggs:
        return None

    raw_heat, detail = _amazon_raw_heat(suggs, keyword)
    if raw_heat <= 0:
        return None

    return {
        "source": "ecommerce",
        "keyword": keyword,
        "heat": 0,  # 占位：跨关键词归一化由 fusion 层完成
        "_raw_heat": raw_heat,
        "change_pct": None,  # 电商无历史曲线，动量由其他源提供
        "status": "stable",
        "ok": True,
        "error": None,
        "detail": detail,
    }


def fetch_all(keywords: list[str]) -> dict[str, dict]:
    """抓取一批关键词的电商信号，返回 {keyword: signal}。失败的关键词不含在内。"""
    out: dict[str, dict] = {}
    for kw in keywords:
        sig = fetch_signal(kw)
        if sig is not None:
            out[kw] = sig
    return out
