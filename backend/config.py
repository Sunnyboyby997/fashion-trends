"""
全局配置：从环境变量读取所有密钥与运行参数。

说明：
- 所有 API 密钥都通过环境变量 / .env 文件读取，绝不硬编码进代码。
- 没有配置任何密钥时，应用自动进入「演示模式」，
  使用内置模拟趋势数据 + 内置示例图片，页面完整可预览。
"""
import os

# 尝试加载项目根目录下的 .env 文件（如果没装 python-dotenv 则跳过）
try:
    from dotenv import load_dotenv

    # .env 位于项目根目录（backend 的上一级）
    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_ROOT, ".env"))
except ImportError:
    pass


def _bool(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Unsplash 图库密钥
# ---------------------------------------------------------------------------
# 申请步骤（免费）：
#   1. 打开 https://unsplash.com/developers 注册/登录开发者账号；
#   2. 点击 "Your apps" → "New application"，同意 API 使用条款；
#   3. 创建后即可在应用详情页看到 "Access Key"（形如一串 32 位字符）；
#   4. 将 Access Key 填入 .env 的 UNSPLASH_ACCESS_KEY。
# 免费额度：每小时 50 次请求，对个人演示完全够用。
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "").strip()

# Unsplash 官方提供的「demo 应用」密钥，仅作演示、速率受限。
# 若你不想申请密钥，也可以留空，代码会自动回退到内置示例图片。
UNSPLASH_DEMO_KEY = os.getenv("UNSPLASH_DEMO_KEY", "").strip()

# 实际生效的 Unsplash 密钥（优先正式 key，其次 demo key）
UNSPLASH_KEY = UNSPLASH_ACCESS_KEY or UNSPLASH_DEMO_KEY

# ---------------------------------------------------------------------------
# 大模型（Claude / Anthropic）密钥
# ---------------------------------------------------------------------------
# 申请步骤：
#   1. 打开 https://console.anthropic.com 注册并创建 API Key；
#   2. 将 key 填入 .env 的 ANTHROPIC_API_KEY。
# 未配置时，趋势数据由内置「模拟数据」生成，功能完整。
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5").strip()

# ---------------------------------------------------------------------------
# 数据库
# ---------------------------------------------------------------------------
DB_PATH = os.getenv(
    "DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "trends.db"),
)

# ---------------------------------------------------------------------------
# 定时任务配置
# ---------------------------------------------------------------------------
# SCHEDULE_MODE: "daily"(每日) / "weekly"(每周) / "off"(关闭定时)
# SCHEDULE_TIME: "HH:MM" 每天/每周触发时间（24 小时制，默认凌晨 3 点错峰）
# SCHEDULE_WEEKDAY: weekly 模式下生效，"mon"~"sun"
SCHEDULE_MODE = os.getenv("SCHEDULE_MODE", "daily").strip().lower()
_SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "03:00").strip()
try:
    SCHEDULE_HOUR, SCHEDULE_MINUTE = (int(x) for x in _SCHEDULE_TIME.split(":"))
except ValueError:
    SCHEDULE_HOUR, SCHEDULE_MINUTE = 3, 0
SCHEDULE_WEEKDAY = os.getenv("SCHEDULE_WEEKDAY", "mon").strip().lower()

# ---------------------------------------------------------------------------
# 服务开关 / 演示模式判定
# ---------------------------------------------------------------------------
LLM_ENABLED = bool(ANTHROPIC_API_KEY)
UNSPLASH_ENABLED = bool(UNSPLASH_KEY)

# 演示模式：没有配置大模型密钥即为演示模式（核心数据走模拟）
DEMO_MODE = not LLM_ENABLED

# ---------------------------------------------------------------------------
# 真实趋势数据源（Google Trends / pytrends）
# ---------------------------------------------------------------------------
# 代理：Google 在中国大陆无法直连，如需访问 Google Trends 请配置本地代理，
# 例如 TRENDS_PROXY=http://127.0.0.1:7890（Clash / V2Ray 等本地代理端口）。
# 留空则优先沿用系统 HTTPS_PROXY。
TRENDS_PROXY = os.getenv("TRENDS_PROXY", "").strip() or os.getenv("HTTPS_PROXY", "").strip()

# 时间窗口（Google Trends 语法）：today 3-m = 近 90 天；today 12-m = 近 12 个月
TRENDS_TIMEFRAME = os.getenv("TRENDS_TIMEFRAME", "today 3-m").strip()

# 地域：留空 = 全球；可填 "US" / "GB" / "CN" 等 ISO 地区码
TRENDS_GEO = os.getenv("TRENDS_GEO", "").strip()

# 服务端口
PORT = int(os.getenv("PORT", "8000"))
