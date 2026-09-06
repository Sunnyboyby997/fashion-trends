"""
大模型客户端（Claude / Anthropic）：把热度关键词转成标准化 JSON 趋势数据。

未配置 ANTHROPIC_API_KEY、或未安装 anthropic SDK 时返回 None，
由 service 层回退到内置模拟数据。
"""
from __future__ import annotations

import json
import re

from . import config

# 系统提示词：约束输出为严格 JSON 数组，字段与前端/数据库一致
_SYSTEM_PROMPT = """你是一位资深的时尚趋势分析师，擅长把热度关键词转成结构化趋势报告。

请严格输出一个 JSON 数组（不要输出任何 Markdown、解释文字或代码块标记），
数组中的每个对象代表一条趋势，字段如下（全部为必填）：

{
  "name": "趋势中文名（可附带英文原名）",
  "status": "rising | stable | falling 三选一，分别代表 上升/平稳/衰退",
  "heat": 0~100 的整数，热度越高数字越大，需与 status 方向一致,
  "style_tags": ["风格标签字符串数组", "..."],
  "hex_colors": ["#RRGGBB 色值数组", "3~5 个，代表该趋势的代表性配色"],
  "silhouette": "廓形描述，一句话（如：宽松落肩、A字廓形）",
  "elements": ["流行元素数组", "如：羊绒大衣、乐福鞋"],
  "fabrics": ["面料数组", "如：羊绒、真丝"],
  "summary": "趋势总结，一句凝练的中文描述",
  "stock_search_keyword": "用于 Unsplash 图库检索的英文关键词短语"
}

要求：
1. 只返回 JSON 数组本身，不要包裹在 ```json 代码块中；
2. 趋势数量与输入关键词一一对应；
3. status 分布要合理：既有 rising 也有 stable 与 falling，不要全是同一种。"""


def _extract_json(text: str) -> list:
    """稳健地从模型输出中提取 JSON 数组（容忍前后缀、代码块等噪声）。"""
    text = text.strip()
    # 去除 Markdown 代码块围栏
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("模型输出不是 JSON 数组")
    return data


def _normalize(item: dict) -> dict:
    """补全缺失字段，保证数据健壮。"""
    status = item.get("status", "stable")
    if status not in ("rising", "stable", "falling"):
        status = "stable"
    heat = item.get("heat", 50)
    try:
        heat = max(0, min(100, int(float(heat))))
    except (TypeError, ValueError):
        heat = 50
    return {
        "name": str(item.get("name", "未命名趋势")),
        "status": status,
        "heat": heat,
        "style_tags": item.get("style_tags", []) or [],
        "hex_colors": item.get("hex_colors", []) or [],
        "silhouette": str(item.get("silhouette", "")),
        "elements": item.get("elements", []) or [],
        "fabrics": item.get("fabrics", []) or [],
        "summary": str(item.get("summary", "")),
        "stock_search_keyword": str(item.get("stock_search_keyword", "")),
    }


def generate_trends(keywords: list[dict]) -> list[dict] | None:
    """
    调用 Claude 生成趋势数据。

    :param keywords: 热度关键词列表，形如 [{"keyword": "...", "heat_hint": 80}]
    :return: 趋势对象列表；失败或无密钥时返回 None
    """
    if not config.LLM_ENABLED:
        return None

    try:
        import anthropic
    except ImportError:
        return None

    # 构造用户提示：把关键词 + 真实热度/涨跌信号一起喂给模型
    def _line(k):
        parts = [f"- {k['keyword']}"]
        extra = []
        if k.get("heat_hint") is not None:
            extra.append(f"热度 {k['heat_hint']}")
        if k.get("status_hint"):
            extra.append(f"方向 {k['status_hint']}")
        if k.get("change_pct") is not None:
            extra.append(f"近月涨跌 {k['change_pct']:+.1f}%")
        if k.get("hint"):
            extra.append(f"中文：{k['hint']}")
        if extra:
            parts.append("（" + "，".join(extra) + "）")
        return " ".join(parts)

    keyword_lines = "\n".join(_line(k) for k in keywords)
    user_prompt = (
        "以下是本期来自 Google Trends 真实搜索量的时尚热度关键词（附热度与涨跌方向，供你判断）：\n"
        f"{keyword_lines}\n\n"
        "请基于这些关键词，输出对应的趋势 JSON 数组。"
        "status 字段应尽量与给出的「方向」一致；heat 字段参考「热度」数值。"
    )

    client = anthropic.Anthropic()
    try:
        response = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=16000,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as exc:  # 网络/鉴权/限流等异常时回退模拟数据
        print(f"[llm] 调用失败，回退模拟数据：{exc}")
        return None

    text = "".join(block.text for block in response.content if block.type == "text")
    try:
        items = _extract_json(text)
        return [_normalize(item) for item in items if isinstance(item, dict)]
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[llm] 解析失败，回退模拟数据：{exc}")
        return None
