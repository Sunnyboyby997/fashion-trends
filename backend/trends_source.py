"""
真实趋势数据源：Google Trends（通过 pytrends 非官方库）。

关键事实（务必诚实）：
- Google Trends 只在你指定具体关键词时返回数据，不会凭空给出「热门榜单」，
  因此这里维护一个「时尚关键词候选池」——这是唯一需要人工维护的部分；
- 每个关键词的「热度 heat」与「上涨/平稳/衰退 status」都由真实搜索兴趣曲线计算：
      heat   = 近期(近30天)平均搜索兴趣，跨关键词归一化到 0~100
      change = 近30天 vs 前30天 的涨跌幅(%)
      status = change >= +6% 为 rising，<= -6% 为 falling，其余 stable
- 抓取失败（未装 pytrends / Google 被墙 / 被限流）时返回 None，
  由 service 层明确降级为「离线样例」并在界面标注，绝不冒充实时数据。
"""
from __future__ import annotations

import time

from . import config

# ---------------------------------------------------------------------------
# pytrends 4.9.2 与 urllib3 2.x 的兼容补丁
# ---------------------------------------------------------------------------
def _patch_urllib3_retry() -> None:
    """pytrends 仍调用 urllib3 已移除的 `method_whitelist` 参数（2.x 改为 `allowed_methods`）。"""
    import urllib3.util.retry as _ur

    if not getattr(_ur.Retry, "_fashion_patched", False):
        _orig = _ur.Retry.__init__

        def _patched(self, *args, **kwargs):
            if "method_whitelist" in kwargs:
                kwargs["allowed_methods"] = kwargs.pop("method_whitelist")
            _orig(self, *args, **kwargs)

        _ur.Retry.__init__ = _patched
        _ur.Retry._fashion_patched = True

    # pytrends 从 requests.packages.urllib3 导入 Retry；若为独立副本也一并打补丁
    try:
        import requests.packages.urllib3.util.retry as _rp  # noqa: F401
        if _rp.Retry is not _ur.Retry:
            _rp.Retry.__init__ = _ur.Retry.__init__
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 时尚关键词候选池（keyword = Google Trends 查询词；其余为该趋势的编辑部模板内容）
# ---------------------------------------------------------------------------
TREND_POOL = [
    {
        "keyword": "quiet luxury",
        "name": "静奢风 Quiet Luxury",
        "default_heat": 94, "default_status": "rising",
        "style_tags": ["极简", "高级感", "无Logo"],
        "hex_colors": ["#8B7355", "#C9A96A", "#2C2A26", "#E8E0D5"],
        "silhouette": "宽松廓形、垂坠直线条、不强调身形",
        "elements": ["羊绒大衣", "真丝衬衫", "无Logo手袋", "极简乐福鞋"],
        "fabrics": ["羊绒", "真丝", "重磅棉"],
        "summary": "以质感与剪裁取胜的低调奢华，摒弃张扬 Logo，用顶级面料与利落线条传递身份感。",
        "stock_search_keyword": "quiet luxury minimal fashion",
    },
    {
        "keyword": "balletcore",
        "name": "芭蕾核 Balletcore",
        "default_heat": 88, "default_status": "rising",
        "style_tags": ["浪漫", "少女感", "缎带"],
        "hex_colors": ["#F5E6E8", "#E8B4C8", "#C9A96A", "#FDF6F0"],
        "silhouette": "收腰、薄纱蓬裙、系带蝴蝶结",
        "elements": ["芭蕾平底鞋", "缎带发饰", "薄纱裙", "针织裹身"],
        "fabrics": ["薄纱", "缎面", "针织"],
        "summary": "芭蕾舞者美学，柔软缎带与薄纱叠搭，温柔浪漫的少女感。",
        "stock_search_keyword": "balletcore fashion",
    },
    {
        "keyword": "gorpcore",
        "name": "户外机能风 Gorpcore",
        "default_heat": 82, "default_status": "rising",
        "style_tags": ["户外", "机能", "实用主义"],
        "hex_colors": ["#4A5A4F", "#8A9A5B", "#2F2F2F", "#C9A96A"],
        "silhouette": "宽松机能、多口袋、抽绳收口",
        "elements": ["机能马甲", "冲锋衣", "户外工装裤", "登山鞋"],
        "fabrics": ["GORE-TEX", "尼龙", "抓绒"],
        "summary": "把户外装备穿进城市，功能性与街头感并存的实用主义风。",
        "stock_search_keyword": "gorpcore outdoor fashion",
    },
    {
        "keyword": "office siren",
        "name": "办公室塞壬风 Office Siren",
        "default_heat": 76, "default_status": "rising",
        "style_tags": ["职场", "复古", "性感"],
        "hex_colors": ["#2C2A26", "#C9A96A", "#8B7355", "#F3ECE1"],
        "silhouette": "修身西装、铅笔裙、尖头细跟",
        "elements": ["修身西装", "铅笔裙", "细框眼镜", "尖头鞋"],
        "fabrics": ["羊毛", "真丝", "皮革"],
        "summary": "干练与性感并存的职场新美学，修身西装与尖头鞋塑造强势气场。",
        "stock_search_keyword": "office siren style",
    },
    {
        "keyword": "old money",
        "name": "老钱风 Old Money",
        "default_heat": 71, "default_status": "stable",
        "style_tags": ["复古", "学院", "低调优雅"],
        "hex_colors": ["#4A3B2A", "#C9A96A", "#F3ECE1", "#2C2A26"],
        "silhouette": "合身剪裁、Polo衫、百褶裙",
        "elements": ["针织开衫", "乐福鞋", "珍珠配饰", "百褶裙"],
        "fabrics": ["羊毛", "亚麻", "麂皮"],
        "summary": "世家气质的低调优雅，羊绒、乐福鞋与珍珠的经典组合。",
        "stock_search_keyword": "old money aesthetic",
    },
    {
        "keyword": "capsule wardrobe",
        "name": "极简胶囊衣橱 Capsule",
        "default_heat": 66, "default_status": "stable",
        "style_tags": ["极简", "基础款", "实用"],
        "hex_colors": ["#F5F5F0", "#C9A96A", "#333333", "#8B7355"],
        "silhouette": "基础直筒、中性色、易叠穿",
        "elements": ["白衬衫", "直筒裤", "基础T恤", "西装外套"],
        "fabrics": ["棉", "羊毛", "牛仔"],
        "summary": "少而精的胶囊衣橱理念，基础款与中性色永不过时。",
        "stock_search_keyword": "minimalist capsule wardrobe",
    },
    {
        "keyword": "cowboy boots",
        "name": "西部牛仔风 Western",
        "default_heat": 58, "default_status": "stable",
        "style_tags": ["复古", "西部", "粗犷"],
        "hex_colors": ["#8B4513", "#C9A96A", "#5C4033", "#F5DEB3"],
        "silhouette": "牛仔靴、流苏、宽檐帽",
        "elements": ["牛仔靴", "流苏外套", "宽檐帽", "皮革腰带"],
        "fabrics": ["牛仔", "麂皮", "皮革"],
        "summary": "西部牛仔元素持续流行，牛仔靴与流苏是核心单品。",
        "stock_search_keyword": "western cowboy fashion",
    },
    {
        "keyword": "coquette",
        "name": "娇俏蝴蝶结风 Coquette",
        "default_heat": 55, "default_status": "falling",
        "style_tags": ["复古", "少女", "蝴蝶结"],
        "hex_colors": ["#FADDE1", "#FFB6C1", "#FFF5F5", "#C9A96A"],
        "silhouette": "荷叶边、蝴蝶结、收腰",
        "elements": ["蝴蝶结发饰", "荷叶边衬衫", "玛丽珍鞋"],
        "fabrics": ["蕾丝", "雪纺", "缎面"],
        "summary": "蝴蝶结与荷叶边的娇俏少女风，热度较峰值有所回落。",
        "stock_search_keyword": "coquette aesthetic",
    },
    {
        "keyword": "y2k fashion",
        "name": "千禧风 Y2K",
        "default_heat": 48, "default_status": "falling",
        "style_tags": ["复古", "千禧", "闪耀"],
        "hex_colors": ["#FF6FB5", "#7FD8E8", "#C9F5FF", "#8A2BE2"],
        "silhouette": "低腰、紧身、露脐",
        "elements": ["低腰牛仔裤", "蝴蝶发夹", "闪亮配饰", "露脐上衣"],
        "fabrics": ["牛仔", "亮片", "PVC"],
        "summary": "千禧年复古回潮，低腰与亮片的热度正在退潮。",
        "stock_search_keyword": "y2k fashion",
    },
    {
        "keyword": "dopamine dressing",
        "name": "多巴胺穿搭 Dopamine",
        "default_heat": 40, "default_status": "falling",
        "style_tags": ["鲜艳", "撞色", "活力"],
        "hex_colors": ["#FF5C5C", "#FFB02E", "#38C172", "#4A90E2"],
        "silhouette": "宽松、高饱和撞色",
        "elements": ["亮色针织", "撞色配饰", "彩色西装"],
        "fabrics": ["针织", "棉", "雪纺"],
        "summary": "高饱和撞色的活力穿搭，热度较峰值明显回落。",
        "stock_search_keyword": "colorful fashion outfit",
    },
]


