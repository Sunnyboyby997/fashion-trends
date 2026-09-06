/* ==========================================================================
   TENDANCE 前端逻辑：加载数据、渲染三大板块、复制色值、导出报告、手动刷新
   ========================================================================== */

const $ = (sel) => document.querySelector(sel);

const STATUS_META = {
  rising: { label: "🔥 上升", cls: "status-rising", en: "Rising" },
  stable: { label: "📌 平稳", cls: "status-stable", en: "Stable" },
  falling: { label: "📉 衰退", cls: "status-falling", en: "Falling" },
};

const ALERT_META = {
  takeoff: { label: "🚀 起飞", cls: "takeoff" },
  hot: { label: "🔥 火热", cls: "hot" },
  watch: { label: "👀 观察", cls: "watch" },
  steady: { label: "📌 平稳", cls: "steady" },
  cooling: { label: "📉 降温", cls: "cooling" },
};

/* ---------- 工具函数 ---------- */

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`请求失败 ${res.status}`);
  return res.json();
}

function showToast(msg, duration = 2200) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove("show"), duration);
}

function escapeHTML(str) {
  return String(str ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

/* ---------- 渲染：趋势总览 ---------- */

function renderTrends(trends) {
  const grid = $("#trendsGrid");
  grid.innerHTML = trends
    .map((t) => {
      const meta = STATUS_META[t.status] || STATUS_META.stable;

      // 真实数据（is_real）优先展示「近月涨跌」，否则展示数据库跨期「环比」
      let momText, momCls;
      if (t.is_real && t.change_pct != null) {
        const c = Number(t.change_pct) || 0;
        momCls = c > 0.05 ? "up" : c < -0.05 ? "down" : "flat";
        momText = momCls === "flat" ? "近月持平" : `近月 ${c > 0 ? "+" : ""}${c.toFixed(1)}%`;
      } else {
        const mom = Number(t.mom) || 0;
        momCls = mom > 0.05 ? "up" : mom < -0.05 ? "down" : "flat";
        momText = momCls === "flat" ? "环比持平" : `环比 ${mom > 0 ? "+" : ""}${mom.toFixed(1)}%`;
      }
      const realTag = t.is_real
        ? `<span class="real-tag">实时</span>`
        : `<span class="real-tag real-tag--off">样例</span>`;

      const alert = ALERT_META[t.alert] || ALERT_META.steady;
      const alertBadge = `<span class="alert-badge alert--${alert.cls}">${alert.label}</span>`;

      const signals = t.signals || {};
      const confCount = Object.values(signals).filter((s) => s && s.ok).length;
      const confDots = `<span class="conf" title="数据来源 ${confCount}/3">${"●".repeat(confCount)}${"○".repeat(3 - confCount)}</span>`;

      const swatches = (t.hex_colors || [])
        .map((h) => `<span class="swatch" style="background:${escapeHTML(h)}" data-hex="${escapeHTML(h)}" title="${escapeHTML(h)}"></span>`)
        .join("");

      const styleTags = (t.style_tags || [])
        .map((s) => `<span class="tag">${escapeHTML(s)}</span>`)
        .join("");

      const fabricTags = (t.fabrics || [])
        .map((f) => `<span class="tag tag--fabric">${escapeHTML(f)}</span>`)
        .join("");

      const credit = t.image_credit || {};
      const creditLink = credit.link || "https://unsplash.com";
      const demoTag = t.is_demo_image ? `<span class="demo-tag">DEMO</span>` : "";

      return `
        <article class="card">
          <div class="card-media">
            <img src="${escapeHTML(t.image_url || "")}" alt="${escapeHTML(t.name)}" loading="lazy"
                 onerror="this.onerror=null;this.style.display='none';" />
            <span class="status ${meta.cls}">${meta.label}</span>
            <span class="heat-badge">热度 ${escapeHTML(t.heat)}</span>
          </div>
          <div class="card-body">
            <h4 class="card-title">${escapeHTML(t.name)}</h4>
            ${alertBadge}
            ${swatches ? `<div class="swatches">${swatches}</div>` : ""}
            ${styleTags || fabricTags ? `<div class="tags">${styleTags}${fabricTags}</div>` : ""}
            ${t.summary ? `<p class="card-summary">${escapeHTML(t.summary)}</p>` : ""}
            <div class="card-meta">
              <span class="meta-left">
                <span class="mom ${momCls}">${realTag}${momText}</span>
                ${confDots}
              </span>
              <span class="credit">
                📷 <a href="${escapeHTML(creditLink)}" target="_blank" rel="noopener">${escapeHTML(credit.name || "Unsplash")}</a>${demoTag}
              </span>
            </div>
          </div>
        </article>`;
    })
    .join("");

  // 绑定色卡复制事件
  grid.querySelectorAll(".swatch").forEach((el) => {
    el.addEventListener("click", () => copyHex(el.dataset.hex));
  });

  // 卡片入场动画（错峰）
  grid.querySelectorAll(".card").forEach((card, i) => {
    card.style.transitionDelay = `${Math.min(i * 60, 420)}ms`;
    requestAnimationFrame(() => card.classList.add("is-visible"));
  });
}

/* ---------- 渲染：色彩板块 ---------- */

function renderPalette(colors) {
  const wrap = $("#palette");
  if (!colors.length) {
    wrap.innerHTML = `<p class="board-empty">暂无配色数据</p>`;
    return;
  }
  wrap.innerHTML = colors
    .map(
      (c) => `
      <div class="color-chip" data-hex="${escapeHTML(c.hex)}" role="button" tabindex="0" title="复制 ${escapeHTML(c.hex)}">
        <div class="color-swatch" style="background:${escapeHTML(c.hex)}"></div>
        <div class="color-info">
          <div class="color-name">${escapeHTML(c.name)}</div>
          <div class="color-hex">${escapeHTML(c.hex)}</div>
          <div class="color-scene">${escapeHTML(c.scene)} · 出现 ${c.count} 次</div>
        </div>
      </div>`
    )
    .join("");

  wrap.querySelectorAll(".color-chip").forEach((el) => {
    const copy = () => copyHex(el.dataset.hex);
    el.addEventListener("click", copy);
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); copy(); }
    });
  });
}

