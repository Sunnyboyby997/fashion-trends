"""
多源信号融合 + 趋势动量 / 起飞预警评分。

目标：把 Google Trends（搜索热度）、Reddit（社区讨论）、电商（购物需求/供给）
三个真实来源的信号，融合成一个可排序、可验证、可用于业务侧的趋势信号：

  - heat         融合热度 0~100（各源按权重加权，缺失源自动重归一化权重）
  - change_pct   融合动量（近月涨跌 %，仅取有动量数据的源加权）
  - status       由融合动量判 rising / stable / falling
  - momentum     融合动量得分（用于排序）
  - confidence   存活源数量 0~3（= 可验证程度）
  - alert        起飞预警：takeoff / hot / watch / steady / cooling

预警逻辑（诚实、可解释，非玄学）：
  - takeoff（起飞）：≥2 个源同时上升 且 融合动量 ≥ +8%
  - hot（火热）：融合热度 ≥ 80
  - watch（观察）：融合动量 ≥ +6%（单一源在升温，值得盯）
  - cooling（降温）：融合动量 ≤ -6%
  - steady（平稳）：其余
"""
from __future__ import annotations

import requests

from . import config, ecommerce_source, reddit_source, trends_source

# 各源在融合热度中的权重
SOURCE_WEIGHTS = {
    "google_trends": 0.5,
    "reddit": 0.3,
    "ecommerce": 0.2,
}

SOURCE_LABELS = {
    "google_trends": "Google Trends 搜索热度",
    "reddit": "Reddit 社区讨论",
    "ecommerce": "电商购物信号",
}

# 动量判定阈值（%）
RISING_THRESHOLD = 6.0
FALLING_THRESHOLD = -6.0
TAKEOFF_MOMENTUM = 8.0
HOT_HEAT = 80.0


def _status_of(change_pct: float | None) -> str:
    if change_pct is None:
        return "stable"
    if change_pct >= RISING_THRESHOLD:
        return "rising"
    if change_pct <= FALLING_THRESHOLD:
        return "falling"
    return "stable"


def _normalize_source_heat(signals: dict[str, dict]) -> dict[str, dict]:
    """
    把某源内各关键词的 `_raw_heat` 归一化到 0~100（heat 字段）。
    若源本身已给出 0~100 的 heat（如 Google Trends），则原样保留。
    """
    # 收集需要归一化的原始值
    raw_values: dict[str, float] = {}
    for kw, sig in signals.items():
        if not sig:
            continue
        if "_raw_heat" in sig and sig["_raw_heat"] is not None:
            raw_values[kw] = float(sig["_raw_heat"])
        elif "heat" in sig and sig.get("heat") is not None:
            raw_values[kw] = float(sig["heat"])

    if not raw_values:
        return signals

    max_raw = max(raw_values.values()) or 1.0
    for kw, sig in signals.items():
        if not sig:
            continue
        val = raw_values.get(kw)
        if val is not None:
            sig["heat"] = round(val / max_raw * 100)
        sig.pop("_raw_heat", None)
    return signals


def _proxies() -> dict | None:
    if config.TRENDS_PROXY:
        return {"http": config.TRENDS_PROXY, "https": config.TRENDS_PROXY}
    return None


def _reachable(url: str, timeout: float = 4.0) -> bool:
    """快速连通性探测：避免网络不可达时每个源逐关键词重试导致长时间卡死。

    返回 HTTP 状态 < 400 才算「可达」——像 Reddit 对 VPN 出口 IP 返回 403，
    虽能连通但实际拿不到数据，应视为「不可用」直接跳过，而非逐关键词空转。
    """
    try:
        r = requests.get(
            url, timeout=timeout, proxies=_proxies(),
            headers={"User-Agent": "Mozilla/5.0"}, stream=True,
        )
        ok = r.status_code < 400
        r.close()
        return ok
    except Exception:
        return False


