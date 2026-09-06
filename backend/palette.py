"""
调色板辅助：把 HEX 色值翻译成「颜色名 + 适配场景」，供色彩板块展示。

场景标签基于色相 / 饱和度 / 亮度做启发式判断，无需外部依赖。
"""
from __future__ import annotations


def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    hex_str = hex_str.strip().lstrip("#")
    if len(hex_str) == 3:
        hex_str = "".join(c * 2 for c in hex_str)
    return tuple(int(hex_str[i : i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hsl(r, g, b):
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        h = s = 0.0
    else:
        d = mx - mn
        s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
        if mx == r:
            h = (g - b) / d + (6 if g < b else 0)
        elif mx == g:
            h = (b - r) / d + 2
        else:
            h = (r - g) / d + 4
        h *= 60
    return h, s, l


def describe_color(hex_str: str) -> dict:
    """返回 {"name": 颜色中文名, "scene": 适配场景}。"""
    r, g, b = hex_to_rgb(hex_str)
    h, s, l = _rgb_to_hsl(r, g, b)

    # 低饱和 → 中性色系
    if s < 0.14:
        if l > 0.86:
            return {"name": "奶油白", "scene": "日常 / 通勤"}
        if l > 0.66:
            return {"name": "燕麦灰", "scene": "通勤 / 约会"}
        if l > 0.45:
            return {"name": "暖灰", "scene": "通勤 / 职场"}
        if l > 0.24:
            return {"name": "炭灰", "scene": "职场 / 晚宴"}
        return {"name": "墨黑", "scene": "晚宴 / 正装"}

    # 彩色系按色相区间命名
    if h < 15 or h >= 340:
        name = "酒红" if l < 0.4 else "正红"
        return {"name": name, "scene": "晚宴 / 派对"}
    if h < 45:
        name = "焦糖棕" if l < 0.5 else "驼色"
        return {"name": name, "scene": "秋冬 / 休闲"}
    if h < 70:
        name = "姜黄" if s > 0.5 else "香槟金"
        return {"name": name, "scene": "度假 / 晚宴"}
    if h < 170:
        name = "橄榄绿" if l < 0.5 else "薄荷绿"
        return {"name": name, "scene": "日常 / 户外"}
    if h < 260:
        name = "雾霾蓝" if s < 0.4 else "湖蓝"
        return {"name": name, "scene": "通勤 / 休闲"}
    name = "薰衣草紫" if l > 0.6 else "玫瑰粉"
    return {"name": name, "scene": "约会 / 浪漫"}