/* ---------- 渲染：元素热度看板 ---------- */

const BOARD_COLS = [
  { key: "rising", emoji: "🔥", title: "正在崛起", sub: "RISING" },
  { key: "stable", emoji: "📌", title: "热度平稳", sub: "STABLE" },
  { key: "falling", emoji: "📉", title: "热度衰退", sub: "FALLING" },
];

function renderElements(data) {
  const board = $("#elementsBoard");
  board.innerHTML = BOARD_COLS.map((col) => {
    const items = data[col.key] || [];
    const body = items.length
      ? items
          .map(
            (it) => `
            <div class="board-item">
              <div>
                <span class="board-item-name">${escapeHTML(it.name)}</span>
                <span class="board-item-trend">${escapeHTML(it.trend)}</span>
              </div>
              <span class="board-item-heat">${it.heat}</span>
            </div>`
          )
          .join("")
      : `<p class="board-empty">暂无元素</p>`;
    return `
      <div class="board-col board-col--${col.key}">
        <div class="board-col-head">
          <span class="board-emoji">${col.emoji}</span>
          <h4 class="board-col-title">${col.title}</h4>
          <span class="board-col-sub">${col.sub}</span>
        </div>
        ${body}
      </div>`;
  }).join("");
}

/* ---------- 渲染：趋势预测 / 早期预警 ---------- */

function renderForecast(forecast) {
  const list = $("#forecastList");
  if (!forecast.length) {
    list.innerHTML = `<p class="board-empty">暂无预警数据</p>`;
    return;
  }
  list.innerHTML = forecast
    .map((f, i) => {
      const alert = ALERT_META[f.alert] || ALERT_META.steady;
      const change = f.change_pct;
      const momText = change == null ? "—" : `${change > 0 ? "+" : ""}${Number(change).toFixed(1)}%`;
      const momCls = (change || 0) > 0.05 ? "up" : (change || 0) < -0.05 ? "down" : "flat";
      const conf = Number(f.confidence) || 0;
      return `
        <div class="forecast-item">
          <span class="forecast-rank">${String(i + 1).padStart(2, "0")}</span>
          <span class="alert-badge alert--${alert.cls}">${alert.label}</span>
          <span class="forecast-name">${escapeHTML(f.name)}</span>
          <span class="forecast-heat">热度 ${escapeHTML(f.heat ?? 0)}</span>
          <span class="forecast-mom ${momCls}">${momText}</span>
          <span class="conf" title="数据来源 ${conf}/3">${"●".repeat(conf)}${"○".repeat(3 - conf)}</span>
        </div>`;
    })
    .join("");
}

