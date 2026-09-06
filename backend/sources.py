"""
公开趋势数据源（模拟）。

说明：
- 这里用「样例数据」模拟 Google Trends / Exploding Topics 等公开免费趋势源，
  仅作为大模型生成趋势报告的输入关键词，绝不爬取任何社交平台页面。
- 每个关键词带一个 heat_hint（0~100 的热度提示），用于在无大模型时
  供模拟数据参考，以及帮助大模型判断上升/平稳/衰退的方向。
"""

# 时尚领域热门关键词样例（keyword 为英文，便于 Unsplash 图库检索；hint 为中文提示）
TREND_KEYWORDS = [
    {"keyword": "quiet luxury fashion", "heat_hint": 94, "hint": "静奢风"},
    {"keyword": "balletcore aesthetic", "heat_hint": 88, "hint": "芭蕾核"},
    {"keyword": "gorpcore outdoor style", "heat_hint": 82, "hint": "户外机能风"},
    {"keyword": "office siren style", "heat_hint": 76, "hint": "办公室塞壬风"},
    {"keyword": "old money aesthetic", "heat_hint": 71, "hint": "老钱风"},
    {"keyword": "minimalist capsule wardrobe", "heat_hint": 66, "hint": "极简胶囊衣橱"},
    {"keyword": "western cowboy fashion", "heat_hint": 58, "hint": "西部牛仔风"},
    {"keyword": "coquette aesthetic", "heat_hint": 55, "hint": "娇俏蝴蝶结风"},
    {"keyword": "y2k fashion", "heat_hint": 48, "hint": "千禧风"},
    {"keyword": "dopamine dressing colorful", "heat_hint": 40, "hint": "多巴胺穿搭"},
]


def get_keywords() -> list[dict]:
    """返回本期的热度关键词列表（供大模型或模拟数据使用）。"""
    return TREND_KEYWORDS
