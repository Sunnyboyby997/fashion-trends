"""
内置示例图片：仅在未配置 Unsplash 密钥时，作为「示意配图」回退使用。

诚实说明：
- 这些是 Unsplash 公共 CDN 上的实拍时尚照片，真实存在（HTTP 200），
  但演示模式下无法按关键词精确检索，只能作为「示意参考图」；
- 界面会对这类图片明确标注「示意配图」，绝不冒充精确匹配；
- 配置 UNSPLASH_ACCESS_KEY 后，会由 unsplash.search_image 按
  stock_search_keyword 检索真实匹配图片，并带真实摄影师署名。
"""
from __future__ import annotations

# Unsplash 公共 CDN 上的时尚实拍示例图（demo 用途，w=900 控制宽度）
_MOCK_IMAGES = [
    "https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=900&q=80&fit=crop",
    "https://images.unsplash.com/photo-1483985988355-763728e1935b?w=900&q=80&fit=crop",
    "https://images.unsplash.com/photo-1445205170230-053b83016050?w=900&q=80&fit=crop",
    "https://images.unsplash.com/photo-1539109136881-3be0616acf4b?w=900&q=80&fit=crop",
    "https://images.unsplash.com/photo-1525507119028-ed4c629a60a3?w=900&q=80&fit=crop",
    "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=900&q=80&fit=crop",
    "https://images.unsplash.com/photo-1529139574466-a303027c1d8b?w=900&q=80&fit=crop",
    "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=900&q=80&fit=crop",
    "https://images.unsplash.com/photo-1495385794356-15371f348c31?w=900&q=80&fit=crop",
    "https://images.unsplash.com/photo-1469334031218-e382a71b716b?w=900&q=80&fit=crop",
]


def get_mock_image(trend: dict, index: int = 0) -> dict:
    """
    返回一张「示意配图」（与 Unsplash 客户端返回结构一致）。

    :param trend: 趋势对象
    :param index: 用于从示例图池里轮换取图
    """
    url = _MOCK_IMAGES[index % len(_MOCK_IMAGES)]
    return {
        "url": url,
        "thumb": url + "&w=400",
        "credit": {
            "name": "Unsplash · 示意配图",
            "username": "unsplash",
            "link": "https://unsplash.com",
        },
        "is_demo": True,
    }
