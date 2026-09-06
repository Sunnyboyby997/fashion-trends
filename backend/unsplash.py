"""
Unsplash 图库客户端：用 stock_search_keyword 检索实拍时尚图片。

申请 Access Key 步骤（免费）：
  1. 打开 https://unsplash.com/developers 登录；
  2. "Your apps" → "New application"，勾选同意 API 条款；
  3. 在应用详情页复制 Access Key，填入 .env 的 UNSPLASH_ACCESS_KEY。

返回结构统一为：
  {"url": 大图, "thumb": 缩略图, "credit": {"name", "username", "link"}, "is_demo": bool}
"""
from __future__ import annotations

from . import config


def search_image(keyword: str, orientation: str = "portrait") -> dict | None:
    """
    根据关键词检索一张时尚图片。

    :param keyword: 英文搜索关键词（来自趋势的 stock_search_keyword）
    :param orientation: 图片方向，默认竖图适合杂志卡片
    :return: 图片信息 dict；无密钥或检索失败时返回 None
    """
    key = config.UNSPLASH_KEY
    if not key:
        return None

    try:
        import requests
    except ImportError:
        return None

    url = "https://api.unsplash.com/search/photos"
    params = {
        "query": keyword,
        "per_page": 1,
        "orientation": orientation,
        "content_filter": "high",
    }
    headers = {"Authorization": f"Client-ID {key}"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"[unsplash] 检索失败，回退示例图片：{exc}")
        return None

    results = data.get("results") or []
    if not results:
        return None

    photo = results[0]
    return {
        "url": photo["urls"]["regular"],
        "thumb": photo["urls"]["thumb"],
        "credit": {
            "name": photo["user"]["name"],
            "username": photo["user"]["username"],
            "link": photo["user"]["links"]["html"],
        },
        "is_demo": False,
    }
