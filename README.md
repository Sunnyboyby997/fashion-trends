# TENDANCE · 全自动时尚流行趋势分析与预测

一个**全程无需手动上传图片、不使用 AI 生成图片**的时尚趋势分析与早期预警应用：后端定时抓取 **三个真实公开数据源**，多源交叉验证识别「正在起飞」的趋势，再调用 **Unsplash 免费商用图库**自动配图，呈现在暗色轻奢杂志风前端，并提供业务可直接消费的数据流。

> 图片全部来自 Unsplash 实拍图库并附带版权署名；趋势热度/涨跌来自真实公开数据（连通时），绝不爬取社交平台登录墙背后的私有内容。

---

## 重要：关于「真实、可靠、可验证」的诚实边界

### 三个真实数据源（都可验证，都能对账）

| 来源 | 信号 | 接口 | 在中国大陆 |
| --- | --- | --- | --- |
| **Google Trends** | 搜索热度 + 近月涨跌 | pytrends 抓真实搜索兴趣曲线 | 需代理 |
| **Reddit 时尚社区** | 社区讨论热度 + 近周动量 | 公开 JSON（`reddit.com/search.json`） | 需代理 |
| **电商（Amazon）** | 购物搜索需求 | Amazon 搜索联想 JSON（精确匹配排名 + 长尾深度） | 需代理 |

> **关于 IP 级限制（如实说明）**：Google Trends 对共享 VPN 出口 IP 会限流（HTTP 429），
> Reddit 会封禁数据中心/VPN 出口 IP（HTTP 403）。这两种限制是「IP 信誉」层面的，
> 不是代码能绕过的——换一个住宅/独享出口节点即可恢复三源全通；否则对应源会被
> 自动标记「离线」，其余源继续工作，绝不冒充。电商侧 Zara 站内搜索是纯前端 SPA
> （商品数据经未公开 JS 接口异步加载），无法稳定可验证地统计，故已移除，电商信号仅用 Amazon。

### 关于「预测」的诚实说法

没有任何工具能可靠「预知下一季流行什么」。本项目的「预测」是**可解释的早期信号预警**：

- 对每个时尚关键词，融合三源热度 → 融合动量（近月涨跌 %）；
- **起飞预警（takeoff）**：≥2 个源同时上升 且 融合动量 ≥ +8%，即标记「🚀 起飞」；
- **置信度**：存活数据源数量（0~3），即「有多少个真实来源交叉印证」，数值越高越可靠。

这是业务侧真正能用、能复现、不吹牛的东西。

### 什么爬不动、不会塞进项目

Instagram / TikTok / 小红书 / 抖音：都有登录墙 + 签名校验 + 强反爬，强爬会封号且数据无法验证，故不纳入「可靠」数据源。

### 离线降级（明确标注）

任何一个源连不上（被墙 / 代理失效 / 未装 pytrends）都会：
- 该源被标记「离线」，其余源继续正常工作；
- 三源全挂时降级为「离线样例」，页面顶部与每张卡片**明确标注「样例」**，绝不冒充实时数据。

---

## 目录结构

```
fashion-trends/
├── backend/
│   ├── app.py             # Flask 应用与 API 路由
│   ├── config.py          # 环境变量 / 密钥 / 代理读取
│   ├── db.py              # SQLite 存储 + 环比计算 + 每源信号
│   ├── trends_source.py   # Google Trends（pytrends）+ 关键词候选池
│   ├── reddit_source.py   # Reddit 社区讨论信号
│   ├── ecommerce_source.py# 电商（Amazon 搜索联想）信号
│   ├── fusion.py          # 多源融合 + 动量 + 起飞预警评分 + 连通性预检
│   ├── llm.py             # 大模型客户端（Claude）+ 模板回退
│   ├── unsplash.py        # Unsplash 图库客户端 + 示例图回退
│   ├── mock_data.py       # 内置示例图（仅未配置 Unsplash 密钥时）
│   ├── palette.py         # 色值 → 颜色名 / 适配场景
│   ├── service.py         # 更新流水线编排 + 派生视图
│   └── scheduler.py       # APScheduler 定时任务
├── frontend/
│   ├── index.html
│   ├── styles.css         # 暗色轻奢杂志风
│   └── app.js
├── run.py                 # 启动入口
├── requirements.txt
├── .env.example           # 环境变量模板
└── README.md
```