def collect_all(keywords: list[str]) -> dict:
    """
    采集全部三个来源的原始信号。先对每个源做快速连通性探测，
    探测不通（被墙 / 代理失效）则直接跳过该源，避免逐关键词重试卡死。

    返回：
      {
        "google_trends": {kw: {...}} | None,
        "reddit":        {kw: {...}},
        "ecommerce":     {kw: {...}},
      }
    """
    gt = None
    if _reachable("https://trends.google.com/"):
        gt = trends_source.fetch_real_signals(keywords)

    rd: dict = {}
    if _reachable("https://www.reddit.com/"):
        rd = reddit_source.fetch_all(keywords)

    ec: dict = {}
    if _reachable(
        "https://completion.amazon.com/api/2017/suggestions?mid=ATVPDKIKX0DER&alias=aps&prefix=fashion&limit=3"
    ):
        ec = ecommerce_source.fetch_all(keywords)

    # 归一化各源 heat（Google Trends 已返回 0~100，直接使用）
    rd = _normalize_source_heat(rd)
    ec = _normalize_source_heat(ec)
    return {"google_trends": gt, "reddit": rd, "ecommerce": ec}


def _as_unified(source: str, keyword: str, sig: dict) -> dict:
    """把一个源的信号统一成展示友好的结构。"""
    return {
        "source": source,
        "label": SOURCE_LABELS[source],
        "heat": sig.get("heat"),
        "change_pct": sig.get("change_pct"),
        "status": sig.get("status", "stable"),
        "ok": bool(sig.get("ok", True)),
        "error": sig.get("error"),
        "detail": sig.get("detail"),
    }


def fuse(keywords: list[str], collected: dict) -> dict[str, dict]:
    """
    融合三个来源，返回 {keyword: fused}。

    fused 结构：
      {
        "keyword", "heat", "change_pct", "status", "momentum",
        "confidence", "alert", "is_real", "signals": {source: {...}}
      }
    """
    gt = collected.get("google_trends") or {}
    rd = collected.get("reddit") or {}
    ec = collected.get("ecommerce") or {}

    fused: dict[str, dict] = {}
    for kw in keywords:
        # 汇总该关键词在各源的信号（统一结构）
        src_map: dict[str, dict] = {}
        if kw in gt:
            src_map["google_trends"] = _as_unified("google_trends", kw, gt[kw])
        if kw in rd:
            src_map["reddit"] = _as_unified("reddit", kw, rd[kw])
        if kw in ec:
            src_map["ecommerce"] = _as_unified("ecommerce", kw, ec[kw])

        live = {s: v for s, v in src_map.items() if v["ok"] and v["heat"] is not None}

        # 融合热度：按权重加权（缺失源重归一化）
        heat = 0.0
        momentum = None
        rising_count = 0
        if live:
            w_sum = sum(SOURCE_WEIGHTS[s] for s in live)
            for s, v in live.items():
                heat += v["heat"] * SOURCE_WEIGHTS[s] / w_sum
            heat = round(heat, 1)

            # 融合动量：仅取有 change_pct 的源加权
            mom_parts = [
                (SOURCE_WEIGHTS[s], v["change_pct"])
                for s, v in live.items()
                if v.get("change_pct") is not None
            ]
            if mom_parts:
                m_sum = sum(w for w, _ in mom_parts)
                momentum = round(sum(w * c for w, c in mom_parts) / m_sum, 1)
            for v in live.values():
                if v.get("status") == "rising":
                    rising_count += 1

        status = _status_of(momentum)
        confidence = len(live)
        is_real = confidence > 0

        # 起飞预警
        if is_real and rising_count >= 2 and (momentum or 0) >= TAKEOFF_MOMENTUM:
            alert = "takeoff"
        elif is_real and heat >= HOT_HEAT:
            alert = "hot"
        elif is_real and (momentum or 0) >= RISING_THRESHOLD:
            alert = "watch"
        elif is_real and (momentum or 0) <= FALLING_THRESHOLD:
            alert = "cooling"
        else:
            alert = "steady"

        fused[kw] = {
            "keyword": kw,
            "heat": heat,
            "change_pct": momentum,
            "status": status,
            "momentum": momentum or 0.0,
            "confidence": confidence,
            "alert": alert,
            "is_real": is_real,
            "signals": src_map,
        }

    return fused
