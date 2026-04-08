const state = {
  view: "dashboard",
  heroMode: "integrated",
  search: "",
  selectedPair: null,
  latest: null,
};

const HERO_MODES = {
  integrated: "통합",
  long: "롱",
  short: "숏",
};

function el(id) {
  return document.getElementById(id);
}

function safeNum(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num : 0;
}

function fmtNum(value, digits = 2) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : "-";
}

function fmtMoney(value, digits = 2) {
  const num = Number(value);
  return Number.isFinite(num) ? `${num.toFixed(digits)} USDT` : "-";
}

function fmtPct(value, digits = 2) {
  const num = Number(value);
  return Number.isFinite(num) ? `${num.toFixed(digits)}%` : "-";
}

function fmtText(value) {
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function numberClass(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "value-neutral";
  if (num > 0) return "value-positive";
  if (num < 0) return "value-negative";
  return "value-neutral";
}

function badgeHtml(value, positiveText = "수익", negativeText = "손실") {
  const num = Number(value);
  if (!Number.isFinite(num)) return '<span class="badge warn">정보 없음</span>';
  if (num > 0) return `<span class="badge good">${positiveText}</span>`;
  if (num < 0) return `<span class="badge bad">${negativeText}</span>`;
  return '<span class="badge warn">보합</span>';
}

function renderRows(targetId, rows, emptyText, colSpan = 1) {
  const target = el(targetId);
  if (!target) return;
  if (!rows.length) {
    target.innerHTML = `<tr><td colspan="${colSpan}" class="value-neutral">${escapeHtml(emptyText)}</td></tr>`;
    return;
  }
  target.innerHTML = rows.join("");
}

function filterBySearch(items, accessor) {
  const query = state.search.trim().toLowerCase();
  if (!query) return items;
  return items.filter((item) => accessor(item).toLowerCase().includes(query));
}

function linePath(points, mapX, mapY, key) {
  return points
    .map((point, index) => {
      const x = mapX(index);
      const y = mapY(safeNum(point[key]));
      return `${index === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");
}

function areaPath(points, mapX, mapY, key, baselineY) {
  if (!points.length) return "";
  const startX = mapX(0);
  const endX = mapX(points.length - 1);
  return `${linePath(points, mapX, mapY, key)} L ${endX} ${baselineY} L ${startX} ${baselineY} Z`;
}

function chartLabels(points, width, left, bottomY, maxLabels = 5) {
  if (!points.length) return "";
  const count = Math.min(maxLabels, points.length);
  const step = Math.max(Math.floor((points.length - 1) / Math.max(count - 1, 1)), 1);
  const indices = [];
  for (let index = 0; index < points.length; index += step) indices.push(index);
  if (indices[indices.length - 1] !== points.length - 1) indices.push(points.length - 1);
  return indices
    .slice(0, maxLabels + 1)
    .map((index) => {
      const point = points[index];
      const x = left + (points.length === 1 ? width / 2 : (index / (points.length - 1)) * width);
      return `<text x="${x}" y="${bottomY}" fill="rgba(236,247,241,0.56)" font-size="11" text-anchor="middle">${escapeHtml(point.x)}</text>`;
    })
    .join("");
}

function renderLineChart(targetId, points, options = {}) {
  const target = el(targetId);
  if (!target) return;
  if (!points.length) {
    target.innerHTML = '<div class="chart-empty">표시할 전적 데이터가 아직 없습니다.</div>';
    return;
  }

  const primaryKey = options.primaryKey || "cumulative_profit_abs_usd";
  const secondaryKey = options.secondaryKey || null;
  const primaryColor = options.primaryColor || "#1de1a1";
  const secondaryColor = options.secondaryColor || "#ffb84d";
  const width = 920;
  const height = options.height || 340;
  const padding = { top: 18, right: 22, bottom: 34, left: 54 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const values = points.map((point) => safeNum(point[primaryKey]));
  if (secondaryKey) points.forEach((point) => values.push(safeNum(point[secondaryKey])));
  values.push(0);
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const span = max - min;
  min -= span * 0.08;
  max += span * 0.08;

  const mapX = (index) => (points.length === 1 ? padding.left + chartWidth / 2 : padding.left + (index / (points.length - 1)) * chartWidth);
  const mapY = (value) => padding.top + ((max - value) / (max - min)) * chartHeight;
  const zeroY = mapY(0);
  const grid = Array.from({ length: 5 }, (_, idx) => {
    const value = min + ((max - min) / 4) * idx;
    const y = mapY(value);
    return `
      <line x1="${padding.left}" y1="${y}" x2="${padding.left + chartWidth}" y2="${y}" stroke="rgba(255,255,255,0.06)" stroke-width="1" />
      <text x="${padding.left - 10}" y="${y + 4}" fill="rgba(236,247,241,0.56)" font-size="11" text-anchor="end">${escapeHtml(fmtNum(value, 2))}</text>
    `;
  }).join("");

  const primaryLine = linePath(points, mapX, mapY, primaryKey);
  const primaryArea = areaPath(points, mapX, mapY, primaryKey, zeroY);
  const secondaryLine = secondaryKey ? linePath(points, mapX, mapY, secondaryKey) : "";
  const lastPoint = points[points.length - 1];
  const lastX = mapX(points.length - 1);
  const lastY = mapY(safeNum(lastPoint[primaryKey]));

  target.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" width="100%" height="100%" preserveAspectRatio="none" role="img" aria-label="${escapeHtml(options.label || "전적 그래프")}">
      <defs>
        <linearGradient id="${targetId}_fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${primaryColor}" stop-opacity="0.34" />
          <stop offset="100%" stop-color="${primaryColor}" stop-opacity="0.02" />
        </linearGradient>
      </defs>
      ${grid}
      <line x1="${padding.left}" y1="${zeroY}" x2="${padding.left + chartWidth}" y2="${zeroY}" stroke="rgba(255,255,255,0.08)" stroke-width="1.2" />
      <path d="${primaryArea}" fill="url(#${targetId}_fill)"></path>
      <path d="${primaryLine}" fill="none" stroke="${primaryColor}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"></path>
      ${secondaryKey ? `<path d="${secondaryLine}" fill="none" stroke="${secondaryColor}" stroke-width="2.2" stroke-dasharray="8 8" stroke-linecap="round" stroke-linejoin="round"></path>` : ""}
      <circle cx="${lastX}" cy="${lastY}" r="5.5" fill="${primaryColor}" stroke="rgba(18,23,21,0.96)" stroke-width="3"></circle>
      ${chartLabels(points, chartWidth, padding.left, height - 10)}
    </svg>
  `;
}

function renderComparisonBars(targetId, rows) {
  const target = el(targetId);
  if (!target) return;
  if (!rows.length) {
    target.innerHTML = '<div class="chart-empty">비교할 전적이 없습니다.</div>';
    return;
  }
  const normalized = rows.map((row) => ({
    ...row,
    ratio: row.max > 0 ? Math.max(6, Math.min(100, (Math.abs(safeNum(row.value)) / row.max) * 100)) : 0,
  }));
  target.innerHTML = normalized.map((row) => `
    <div class="bar-row">
      <div class="bar-row-head">
        <span>${escapeHtml(row.label)}</span>
        <strong class="${row.className || numberClass(row.value)}">${escapeHtml(row.display)}</strong>
      </div>
      <div class="bar-track">
        <div class="bar-fill" style="width:${row.ratio}%; background:${row.color || "linear-gradient(90deg, var(--accent-2), var(--accent))"};"></div>
      </div>
    </div>
  `).join("");
}

function setActiveView(view) {
  state.view = view;
  document.querySelectorAll(".side-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  document.querySelectorAll(".view-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.panel === view);
  });
}

function renderTopSummary(status, dashboard) {
  const overview = dashboard.overview || {};
  el("sidebar_mode").innerHTML = status.mode?.dry_run ? '<span class="badge warn">DRY</span>' : '<span class="badge good">LIVE</span>';
  el("sidebar_updated").textContent = formatDateTime(status.generated_at);
  el("header_balance").textContent = fmtMoney(overview.remaining_balance_usd, 2);
  el("header_today_profit").innerHTML = `<span class="${numberClass(overview.today_profit_abs_usd)}">${fmtMoney(overview.today_profit_abs_usd, 2)}</span>`;
  el("header_today_roi").innerHTML = `<span class="${numberClass(overview.today_roi_pct)}">${fmtPct(overview.today_roi_pct, 2)}</span>`;
  el("header_engine").textContent = status.engine?.strategy || "전략 정보 없음";
  el("header_model_note").textContent = `${fmtText(status.engine?.freqai_model)} · ${fmtText(status.engine?.llm_model)} · 기준선 ${fmtText(overview.baseline_label)}`;

  el("summary_total_win_rate").innerHTML = `<span class="${numberClass(overview.total_win_rate_pct - 50)}">${fmtPct(overview.total_win_rate_pct, 2)}</span>`;
  el("summary_total_win_rate_hint").textContent = "기준선 이후 닫힌 거래 승률";
  el("summary_balance").textContent = fmtMoney(overview.remaining_balance_usd, 2);
  el("summary_balance_hint").textContent = `가용 ${fmtMoney(overview.available_balance_usd, 2)}`;
  el("summary_today_profit").innerHTML = `<span class="${numberClass(overview.today_profit_abs_usd)}">${fmtMoney(overview.today_profit_abs_usd, 2)}</span>`;
  el("summary_today_profit_hint").textContent = `오늘 닫힌 거래 ${fmtText(overview.today_closed_trades)}건`;
  el("summary_today_roi").innerHTML = `<span class="${numberClass(overview.today_roi_pct)}">${fmtPct(overview.today_roi_pct, 2)}</span>`;
  el("summary_today_roi_hint").textContent = "오늘 기준 ROI";
  el("summary_total_profit").innerHTML = `<span class="${numberClass(overview.total_profit_abs_usd)}">${fmtMoney(overview.total_profit_abs_usd, 2)}</span>`;
  el("summary_total_profit_hint").textContent = `기준선 ${fmtText(overview.baseline_label)}`;
  el("summary_total_fee").textContent = fmtMoney(dashboard.performance?.overall?.fees_abs_usd, 2);
  el("summary_total_fee_hint").textContent = `오늘 수수료 ${fmtMoney(overview.today_fees_abs_usd, 2)}`;
}

function renderMarketCards(cards) {
  const target = el("market_cards");
  const filtered = filterBySearch(cards, (item) => `${item.asset} ${item.pair} ${item.symbol}`);
  if (!filtered.length) {
    target.innerHTML = '<div class="chart-empty" style="min-height:98px;">조건에 맞는 코인 카드가 없습니다.</div>';
    return;
  }
  target.innerHTML = filtered.map((item) => `
    <article class="market-card ${item.selected ? "active" : ""}">
      <div class="market-card-top">
        <div style="display:flex; gap:10px; align-items:center;">
          <div class="coin-badge">${escapeHtml(item.asset.slice(0, 2))}</div>
          <div>
            <h3>${escapeHtml(item.asset)}</h3>
            <small>${escapeHtml(item.symbol || item.pair)}</small>
          </div>
        </div>
        ${safeNum(item.abs_change_pct) >= 0 ? '<span class="badge good">상승</span>' : '<span class="badge bad">하락</span>'}
      </div>
      <div class="market-price">${escapeHtml(fmtNum(item.last_price, safeNum(item.last_price) >= 100 ? 2 : 4))}</div>
      <div class="market-meta">
        <span class="${numberClass(item.abs_change_pct)}">변동 ${escapeHtml(fmtPct(item.abs_change_pct, 2))}</span>
        <span>품질 ${escapeHtml(fmtPct(item.quality_score_pct, 1))}</span>
      </div>
    </article>
  `).join("");
}

function renderLivePositions(status) {
  const target = el("live_positions_strip");
  const caption = el("live_positions_caption");
  if (!target || !caption) return;

  const positions = filterBySearch(status.live_positions || status.open_positions || [], (item) => `${item.pair} ${item.side} ${item.enter_tag} ${item.recovery_summary}`);
  const totalNet = positions.reduce((sum, item) => sum + safeNum(item.net_profit_abs), 0);
  const totalRoi = positions.reduce((sum, item) => sum + safeNum(item.roi_pct), 0);

  caption.innerHTML = `현재 ${fmtText(positions.length)}건 / 평가손익 <span class="${numberClass(totalNet)}">${fmtMoney(totalNet, 2)}</span> / 합산 ROI <span class="${numberClass(totalRoi)}">${fmtPct(totalRoi, 2)}</span>`;

  if (!positions.length) {
    target.innerHTML = '<div class="chart-empty" style="min-height:72px;">현재 열린 포지션이 없습니다.</div>';
    return;
  }

  target.innerHTML = positions.map((item) => {
    const tpValue = item.tp_mode === "recovery" && item.recovery_tp_target_pct !== null && item.recovery_tp_target_pct !== undefined
      ? fmtPct(item.recovery_tp_target_pct, 2)
      : fmtPct(item.base_tp_target_pct, 2);
    const tpLabel = item.tp_mode === "recovery" ? "Recovery TP" : "Base TP";
    const sideLabel = item.side === "long" ? "LONG" : "SHORT";
    return `
      <article class="position-card">
        <div class="position-cell position-symbol">
          <strong>${escapeHtml(fmtText(item.pair))}</strong>
          <small>${escapeHtml(formatDateTime(item.open_date))}</small>
        </div>
        <div class="position-cell position-side-cell">
          ${item.side === "long" ? '<span class="badge good">LONG</span>' : '<span class="badge bad">SHORT</span>'}
        </div>
        <div class="position-cell position-pnl-compact">
          <span class="label">평가손익</span>
          <strong class="${numberClass(item.net_profit_abs)}">${escapeHtml(fmtMoney(item.net_profit_abs, 2))}</strong>
          <small class="${numberClass(item.roi_pct)}">${escapeHtml(fmtPct(item.roi_pct, 2))}</small>
        </div>
        <div class="position-cell position-inline">
          <span class="label">진입가 / 현재가</span>
          <strong>${escapeHtml(fmtNum(item.open_rate, 4))} → ${escapeHtml(fmtNum(item.current_rate, 4))}</strong>
          <small>${escapeHtml(sideLabel)} 포지션</small>
        </div>
        <div class="position-cell position-inline">
          <span class="label">진입금 / 레버리지</span>
          <strong>${escapeHtml(fmtMoney(item.stake_amount, 2))}</strong>
          <small>${escapeHtml(fmtText(item.leverage))}x</small>
        </div>
        <div class="position-cell position-inline">
          <span class="label">${escapeHtml(tpLabel)}</span>
          <strong>${escapeHtml(tpValue)}</strong>
          <small>${escapeHtml(fmtText(item.tp_mode || "base"))}</small>
        </div>
        <div class="position-cell position-inline">
          <span class="label">Recovery</span>
          <strong>${escapeHtml(fmtText(item.recovery_summary || "-"))}</strong>
          <small>${escapeHtml(fmtText(item.enter_tag || "-"))}</small>
        </div>
      </article>
    `;
  }).join("");
}

function buildPerformanceCard(title, stats) {
  return `
    <section class="performance-card">
      <header>
        <strong>${escapeHtml(title)}</strong>
        ${badgeHtml(stats.net_profit_abs_usd)}
      </header>
      <div class="meta">
        <span>승률 <strong class="${numberClass(stats.win_rate_pct - 50)}">${escapeHtml(fmtPct(stats.win_rate_pct, 2))}</strong></span>
        <span>순손익 <strong class="${numberClass(stats.net_profit_abs_usd)}">${escapeHtml(fmtMoney(stats.net_profit_abs_usd, 2))}</strong></span>
        <span>수수료 <strong>${escapeHtml(fmtMoney(stats.fees_abs_usd, 2))}</strong></span>
        <span>평균 ROI <strong class="${numberClass(stats.avg_roi_pct)}">${escapeHtml(fmtPct(stats.avg_roi_pct, 2))}</strong></span>
        <span>닫힌 거래 <strong>${escapeHtml(fmtText(stats.closed_trades))}</strong></span>
        <span>PF <strong>${escapeHtml(fmtNum(stats.profit_factor, 2))}</strong></span>
      </div>
    </section>
  `;
}

function renderPerformanceSummary(dashboard) {
  const performance = dashboard.performance || {};
  const overall = performance.overall || {};
  const longStats = performance.long || {};
  const shortStats = performance.short || {};
  el("performance_cards").innerHTML = [
    buildPerformanceCard("통합", overall),
    buildPerformanceCard("롱", longStats),
    buildPerformanceCard("숏", shortStats),
  ].join("");

  const maxProfit = Math.max(Math.abs(safeNum(overall.net_profit_abs_usd)), Math.abs(safeNum(longStats.net_profit_abs_usd)), Math.abs(safeNum(shortStats.net_profit_abs_usd)), 1);
  const maxFees = Math.max(safeNum(overall.fees_abs_usd), safeNum(longStats.fees_abs_usd), safeNum(shortStats.fees_abs_usd), 1);
  renderComparisonBars("performance_compare", [
    { label: "통합 승률", value: overall.win_rate_pct, display: fmtPct(overall.win_rate_pct, 2), max: 100 },
    { label: "롱 승률", value: longStats.win_rate_pct, display: fmtPct(longStats.win_rate_pct, 2), max: 100, color: "linear-gradient(90deg, #49d3ff, #1de1a1)" },
    { label: "숏 승률", value: shortStats.win_rate_pct, display: fmtPct(shortStats.win_rate_pct, 2), max: 100, color: "linear-gradient(90deg, #ffb84d, #1de1a1)" },
    { label: "통합 순손익", value: overall.net_profit_abs_usd, display: fmtMoney(overall.net_profit_abs_usd, 2), max: maxProfit, className: numberClass(overall.net_profit_abs_usd) },
    { label: "롱 순손익", value: longStats.net_profit_abs_usd, display: fmtMoney(longStats.net_profit_abs_usd, 2), max: maxProfit, className: numberClass(longStats.net_profit_abs_usd), color: "linear-gradient(90deg, #49d3ff, #1de1a1)" },
    { label: "숏 순손익", value: shortStats.net_profit_abs_usd, display: fmtMoney(shortStats.net_profit_abs_usd, 2), max: maxProfit, className: numberClass(shortStats.net_profit_abs_usd), color: "linear-gradient(90deg, #ffb84d, #1de1a1)" },
    { label: "통합 수수료", value: overall.fees_abs_usd, display: fmtMoney(overall.fees_abs_usd, 2), max: maxFees, className: "value-neutral", color: "linear-gradient(90deg, #7f8f87, #d6e6dd)" },
  ]);

  const bestTrade = overall.best_trade || {};
  const worstTrade = overall.worst_trade || {};
  el("performance_highlights").innerHTML = `
    <div class="highlight-item">
      <span>최고 거래</span>
      <strong class="${numberClass(bestTrade.net_profit_abs)}">${escapeHtml(fmtText(bestTrade.pair))} / ${escapeHtml(fmtMoney(bestTrade.net_profit_abs, 2))}</strong>
    </div>
    <div class="highlight-item">
      <span>최저 거래</span>
      <strong class="${numberClass(worstTrade.net_profit_abs)}">${escapeHtml(fmtText(worstTrade.pair))} / ${escapeHtml(fmtMoney(worstTrade.net_profit_abs, 2))}</strong>
    </div>
    <div class="highlight-item">
      <span>누적 Profit Factor</span>
      <strong>${escapeHtml(fmtNum(overall.profit_factor, 2))}</strong>
    </div>
  `;
}

function currentHeroSeries(dashboard) {
  const charts = dashboard.charts || {};
  if (state.heroMode === "long") return charts.long_curve || [];
  if (state.heroMode === "short") return charts.short_curve || [];
  return charts.integrated_curve || [];
}

function currentHeroStats(dashboard) {
  const performance = dashboard.performance || {};
  if (state.heroMode === "long") return performance.long || {};
  if (state.heroMode === "short") return performance.short || {};
  return performance.overall || {};
}

function renderHero(dashboard) {
  const series = currentHeroSeries(dashboard);
  const stats = currentHeroStats(dashboard);
  el("hero_subtitle").textContent = `${HERO_MODES[state.heroMode]} 기준 누적 잔고 / 누적 손익 흐름입니다.`;
  renderLineChart("hero_chart", series, {
    label: `${HERO_MODES[state.heroMode]} 누적 곡선`,
    primaryKey: "cumulative_balance_usd",
    secondaryKey: "cumulative_profit_abs_usd",
    primaryColor: "#1de1a1",
    secondaryColor: "#ffb84d",
    height: 360,
  });
  el("hero_stat_profit").innerHTML = `<span class="${numberClass(stats.net_profit_abs_usd)}">${fmtMoney(stats.net_profit_abs_usd, 2)}</span>`;
  el("hero_stat_fee").textContent = fmtMoney(stats.fees_abs_usd, 2);
  el("hero_stat_win_rate").innerHTML = `<span class="${numberClass(stats.win_rate_pct - 50)}">${fmtPct(stats.win_rate_pct, 2)}</span>`;
  el("hero_legend").innerHTML = `
    <span class="legend-item"><span class="legend-swatch" style="background:#1de1a1;"></span>누적 잔고</span>
    <span class="legend-item"><span class="legend-swatch" style="background:#ffb84d;"></span>누적 손익</span>
  `;
  el("hero_caption_left").textContent = series.length ? `마지막 체결 ${series[series.length - 1].x} / 거래 ${series.length}건` : "체결 없음";
  el("hero_caption_right").textContent = `현재 보기 ${HERO_MODES[state.heroMode]} / PF ${fmtNum(stats.profit_factor, 2)} / 평균 ROI ${fmtPct(stats.avg_roi_pct, 2)}`;
}

function renderTodayCharts(dashboard) {
  const charts = dashboard.charts || {};
  const todaySeries = charts.today_intraday || [];
  const dailySeries = charts.daily_profit || [];
  renderLineChart("today_chart", todaySeries, {
    label: "오늘 손익 흐름",
    primaryKey: "cumulative_profit_abs_usd",
    secondaryKey: "cumulative_fee_abs_usd",
    primaryColor: "#1de1a1",
    secondaryColor: "#ff6d82",
    height: 300,
  });
  const todayStats = dashboard.today || {};
  el("today_caption_left").textContent = `오늘 닫힌 거래 ${fmtText(todayStats.closed_trades)}건 / 승률 ${fmtPct(todayStats.win_rate_pct, 2)}`;
  el("today_caption_right").textContent = `오늘 손익 ${fmtMoney(todayStats.net_profit_abs_usd, 2)} / 수수료 ${fmtMoney(todayStats.fees_abs_usd, 2)}`;
  renderLineChart("daily_chart", dailySeries, {
    label: "일별 손익 / 수수료",
    primaryKey: "net_profit_abs_usd",
    secondaryKey: "fees_abs_usd",
    primaryColor: "#1de1a1",
    secondaryColor: "#a7b7ae",
    height: 300,
  });
  el("daily_caption_left").textContent = `리셋 이후 일별 집계 ${fmtText(dailySeries.length)}일`;
  const totalDailyProfit = dailySeries.reduce((sum, item) => sum + safeNum(item.net_profit_abs_usd), 0);
  el("daily_caption_right").textContent = `누적 일별 손익 ${fmtMoney(totalDailyProfit, 2)}`;
}

function renderRecentTrades(status) {
  const trades = filterBySearch(status.recent_closed || [], (item) => `${item.pair} ${item.side} ${item.exit_reason} ${item.enter_tag}`);
  const rows = trades.slice(0, 20).map((item) => `
    <tr>
      <td class="mono">${escapeHtml(fmtText(item.id))}</td>
      <td>${escapeHtml(fmtText(item.pair))}</td>
      <td>${escapeHtml(item.side === "long" ? "롱" : "숏")}</td>
      <td>${escapeHtml(formatDateTime(item.open_date))}</td>
      <td>${escapeHtml(formatDateTime(item.close_date))}</td>
      <td>${escapeHtml(fmtNum(item.open_rate, 4))}</td>
      <td>${escapeHtml(fmtNum(item.close_rate, 4))}</td>
      <td>${escapeHtml(fmtMoney(item.stake_amount, 2))}</td>
      <td class="${numberClass(item.gross_profit_abs)}">${escapeHtml(fmtMoney(item.gross_profit_abs, 2))}</td>
      <td>${escapeHtml(fmtMoney(item.fee_total_abs, 2))}</td>
      <td class="${numberClass(item.net_profit_abs)}">${escapeHtml(fmtMoney(item.net_profit_abs, 2))}</td>
      <td class="${numberClass(item.profit_pct)}">${escapeHtml(fmtPct(item.profit_pct, 2))}</td>
      <td class="value-positive">${escapeHtml(fmtPct(item.max_tp_pct, 2))}</td>
      <td class="value-negative">${escapeHtml(fmtPct(item.max_sl_pct, 2))}</td>
      <td>${escapeHtml(fmtText(item.exit_reason))}</td>
      <td>${escapeHtml(fmtText(item.enter_tag))}</td>
    </tr>
  `);
  renderRows("recent_trades_body", rows, "표시할 최근 전적이 없습니다.", 16);
}

function ensureSelectedPair(pairs) {
  const filtered = filterBySearch(pairs, (item) => item.pair);
  if (!filtered.length) {
    state.selectedPair = null;
    return null;
  }
  if (!state.selectedPair || !filtered.some((item) => item.pair === state.selectedPair)) {
    state.selectedPair = filtered[0].pair;
  }
  return filtered.find((item) => item.pair === state.selectedPair) || filtered[0];
}

function renderPairs(dashboard) {
  const details = dashboard.pairs?.detail || [];
  const filtered = filterBySearch(details, (item) => `${item.pair} ${item.asset}`);
  const pairSelect = el("pair_select");
  pairSelect.innerHTML = filtered.map((item) => `
    <option value="${escapeHtml(item.pair)}" ${item.pair === state.selectedPair ? "selected" : ""}>${escapeHtml(item.pair)}</option>
  `).join("");
  const selected = ensureSelectedPair(details);
  if (state.selectedPair) {
    pairSelect.value = state.selectedPair;
  }

  const rows = filtered.map((item) => `
    <tr>
      <td>${escapeHtml(item.pair)}</td>
      <td>${escapeHtml(fmtText(item.stats.closed_trades))}</td>
      <td>${escapeHtml(fmtText(item.stats.wins))}</td>
      <td>${escapeHtml(fmtText(item.stats.losses))}</td>
      <td class="${numberClass(item.stats.win_rate_pct - 50)}">${escapeHtml(fmtPct(item.stats.win_rate_pct, 2))}</td>
      <td class="${numberClass(item.stats.net_profit_abs_usd)}">${escapeHtml(fmtMoney(item.stats.net_profit_abs_usd, 2))}</td>
      <td>${escapeHtml(fmtMoney(item.stats.fees_abs_usd, 2))}</td>
      <td class="${numberClass(item.stats.avg_roi_pct)}">${escapeHtml(fmtPct(item.stats.avg_roi_pct, 2))}</td>
      <td class="value-positive">${escapeHtml(fmtPct(item.stats.avg_max_tp_pct, 2))}</td>
      <td class="value-negative">${escapeHtml(fmtPct(item.stats.avg_max_sl_pct, 2))}</td>
    </tr>
  `);
  renderRows("pair_table_body", rows, "조건에 맞는 코인별 전적이 없습니다.", 10);

  if (!selected) {
    el("pair_chart").innerHTML = '<div class="chart-empty">선택 가능한 코인이 없습니다.</div>';
    el("pair_metrics").innerHTML = "";
    el("pair_legend").innerHTML = "";
    return;
  }

  renderLineChart("pair_chart", selected.series || [], {
    label: `${selected.pair} 누적 그래프`,
    primaryKey: "cumulative_profit_abs_usd",
    secondaryKey: "cumulative_fee_abs_usd",
    primaryColor: "#1de1a1",
    secondaryColor: "#ffb84d",
    height: 360,
  });
  el("pair_legend").innerHTML = `
    <span class="legend-item"><span class="legend-swatch" style="background:#1de1a1;"></span>누적 손익</span>
    <span class="legend-item"><span class="legend-swatch" style="background:#ffb84d;"></span>누적 수수료</span>
  `;
  const metrics = [
    ["총 거래", fmtText(selected.stats.closed_trades)],
    ["승률", fmtPct(selected.stats.win_rate_pct, 2), numberClass(selected.stats.win_rate_pct - 50)],
    ["순손익", fmtMoney(selected.stats.net_profit_abs_usd, 2), numberClass(selected.stats.net_profit_abs_usd)],
    ["수수료", fmtMoney(selected.stats.fees_abs_usd, 2)],
    ["평균 ROI", fmtPct(selected.stats.avg_roi_pct, 2), numberClass(selected.stats.avg_roi_pct)],
    ["평균 최대 TP", fmtPct(selected.stats.avg_max_tp_pct, 2), "value-positive"],
    ["평균 최대 SL", fmtPct(selected.stats.avg_max_sl_pct, 2), "value-negative"],
    ["롱 / 숏", `${fmtText(selected.stats.long_trades)} / ${fmtText(selected.stats.short_trades)}`],
  ];
  el("pair_metrics").innerHTML = metrics.map(([label, value, className]) => `
    <div class="pair-metric">
      <span>${escapeHtml(label)}</span>
      <strong class="${className || "value-neutral"}">${escapeHtml(value)}</strong>
    </div>
  `).join("");
}

function stageCardHtml(label, stage) {
  const pass = safeNum(stage?.pass_count);
  const blocked = safeNum(stage?.blocked_count);
  const passedPairs = Array.isArray(stage?.passed_pairs) && stage.passed_pairs.length ? stage.passed_pairs.join(", ") : "없음";
  const blockedPairs = Array.isArray(stage?.blocked_pairs) && stage.blocked_pairs.length
    ? stage.blocked_pairs.map((item) => `${item.pair} (${item.reason})`).join(" / ")
    : "없음";
  return `
    <article class="filter-stage-card">
      <div class="title">${escapeHtml(label)}</div>
      <strong>${escapeHtml(`${pass} 통과 / ${blocked} 차단`)}</strong>
      <div class="detail">통과: ${escapeHtml(passedPairs)}</div>
      <div class="detail">차단: ${escapeHtml(blockedPairs)}</div>
    </article>
  `;
}

function renderFilters(status, dashboard) {
  const stages = status.pipeline?.stages || {};
  el("pipeline_stage_cards").innerHTML = [
    stageCardHtml("전략", stages.strategy),
    stageCardHtml("ML", stages.ml),
    stageCardHtml("DL", stages.dl),
    stageCardHtml("LLM", stages.llm),
  ].join("");

  const records = filterBySearch(dashboard.pipeline_filter?.records || [], (item) => `${item.pair} ${item.side} ${item.blocked_stage} ${item.blocked_reason} ${item.enter_tag} ${item.llm_signal}`);
  const rows = records.map((item) => `
    <tr>
      <td>${escapeHtml(item.pair)}</td>
      <td>${escapeHtml(item.side === "long" ? "롱" : item.side === "short" ? "숏" : "-")}</td>
      <td>${item.strategy_pass ? '<span class="badge good">통과</span>' : '<span class="badge bad">차단</span>'}</td>
      <td>${item.ml_pass ? '<span class="badge good">통과</span>' : '<span class="badge bad">차단</span>'}</td>
      <td>${item.dl_pass ? '<span class="badge good">통과</span>' : '<span class="badge bad">차단</span>'}</td>
      <td>${item.llm_pass ? '<span class="badge good">통과</span>' : '<span class="badge bad">차단</span>'}</td>
      <td>${escapeHtml(fmtPct(item.ensemble_prob_pct, 2))}</td>
      <td>${escapeHtml(fmtPct(item.ml_prob_pct, 2))}</td>
      <td>${escapeHtml(fmtPct(item.dl_prob_pct, 2))}</td>
      <td>${escapeHtml(fmtText(item.llm_signal))}</td>
      <td>${escapeHtml(fmtText(item.blocked_stage || "최종 통과"))}</td>
      <td>${escapeHtml(fmtText(item.blocked_reason || "-"))}</td>
      <td>${escapeHtml(fmtText(item.enter_tag || "-"))}</td>
    </tr>
  `);
  renderRows("pipeline_table_body", rows, "표시할 필터 상세가 없습니다.", 13);
}

function renderRecordSummary(status, dashboard) {
  const overall = dashboard.performance?.overall || {};
  const longStats = dashboard.performance?.long || {};
  const shortStats = dashboard.performance?.short || {};
  el("record_baseline").textContent = fmtText(dashboard.overview?.baseline_label);
  el("record_baseline_hint").textContent = `업데이트 ${formatDateTime(status.generated_at)}`;
  el("record_total_trades").textContent = fmtText(overall.closed_trades);
  el("record_total_trades_hint").textContent = `승 ${fmtText(overall.wins)} / 패 ${fmtText(overall.losses)}`;
  el("record_long_trades").textContent = fmtText(longStats.closed_trades);
  el("record_long_trades_hint").textContent = `승률 ${fmtPct(longStats.win_rate_pct, 2)}`;
  el("record_short_trades").textContent = fmtText(shortStats.closed_trades);
  el("record_short_trades_hint").textContent = `승률 ${fmtPct(shortStats.win_rate_pct, 2)}`;
  el("record_active_pairs").textContent = fmtText(dashboard.overview?.active_pairs);
  el("record_active_pairs_hint").textContent = `시장 카드 ${(dashboard.market_cards || []).length}개`;
  el("record_open_positions").textContent = fmtText(dashboard.overview?.open_positions);
  el("record_open_positions_hint").textContent = "현재 오픈 포지션";
}

function bindInteractions() {
  document.querySelectorAll(".side-btn").forEach((button) => {
    button.addEventListener("click", () => setActiveView(button.dataset.view));
  });

  document.querySelectorAll("#hero_mode_switch button").forEach((button) => {
    button.addEventListener("click", () => {
      state.heroMode = button.dataset.heroMode;
      document.querySelectorAll("#hero_mode_switch button").forEach((item) => item.classList.toggle("active", item === button));
      if (state.latest) renderDashboard(state.latest);
    });
  });

  el("global_search").addEventListener("input", (event) => {
    state.search = event.target.value || "";
    if (state.latest) renderAll(state.latest);
  });

  el("pair_select").addEventListener("change", (event) => {
    state.selectedPair = event.target.value || null;
    if (state.latest) renderPairs(state.latest.dashboard || {});
  });
}

function renderDashboard(status) {
  const dashboard = status.dashboard || {};
  renderTopSummary(status, dashboard);
  renderMarketCards(dashboard.market_cards || []);
  renderLivePositions(status);
  renderHero(dashboard);
  renderPerformanceSummary(dashboard);
  renderTodayCharts(dashboard);
  renderRecentTrades(status);
  renderPairs(dashboard);
  renderFilters(status, dashboard);
  renderRecordSummary(status, dashboard);
}

function renderAll(status) {
  state.latest = status;
  renderDashboard(status);
}

async function refresh() {
  const response = await fetch(`/runtime/status.json?ts=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`status.json load failed: ${response.status}`);
  const status = await response.json();
  renderAll(status);
}

bindInteractions();
refresh().catch((error) => {
  console.error(error);
  document.body.insertAdjacentHTML(
    "beforeend",
    `<div style="position:fixed;right:18px;bottom:18px;padding:14px 16px;border-radius:16px;background:rgba(255,109,130,0.16);border:1px solid rgba(255,109,130,0.24);color:#ffd8df;z-index:9999;">대시보드 로딩 실패: ${escapeHtml(error.message)}</div>`
  );
});
setInterval(() => refresh().catch(console.error), 5000);