---

## 快速开始

**1. 安装依赖（建议虚拟环境）**

```bash
cd fashion-trends
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

**2. 配置（可选）**

```bash
cp .env.example .env   # Windows: copy .env.example .env
```

**3. 启动**

```bash
python run.py
```

打开 <http://127.0.0.1:8000>。

---

## 如何拿到「实时数据」

三个数据源都在国外，需要代理：

```ini
# .env
TRENDS_PROXY=http://127.0.0.1:7890   # 你的 Clash/V2Ray 本地代理端口
TRENDS_TIMEFRAME=today 3-m           # Google Trends 时间窗
TRENDS_GEO=                          # 留空=全球；可填 US / GB / CN
```

配好代理后点击「刷新趋势」，页面顶部三个来源会依次变「实时」，卡片出现金色「实时」标签与「近月涨跌」。

> 注意：请确认代理客户端已真正「连接」到国外节点（浏览器能打开 google.com），否则仍会降级为离线。部分 VPN 的「游戏/大陆加速」节点无法访问 Google。

### 申请 Unsplash Access Key（免费，真实匹配图片）

1. 打开 <https://unsplash.com/developers> 注册/登录；
2. **Your apps → New application**，同意 API 条款；
3. 复制 **Access Key** 填入 `.env` 的 `UNSPLASH_ACCESS_KEY`（免费约 50 次/小时）。

### 申请大模型密钥（可选，Claude / Anthropic）

1. 打开 <https://console.anthropic.com> 创建 API Key；
2. 填入 `.env` 的 `ANTHROPIC_API_KEY`。

配置后编辑部内容（风格标签、色值、总结）由 Claude 实时生成，否则用内置模板。

---

## 定时任务配置

```ini
SCHEDULE_MODE=daily      # daily / weekly / off
SCHEDULE_TIME=03:00
SCHEDULE_WEEKDAY=mon     # weekly 时生效
SCHEDULE_TZ=Asia/Shanghai
```

前端「刷新趋势」按钮异步触发一次全自动更新（立即返回，轮询完成后刷新页面）。

---

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 前端首页 |
| GET | `/api/status` | 状态（数据来源存活、定时计划、最近更新） |
| GET | `/api/trends` | 最近一期趋势（含 `signals` 每源明细 / `alert` 预警） |
| GET | `/api/forecast` | 早期预警：按动量排序 + 预警等级 + 置信度 |
| GET | `/api/feed` | 业务结构化信号流（JSON） |
| GET | `/api/feed.csv` | 业务信号流 CSV 导出 |
| GET | `/api/colors` | 整套流行配色 |
| GET | `/api/elements` | 元素热度排行（三栏） |
| GET | `/api/report` | Markdown 完整趋势报告 |
| POST | `/api/refresh` | 手动异步触发一次全自动更新 |

---

## 技术要点

- **多源采集**：三个采集器各自独立、可单独降级，入口 `fusion.collect_all` 先做连通性预检（4s 超时），网络不可达时跳过该源而非逐关键词卡死。
- **融合评分**：热度按权重（Google 0.5 / Reddit 0.3 / 电商 0.2）加权，缺失源自动重归一化；动量取有涨跌数据的源加权。
- **起飞预警**：`fusion.fuse` 输出 `alert ∈ {takeoff, hot, watch, steady, cooling}` 与 `confidence`（存活源数）。
- **大模型标准化 JSON**：`llm.py` 约束 Claude 输出「趋势名称、状态、风格标签、hex 色值、廓形、流行元素、面料、总结、stock_search_keyword」。
- **环比与每源明细**：SQLite 按 `period` 存快照，自动算 `mom`；`signals` 列存每源真实信号便于对账。
- **图片版权署名**：真实模式保存摄影师姓名/用户名/主页链接；演示模式标注「示意配图」。