/* ---------- 交互：复制 HEX ---------- */

async function copyHex(hex) {
  try {
    await navigator.clipboard.writeText(hex);
    showToast(`已复制 ${hex} ✓`);
  } catch {
    // 剪贴板不可用时降级方案
    const ta = document.createElement("textarea");
    ta.value = hex;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); showToast(`已复制 ${hex} ✓`); }
    catch { showToast("复制失败，请手动复制"); }
    document.body.removeChild(ta);
  }
}

/* ---------- 交互：导出 Markdown 报告 ---------- */

async function exportReport() {
  try {
    const res = await fetch("/api/report");
    if (!res.ok) throw new Error("报告生成失败");
    const md = await res.text();
    const date = new Date().toISOString().slice(0, 10);
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `fashion-trends-${date}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast("报告已导出 ✓");
  } catch (err) {
    showToast(`导出失败：${err.message}`);
  }
}

/* ---------- 交互：手动刷新 ---------- */

async function refresh() {
  const btn = $("#refreshBtn");
  btn.disabled = true;
  $(".btn-label").textContent = "更新中…";
  showToast("已启动更新，正在抓取多源数据…", 3000);
  try {
    const res = await fetch("/api/refresh", { method: "POST" });
    const data = await res.json();
    if (res.status === 409) {
      showToast("已有更新任务进行中，请稍候");
      return;
    }
    if (!res.ok) {
      showToast(`启动失败：${data.error || res.status}`);
      return;
    }
    await waitForUpdate();
    showToast("更新完成 ✓");
    await loadAll();
    await loadStatus();
  } catch (err) {
    showToast(`刷新失败：${err.message}`);
  } finally {
    btn.disabled = false;
    $(".btn-label").textContent = "刷新趋势";
  }
}

/* 轮询等待后台更新完成（/api/refresh 现在异步返回） */
async function waitForUpdate(timeoutMs = 240000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    await new Promise((r) => setTimeout(r, 1500));
    let s = null;
    try { s = await fetchJSON("/api/status"); } catch { /* 忽略轮询错误 */ }
    if (s && s.last_result && !s.last_result.running) return;
  }
}

/* ---------- 状态栏 ---------- */

async function loadStatus() {
  try {
    const s = await fetchJSON("/api/status");
    $("#lastUpdate").textContent = s.last_update
      ? `最近更新 ${s.last_update} · ${s.schedule.mode === "daily" ? "每日" : s.schedule.mode === "weekly" ? "每周" : "手动"} ${s.schedule.time} 自动刷新`
      : "最近更新 ——";
    $("#demoBadge").hidden = !s.demo;

    // 数据来源状态条：三源各自「实时 / 离线」
    const sources = [
      { key: "google_trends", label: "Google Trends" },
      { key: "reddit", label: "Reddit 社区" },
      { key: "ecommerce", label: "电商信号" },
    ];
    const ok = (s.last_result && s.last_result.sources) || {};
    $("#sources").innerHTML = sources
      .map((src) => {
        const live = !!ok[src.key];
        return `<span class="source-item ${live ? "is-live" : "is-off"}">
          <span class="source-dot"></span>${src.label}
          <em>${live ? "实时" : "离线"}</em>
        </span>`;
      })
      .join("");
  } catch { /* 忽略状态栏错误 */ }
}

/* ---------- 数据加载入口 ---------- */

async function loadAll() {
  const [tData, cData, eData, fData] = await Promise.all([
    fetchJSON("/api/trends"),
    fetchJSON("/api/colors"),
    fetchJSON("/api/elements"),
    fetchJSON("/api/forecast"),
  ]);
  renderTrends(tData.trends || []);
  renderPalette(cData.colors || []);
  renderElements(eData);
  renderForecast(fData.forecast || []);
}

async function init() {
  $("#exportBtn").addEventListener("click", exportReport);
  $("#refreshBtn").addEventListener("click", refresh);

  await loadStatus();
  try {
    await loadAll();
  } catch (err) {
    showToast(`数据加载失败：${err.message}`, 4000);
  }
}

document.addEventListener("DOMContentLoaded", init);