def get_templates() -> list[dict]:
    """返回关键词候选池（模板）。"""
    return TREND_POOL


def get_keywords() -> list[str]:
    """返回全部 Google Trends 查询词。"""
    return [t["keyword"] for t in TREND_POOL]


def build_offline_trends() -> list[dict]:
    """把模板转成「离线样例」趋势列表（无实时数据时使用，明确标注 is_real=False）。"""
    out = []
    for t in TREND_POOL:
        d = {k: v for k, v in t.items() if k not in ("keyword", "default_heat", "default_status")}
        d["heat"] = t["default_heat"]
        d["status"] = t["default_status"]
        d["is_real"] = False
        d["change_pct"] = None
        out.append(d)
    return out


_CHUNK_SIZE = 5  # Google Trends 单次对比的词数上限


def _make_chunks(keywords: list[str]) -> list[list[str]]:
    """把关键词切成 ≤5 个/块的序列，相邻块共享 1 个「桥接词」，用于跨块对齐热度标尺。"""
    if len(keywords) <= _CHUNK_SIZE:
        return [list(keywords)]
    chunks = [keywords[:_CHUNK_SIZE]]
    remaining = keywords[_CHUNK_SIZE:]
    while remaining:
        bridge = chunks[-1][-1]                 # 上一块的最后一个词作桥
        chunks.append([bridge] + remaining[:_CHUNK_SIZE - 1])
        remaining = remaining[_CHUNK_SIZE - 1:]
    return chunks


def fetch_real_signals(keywords: list[str], timeframe: str | None = None, geo: str | None = None) -> dict | None:
    """
    用 pytrends 抓取每个关键词的真实 Google 搜索兴趣，返回信号字典：

        {keyword: {"heat": int(0-100), "change_pct": float, "status": "rising|stable|falling"}}

    关键实现点（诚实、可复现）：
    - Google Trends 一次最多对比 5 个词，超过会返回 400，故必须分块；
    - 各块内部共用 0~100 相对刻度（100 = 组内峰值）。为了把不同块拉到同一条标尺，
      相邻块共享一个「桥接词」：同一桥接词在两块中的值之比，即两块刻度之比，
      据此把后续块等比缩放到第一块的标尺（链式桥接）。
    - 不能用一个超大词（如 "fashion"）当锚点——它比这些长尾趋势词大百倍，
      会导致趋势词被四舍五入成 0；所以桥接词只用「趋势词彼此」。
    - heat = 近 30 天平均兴趣，跨关键词对齐后归一化到 0~100；
    - change_pct = 近 30 天 vs 前 30 天的涨跌幅（逐词自相对，天然可比较）。

    失败（未安装 pytrends / 无法访问 Google / 被限流）返回 None。
    """
    try:
        from pytrends.request import TrendReq
    except ImportError:
        return None

    timeframe = timeframe or config.TRENDS_TIMEFRAME
    if geo is None:
        geo = config.TRENDS_GEO

    # pytrends 要求 proxies 为「代理字符串列表」，并在内部按索引取用；
    # 传 dict 会导致 KeyError，传字符串会被按字符拆解。
    proxies = None
    if config.TRENDS_PROXY:
        proxies = [config.TRENDS_PROXY]

    _patch_urllib3_retry()
    try:
        pytrends = TrendReq(
            hl="en-US",
            tz=0,
            timeout=(15, 45),
            proxies=proxies,
            retries=1,          # 内部重试收敛为 1 次：429 由外层的长退避重试处理
            backoff_factor=1.0,
        )
    except Exception as exc:
        print(f"[trends] Google Trends 初始化失败（将降级为离线样例）：{exc}")
        return None

    chunks = _make_chunks(keywords)
    kw_recent: dict[str, float] = {}     # keyword -> 对齐到第 0 块标尺的近 30 天均值
    kw_change: dict[str, float] = {}     # keyword -> 涨跌幅 %

    # 共享 VPN 出口 IP 会被 Google Trends 限流（429），故用较长的指数退避重试，
    # 并在块间留出冷却时间；单块失败仅跳过该块，其余块/源继续（优雅降级）。
    _RETRY_BACKOFF = (6.0, 15.0, 30.0)

    for i, chunk in enumerate(chunks):
        if i > 0:
            time.sleep(8.0)

        df = None
        for attempt in range(len(_RETRY_BACKOFF)):
            try:
                pytrends.build_payload(kw_list=chunk, timeframe=timeframe, geo=geo or "")
                df = pytrends.interest_over_time()
                if df is not None and not df.empty:
                    break
            except Exception as exc:
                print(f"[trends] Google Trends 块抓取失败（{chunk}，第{attempt + 1}次）：{exc}")
            if attempt < len(_RETRY_BACKOFF) - 1:
                time.sleep(_RETRY_BACKOFF[attempt])

        if df is None or df.empty:
            continue
        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])

        block_recent: dict[str, float] = {}
        block_change: dict[str, float] = {}
        for kw in chunk:
            if kw not in df.columns:
                continue
            series = df[kw].astype(float).dropna()
            if series.empty or series.sum() == 0:
                continue  # 该词无有效数据（搜索量过低），跳过
            recent = float(series.iloc[-30:].mean())
            block_recent[kw] = recent
            n = len(series)
            if n >= 60:
                prior = float(series.iloc[-60:-30].mean())
            elif n > 30:
                prior = float(series.iloc[:-30].mean())
            else:
                prior = recent
            block_change[kw] = float((recent - prior) / prior * 100) if prior else 0.0

        if i == 0:
            scale = 1.0
        else:
            # 用桥接词把本块缩放到第 0 块标尺；桥失效则退化为独立刻度（诚实，不做假对齐）
            bridge = chunk[0]
            scale = 1.0
            if bridge in block_recent and bridge in kw_recent:
                b0, bi = kw_recent[bridge], block_recent[bridge]
                if b0 > 0 and bi > 0:
                    scale = b0 / bi

        for kw in chunk:
            if kw in block_recent:
                if kw not in kw_recent:  # 每个词只按首次出现的块记录
                    kw_recent[kw] = block_recent[kw] * scale
                    kw_change[kw] = block_change[kw]

    if not kw_recent:
        return None

    max_recent = max(kw_recent.values()) or 1.0
    signals: dict = {}
    for kw, recent in kw_recent.items():
        change = kw_change.get(kw, 0.0)
        if change >= 6:
            status = "rising"
        elif change <= -6:
            status = "falling"
        else:
            status = "stable"
        signals[kw] = {
            "heat": round(recent / max_recent * 100),
            "change_pct": round(change, 1),
            "status": status,
        }
    return signals
