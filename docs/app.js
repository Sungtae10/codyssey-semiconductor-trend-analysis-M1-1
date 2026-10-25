/* 삼성전자 트렌드 탐색기
   - 데이터: data/dashboard-data.js (python -m src.run_all 이 만든다)
   - 계산 방식은 src/metrics.py 와 같다: 출발값 = 시작일 직전 거래일 종가,
     변동성 = 기간 내 하루 수익률의 표본 표준편차 × √252, 최대 낙폭 = 출발일부터 끝날까지 경로에서 계산. */
(function () {
  "use strict";

  const D = window.DASHBOARD_DATA;
  const dates = D.dates;
  const COLS = D.cols;
  const TD = D.meta.trading_days_per_year;
  const A_START = D.meta.analysis_start;
  const A_END = D.meta.analysis_end;

  const SERIES = {
    SEC: { name: "삼성전자", close: "sec_close", ret: "sec_ret", ma: "sec_ma", vol: "sec_vol20", mcap: "sec_mcap_tr", color: "--sec", unit: "원" },
    SKH: { name: "SK하이닉스", close: "skh_close", ret: "skh_ret", ma: "skh_ma", vol: "skh_vol20", mcap: "skh_mcap_tr", color: "--skh", unit: "원" },
    KOSPI: { name: "KOSPI(재계산)", close: "kospi_level", ret: "kospi_ret", ma: "kospi_ma", vol: "kospi_vol20", color: "--kospi", unit: "pt" },
  };
  const ORDER = ["SEC", "SKH", "KOSPI"];
  const METRIC_TITLES = {
    cum: "누적 수익률",
    price: "주가와 이동평균",
    dd: "고점 대비 낙폭",
    vol: "20일 변동성(연환산)",
    corr: "삼성전자와 함께 움직인 정도(60일 상관계수)",
    share: "KOSPI 시가총액 중 두 회사 비중",
  };
  const METRIC_NOTES = {
    cum: "시작일 직전 거래일 종가를 100으로 맞춘 값입니다. 로그 눈금에서는 같은 높이 차이가 같은 비율의 변화를 뜻합니다.",
    price: "종목마다 단위가 달라 한 축에 겹치지 않고 위아래로 나눴습니다(삼성전자·SK하이닉스는 원, KOSPI는 포인트). 회색 선은 이동평균입니다.",
    dd: "선택한 기간 안에서 '그날까지의 최고 종가'보다 몇 % 아래에 있는지 보여 줍니다. 0%는 신고가입니다.",
    vol: "최근 20거래일 하루 수익률의 표준편차를 연환산(√252)한 값입니다. 기간을 바꿔도 계산 창은 20거래일로 같습니다.",
    corr: "최근 60거래일 하루 수익률의 상관계수입니다. SK하이닉스를 고르면 삼성전자와 SK하이닉스, KOSPI를 고르면 삼성전자와 '나머지 시장'(KOSPI에서 두 종목을 뺀 시장)의 상관을 그립니다.",
    share: "KOSPI 전체 시가총액(우선주 포함)에서 두 회사 보통주가 차지하는 비중입니다. 쌓은 영역의 맨 위가 두 종목 합계입니다.",
  };

  const state = {
    start: A_START, end: A_END, preset: "all", metric: "cum",
    series: new Set(ORDER), log: true, events: true, ma: new Set([60, 120]),
    monthly: "SEC", showTable: false,
  };

  // ------------------------------------------------------------ 작은 도구
  const $ = (sel) => document.querySelector(sel);
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const nf1 = new Intl.NumberFormat("ko-KR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const nf2 = new Intl.NumberFormat("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const nf0 = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 });
  const fmtPct = (v, sign = true) => (v === null || !isFinite(v)) ? "없음" : (sign && v > 0 ? "+" : "") + nf1.format(v) + "%";
  const fmtDate = (s) => { const [y, m, d] = s.split("-"); return `${y}.${+m}.${+d}`; };
  const fmtValue = (k, v) => k === "KOSPI" ? nf2.format(v) : nf0.format(v) + "원";
  const fmtTimes = (v) => (v >= 10 ? nf1.format(v) : v >= 1 ? nf1.format(v) : nf2.format(v)) + "배";

  function lowerBound(day) { // 첫 번째 dates[i] >= day
    let lo = 0, hi = dates.length;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (dates[mid] < day) lo = mid + 1; else hi = mid; }
    return lo;
  }
  function upperBound(day) { // 마지막 dates[i] <= day
    let lo = 0, hi = dates.length;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (dates[mid] <= day) lo = mid + 1; else hi = mid; }
    return lo - 1;
  }
  function addMonths(day, months) {
    const d = new Date(day + "T00:00:00Z");
    d.setUTCMonth(d.getUTCMonth() + months);
    return d.toISOString().slice(0, 10);
  }
  function addDays(day, n) {
    const d = new Date(day + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  }
  const clampDay = (day) => (day < A_START ? A_START : day > A_END ? A_END : day);

  function currentRange() {
    const s = Math.max(lowerBound(state.start), lowerBound(A_START));
    const e = Math.min(upperBound(state.end), upperBound(A_END));
    return { s, e, b: s - 1, ok: s <= e && s >= 1 };
  }

  // ------------------------------------------------------------ 통계 (metrics.py 와 같은 정의)
  function stats(key, s, e) {
    const S = SERIES[key];
    const close = COLS[S.close], ret = COLS[S.ret];
    const b = s - 1;
    const r = ret.slice(s, e + 1);
    const n = r.length;
    const mean = r.reduce((a, x) => a + x, 0) / n;
    const sd = n > 1 ? Math.sqrt(r.reduce((a, x) => a + (x - mean) * (x - mean), 0) / (n - 1)) : NaN;
    let peak = close[b], peakIdx = b, mdd = 0, mddPeak = b, mddTrough = b;
    for (let i = b; i <= e; i++) {
      if (close[i] > peak) { peak = close[i]; peakIdx = i; }
      const dd = close[i] / peak - 1;
      if (dd < mdd) { mdd = dd; mddTrough = i; mddPeak = peakIdx; }
    }
    let hi = -Infinity, hiIdx = s, lo = Infinity, loIdx = s;
    for (let i = s; i <= e; i++) {
      if (close[i] > hi) { hi = close[i]; hiIdx = i; }
      if (close[i] < lo) { lo = close[i]; loIdx = i; }
    }
    return {
      baseIdx: b, endIdx: e, base: close[b], end: close[e],
      returnPct: (close[e] / close[b] - 1) * 100,
      volPct: sd * Math.sqrt(TD),
      mddPct: mdd * 100, mddPeak, mddTrough,
      high: hi, highIdx: hiIdx, low: lo, lowIdx: loIdx,
      upRatio: r.filter((x) => x > 0).length / n * 100,
      n,
    };
  }

  function corr(a, b) {
    const n = a.length;
    const ma = a.reduce((s, x) => s + x, 0) / n, mb = b.reduce((s, x) => s + x, 0) / n;
    let sab = 0, saa = 0, sbb = 0;
    for (let i = 0; i < n; i++) { const da = a[i] - ma, db = b[i] - mb; sab += da * db; saa += da * da; sbb += db * db; }
    return sab / Math.sqrt(saa * sbb);
  }

  // ------------------------------------------------------------ 읽어 주는 문장과 숫자 표
  function renderReadout(range) {
    const out = $("#readout-text");
    const note = $("#readout-note");
    out.textContent = "";
    if (!range.ok) { out.textContent = "선택한 기간에 거래일이 없습니다. 시작일과 끝날을 다시 골라 주세요."; note.textContent = ""; return; }
    const keys = ORDER.filter((k) => state.series.has(k));
    if (!keys.length) { out.textContent = "종목을 하나 이상 골라 주세요."; note.textContent = ""; return; }
    out.append(`${fmtDate(dates[range.b])} 종가에서 ${fmtDate(dates[range.e])}까지 `);
    keys.forEach((k, i) => {
      const st = stats(k, range.s, range.e);
      const who = document.createElement("span");
      who.className = "who";
      const key = document.createElement("span");
      key.className = "key key-" + k.toLowerCase();
      key.setAttribute("aria-hidden", "true");
      who.append(key, SERIES[k].name + "는 ");
      out.append(who);
      const strong = document.createElement("b");
      strong.textContent = `${fmtTimes(st.end / st.base)}(${fmtPct(st.returnPct)})`;
      out.append(strong);
      out.append(i < keys.length - 1 ? ", " : "가 됐습니다.");
    });
    note.textContent = "출발값은 시작일 바로 전 거래일 종가입니다. 배당은 빼고 가격만으로 계산했습니다.";
  }

  function renderKpi(range) {
    const tbody = $("#kpi-table tbody");
    tbody.textContent = "";
    const note = $("#kpi-note");
    if (!range.ok) { note.textContent = ""; return; }
    note.textContent = `거래일 ${range.e - range.s + 1}일 · 변동성은 기간 안 하루 수익률 표준편차 × √${TD}, 최대 낙폭은 출발일부터 끝날까지의 경로로 계산합니다.`;
    const secRet = COLS.sec_ret.slice(range.s, range.e + 1);
    ORDER.filter((k) => state.series.has(k)).forEach((k) => {
      const st = stats(k, range.s, range.e);
      const tr = document.createElement("tr");
      const cells = [];
      const nameCell = document.createElement("td");
      const key = document.createElement("span");
      key.className = "key key-" + k.toLowerCase();
      key.setAttribute("aria-hidden", "true");
      nameCell.append(key, SERIES[k].name);
      cells.push(nameCell);
      const add = (main, sub) => {
        const td = document.createElement("td");
        td.append(main);
        if (sub) { const s = document.createElement("span"); s.className = "sub"; s.textContent = sub; td.append(s); }
        cells.push(td);
      };
      add(`${fmtValue(k, st.base)} → ${fmtValue(k, st.end)}`, `${fmtDate(dates[st.baseIdx])} → ${fmtDate(dates[st.endIdx])}`);
      add(fmtPct(st.returnPct));
      add(fmtPct(st.volPct, false));
      add(fmtPct(st.mddPct), st.mddPct < 0 ? `${fmtDate(dates[st.mddPeak])} → ${fmtDate(dates[st.mddTrough])}` : "하락 없음");
      add(fmtValue(k, st.high), fmtDate(dates[st.highIdx]));
      add(fmtValue(k, st.low), fmtDate(dates[st.lowIdx]));
      add(fmtPct(st.upRatio, false));
      if (k === "SEC") add("기준");
      else add(nf2.format(corr(secRet, COLS[SERIES[k].ret].slice(range.s, range.e + 1))));
      tr.append(...cells);
      tbody.append(tr);
    });
  }

  // ------------------------------------------------------------ 그래프
  function baseLayout() {
    return {
      paper_bgcolor: css("--surface"), plot_bgcolor: css("--surface"),
      font: { family: css("--font"), size: 13, color: css("--ink-2") },
      margin: { l: 70, r: 20, t: 52, b: 78 },
      hovermode: "x unified",
      hoverlabel: { bgcolor: css("--surface"), bordercolor: css("--line"), font: { color: css("--ink"), size: 13, family: css("--font") } },
      showlegend: true,
      legend: { orientation: "h", x: 0, y: -0.13, yanchor: "top", font: { color: css("--ink"), size: 13 } },
      xaxis: {
        type: "date", showgrid: false, linecolor: css("--axis"), tickcolor: css("--axis"), ticks: "outside",
        tickformatstops: [
          { dtickrange: [null, 86400000 * 25], value: "%-m.%-d" },
          { dtickrange: [86400000 * 25, null], value: "%Y.%-m" },
        ],
        hoverformat: "%Y.%-m.%-d", showspikes: true, spikemode: "across",
        spikethickness: 1, spikecolor: css("--axis"), spikedash: "solid", spikesnap: "cursor",
      },
      shapes: [], annotations: [],
    };
  }
  function yAxis(extra) {
    return Object.assign({ gridcolor: css("--grid"), zeroline: false, linecolor: css("--axis"), automargin: true, tickfont: { color: css("--ink-2") } }, extra || {});
  }
  // 로그 눈금 숫자: Plotly 기본값은 1,000 다음 눈금을 '2, 3, 4'처럼 앞자리만 적어 2,000인지 알기 어렵다.
  // 값의 폭이 3배 이상이면 정해 둔 눈금(× 10ⁿ)만 전체 숫자로 적는다. 폭이 15배 이상이면 1·2·3·5, 그보다 좁으면
  // 1·1.5·2·3·4·5·7로 촘촘히 둔다. 폭이 3배보다 좁으면 Plotly 기본값(전체 숫자로 나온다)을 쓴다.
  function logTicks(values) {
    let lo = Infinity, hi = -Infinity;
    values.forEach((v) => { if (v > 0 && isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; } });
    if (!(hi / lo >= 3)) return {};
    const mults = hi / lo >= 15 ? [1, 2, 3, 5] : [1, 1.5, 2, 3, 4, 5, 7];
    const vals = [];
    for (let p = Math.floor(Math.log10(lo)); p <= Math.ceil(Math.log10(hi)); p++) {
      mults.forEach((m) => { const t = m * Math.pow(10, p); if (t >= lo * 0.9 && t <= hi * 1.1) vals.push(t); });
    }
    return { tickmode: "array", tickvals: vals, ticktext: vals.map((t) => nf0.format(t)) };
  }
  function line(name, x, y, colorVar, extra) {
    return Object.assign({
      type: "scatter", mode: "lines", name, x, y,
      line: { color: css(colorVar), width: 2 }, hovertemplate: "%{y:,.1f}",
    }, extra || {});
  }

  function eventMarks(layout, range) {
    if (!state.events) return;
    const first = dates[range.b], last = dates[range.e];
    const spanDays = (Date.parse(last) - Date.parse(first)) / 86400000;
    const near = Math.max(3, spanDays / 40);   // 이보다 가까운 사건끼리는 번호 높이를 엇갈린다
    let prev = null, level = 0;
    D.events.forEach((ev, i) => {
      if (ev.date < first || ev.date > last) return;
      level = prev && (Date.parse(ev.date) - Date.parse(prev)) / 86400000 < near ? (level + 1) % 3 : 0;
      prev = ev.date;
      layout.shapes.push({ type: "line", xref: "x", yref: "paper", x0: ev.date, x1: ev.date, y0: 0, y1: 1, line: { color: css("--axis"), width: 1 } });
      layout.annotations.push({
        xref: "x", yref: "paper", x: ev.date, y: 1, yanchor: "bottom", yshift: 2 + level * 14, showarrow: false,
        text: String(i + 1), font: { size: 11, color: css("--muted") },
        hovertext: `${fmtDate(ev.date)} ${ev.title}`, hoverlabel: { bgcolor: css("--surface") },
      });
    });
  }

  function buildFigure(range) {
    const layout = baseLayout();
    const traces = [];
    const keys = ORDER.filter((k) => state.series.has(k));
    const xs = dates.slice(range.b, range.e + 1);
    const m = state.metric;

    if (m === "cum") {
      keys.forEach((k) => {
        const c = COLS[SERIES[k].close], base = c[range.b];
        traces.push(line(SERIES[k].name, xs, c.slice(range.b, range.e + 1).map((v) => (v / base) * 100), SERIES[k].color));
      });
      layout.yaxis = yAxis(Object.assign({ type: state.log ? "log" : "linear", tickformat: ",.0f", title: { text: "출발값 = 100", font: { size: 12 } } },
        state.log ? logTicks(traces.flatMap((t) => t.y)) : {}));
      layout.shapes.push({ type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: 100, y1: 100, line: { color: css("--axis"), width: 1 } });
    } else if (m === "price") {
      const n = keys.length || 1;
      const gap = 0.06;
      const h = (1 - gap * (n - 1)) / n;
      keys.forEach((k, i) => {
        const S = SERIES[k];
        const axisName = i === 0 ? "y" : "y" + (i + 1);
        const layoutKey = i === 0 ? "yaxis" : "yaxis" + (i + 1);
        const top = 1 - i * (h + gap);
        const shown = [COLS[S.close]].concat([20, 60, 120].filter((w) => state.ma.has(w)).map((w) => COLS[S.ma + w]))
          .flatMap((c) => c.slice(range.b, range.e + 1));
        layout[layoutKey] = yAxis(Object.assign({
          domain: [top - h, top], type: state.log ? "log" : "linear",
          title: { text: `${S.name} (${S.unit})`, font: { size: 12 } },
          tickformat: ",.0f",
        }, state.log ? logTicks(shown) : {}));
        const fmt = k === "KOSPI" ? "%{y:,.2f}" : "%{y:,.0f}원";
        traces.push(line(S.name, xs, COLS[S.close].slice(range.b, range.e + 1), S.color, { yaxis: axisName, hovertemplate: fmt, line: { color: css(S.color), width: 1.6 } }));
        const shades = { 20: "--ma20", 60: "--ma60", 120: "--ma120" };
        [20, 60, 120].filter((w) => state.ma.has(w)).forEach((w) => {
          traces.push(line(`${S.name} ${w}일 이동평균`, xs, COLS[S.ma + w].slice(range.b, range.e + 1), shades[w],
            { yaxis: axisName, hovertemplate: fmt, line: { color: css(shades[w]), width: w === 120 ? 2 : 1.5 }, showlegend: i === 0, legendgroup: "ma" + w, name: `${w}일 이동평균` }));
        });
      });
      if (!keys.length) layout.yaxis = yAxis();
    } else if (m === "dd") {
      keys.forEach((k) => {
        const c = COLS[SERIES[k].close];
        let peak = c[range.b];
        const y = [];
        for (let i = range.b; i <= range.e; i++) { if (c[i] > peak) peak = c[i]; y.push((c[i] / peak - 1) * 100); }
        traces.push(line(SERIES[k].name, xs, y, SERIES[k].color, { hovertemplate: "%{y:.1f}%" }));
      });
      layout.yaxis = yAxis({ ticksuffix: "%", title: { text: "고점 대비 (%)", font: { size: 12 } } });
      layout.shapes.push({ type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: 0, y1: 0, line: { color: css("--axis"), width: 1 } });
    } else if (m === "vol") {
      const vx = dates.slice(range.s, range.e + 1);
      keys.forEach((k) => {
        traces.push(line(SERIES[k].name, vx, COLS[SERIES[k].vol].slice(range.s, range.e + 1), SERIES[k].color, { hovertemplate: "%{y:.1f}%" }));
      });
      layout.yaxis = yAxis({ ticksuffix: "%", rangemode: "tozero", title: { text: "연환산 변동성 (%)", font: { size: 12 } } });
    } else if (m === "corr") {
      const vx = dates.slice(range.s, range.e + 1);
      if (state.series.has("SKH")) traces.push(line("삼성전자 ↔ SK하이닉스", vx, COLS.corr60_sec_skh.slice(range.s, range.e + 1), "--skh", { hovertemplate: "%{y:.2f}" }));
      if (state.series.has("KOSPI")) traces.push(line("삼성전자 ↔ 나머지 시장", vx, COLS.corr60_sec_ex2.slice(range.s, range.e + 1), "--kospi", { hovertemplate: "%{y:.2f}" }));
      layout.yaxis = yAxis({ range: [-0.2, 1.05], title: { text: "상관계수", font: { size: 12 } } });
    } else if (m === "share") {
      const vx = dates.slice(range.s, range.e + 1);
      const tot = COLS.kospi_mcap_tr;
      ["SEC", "SKH"].filter((k) => state.series.has(k)).forEach((k) => {
        const mc = COLS[SERIES[k].mcap];
        const y = [];
        for (let i = range.s; i <= range.e; i++) y.push((mc[i] / tot[i]) * 100);
        const col = css(SERIES[k].color);
        traces.push(line(SERIES[k].name, vx, y, SERIES[k].color, {
          stackgroup: "share", fillcolor: hexToRgba(col, 0.25), line: { color: col, width: 1.6 }, hovertemplate: "%{y:.1f}%",
        }));
      });
      layout.yaxis = yAxis({ ticksuffix: "%", rangemode: "tozero", title: { text: "KOSPI 시가총액 중 (%)", font: { size: 12 } } });
    }
    eventMarks(layout, range);
    return { traces, layout };
  }

  function hexToRgba(hex, a) {
    const h = hex.replace("#", "");
    const v = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
    const n = parseInt(v, 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  }

  let lastFigure = null;
  function renderChart(range) {
    $("#chart-title").textContent = METRIC_TITLES[state.metric];
    let note = METRIC_NOTES[state.metric];
    if (state.metric === "corr" && !state.series.has("SKH") && !state.series.has("KOSPI")) note += " 지금은 SK하이닉스와 KOSPI가 모두 꺼져 있어 그릴 선이 없습니다.";
    if (state.metric === "share" && !state.series.has("SEC") && !state.series.has("SKH")) note += " 지금은 두 회사가 모두 꺼져 있어 그릴 영역이 없습니다.";
    $("#chart-note").textContent = note;
    const el = $("#main-chart");
    if (!range.ok) { Plotly.purge(el); lastFigure = null; return; }
    const fig = buildFigure(range);
    lastFigure = fig;
    Plotly.react(el, fig.traces, fig.layout, { responsive: true, displayModeBar: false });
    if (state.showTable) renderChartTable();
  }

  function renderChartTable() {
    const table = $("#chart-table");
    table.textContent = "";
    if (!lastFigure || !lastFigure.traces.length) return;
    const traces = lastFigure.traces;
    const thead = document.createElement("thead");
    const hr = document.createElement("tr");
    ["날짜", ...traces.map((t) => t.name)].forEach((h) => { const th = document.createElement("th"); th.scope = "col"; th.textContent = h; hr.append(th); });
    thead.append(hr);
    const tbody = document.createElement("tbody");
    const index = new Map();
    traces.forEach((t, j) => t.x.forEach((x, i) => { if (!index.has(x)) index.set(x, new Array(traces.length).fill(null)); index.get(x)[j] = t.y[i]; }));
    [...index.keys()].sort().forEach((x) => {
      const tr = document.createElement("tr");
      const td0 = document.createElement("td"); td0.textContent = fmtDate(x); tr.append(td0);
      index.get(x).forEach((v) => { const td = document.createElement("td"); td.textContent = v === null || v === undefined ? "" : nf2.format(v); tr.append(td); });
      tbody.append(tr);
    });
    table.append(thead, tbody);
  }

  // ------------------------------------------------------------ 월별 수익률 표
  function mix(c1, c2, t) {
    const p = (c) => { const n = parseInt(c.replace("#", ""), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
    const a = p(c1), b = p(c2);
    return `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(",")})`;
  }
  function monthlyReturns(key) {
    const close = COLS[SERIES[key].close];
    const lastOfMonth = new Map(); // "YYYY-MM" -> index
    const firstOfMonth = new Map();
    for (let i = 0; i < dates.length; i++) {
      const ym = dates[i].slice(0, 7);
      lastOfMonth.set(ym, i);
      if (!firstOfMonth.has(ym)) firstOfMonth.set(ym, i);
    }
    const months = [...lastOfMonth.keys()].sort();
    const out = [];
    for (let j = 1; j < months.length; j++) {
      const ym = months[j];
      if (ym < A_START.slice(0, 7)) continue;
      const prev = lastOfMonth.get(months[j - 1]), cur = lastOfMonth.get(ym);
      out.push({ ym, ret: (close[cur] / close[prev] - 1) * 100, first: dates[firstOfMonth.get(ym)], last: dates[cur] });
    }
    return out;
  }
  function renderMonthly(range) {
    const table = $("#monthly-table");
    table.textContent = "";
    const rows = monthlyReturns(state.monthly);
    const years = [...new Set(rows.map((r) => r.ym.slice(0, 4)))];
    const thead = document.createElement("thead");
    const hr = document.createElement("tr");
    ["연도", ...Array.from({ length: 12 }, (_, i) => `${i + 1}월`)].forEach((h) => { const th = document.createElement("th"); th.scope = "col"; th.textContent = h; hr.append(th); });
    thead.append(hr);
    const tbody = document.createElement("tbody");
    const up = css("--up"), down = css("--down"), mid = css("--neutral");
    const first = range.ok ? dates[range.s] : A_START, last = range.ok ? dates[range.e] : A_END;
    years.forEach((y) => {
      const tr = document.createElement("tr");
      const th = document.createElement("th"); th.scope = "row"; th.textContent = y; tr.append(th);
      for (let mth = 1; mth <= 12; mth++) {
        const ym = `${y}-${String(mth).padStart(2, "0")}`;
        const r = rows.find((x) => x.ym === ym);
        const td = document.createElement("td");
        if (!r) { td.className = "empty"; td.textContent = ""; tr.append(td); continue; }
        const t = Math.min(Math.abs(r.ret) / 30, 1);
        td.style.background = r.ret >= 0 ? mix(mid, up, t) : mix(mid, down, t);
        td.style.color = t >= 0.6 ? "#ffffff" : css("--ink");
        td.className = "cell" + (r.last < first || r.first > last ? " out" : "");
        const partial = ym === A_END.slice(0, 7);
        td.textContent = (r.ret > 0 ? "+" : "") + nf1.format(r.ret) + (partial ? "*" : "");
        td.title = `${y}년 ${mth}월 ${fmtPct(r.ret)}${partial ? " (" + fmtDate(A_END) + "까지)" : ""}`;
        tr.append(td);
      }
      tbody.append(tr);
    });
    table.append(thead, tbody);
  }

  // ------------------------------------------------------------ 사건 목록
  function renderEvents() {
    const ol = $("#event-list");
    ol.textContent = "";
    D.events.forEach((ev) => {
      const li = document.createElement("li");
      const time = document.createElement("time");
      time.dateTime = ev.date; time.textContent = fmtDate(ev.date);
      const what = document.createElement("div");
      what.className = "what";
      const b = document.createElement("b"); b.textContent = ev.title;
      const p = document.createElement("p"); p.textContent = ev.detail;
      const a = document.createElement("a"); a.className = "src"; a.href = ev.source_url; a.target = "_blank"; a.rel = "noopener"; a.textContent = "출처: " + ev.source_title;
      what.append(b, p, a);
      const btn = document.createElement("button");
      btn.type = "button"; btn.textContent = "전후 보기";
      btn.addEventListener("click", () => {
        setRange(clampDay(addDays(ev.date, -60)), clampDay(addDays(ev.date, 60)), null);
        const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        document.getElementById("chart-title").scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "start" });
      });
      li.append(time, what, btn);
      ol.append(li);
    });
  }

  // ------------------------------------------------------------ 상태 반영
  function syncControls() {
    document.querySelectorAll("#period-presets button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.preset === state.preset)));
    document.querySelectorAll("#metric-buttons button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.metric === state.metric)));
    document.querySelectorAll("#ma-buttons button").forEach((b) => b.setAttribute("aria-pressed", String(state.ma.has(+b.dataset.ma))));
    document.querySelectorAll("#monthly-series button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.series === state.monthly)));
    $("#start-date").value = state.start;
    $("#end-date").value = state.end;
    const maOn = state.metric === "price";
    $("#ma-buttons").classList.toggle("is-disabled", !maOn);
    document.querySelectorAll("#ma-buttons button").forEach((b) => { b.disabled = !maOn; });
    const logOn = state.metric === "cum" || state.metric === "price";
    $("#opt-log").disabled = !logOn;
    $("#opt-log").closest("label").classList.toggle("is-disabled", !logOn);
  }

  function render() {
    syncControls();
    const range = currentRange();
    renderReadout(range);
    renderKpi(range);
    renderChart(range);
    renderMonthly(range);
  }

  function presetRange(p) {
    if (p === "all") return [A_START, A_END];
    if (p === "6m") return [clampDay(addMonths(A_END, -6)), A_END];
    return [clampDay(`${p}-01-01`), clampDay(`${p}-12-31`)];
  }
  function setRange(start, end, preset) {
    state.start = start; state.end = end; state.preset = preset;
    render();
  }

  // ------------------------------------------------------------ 이벤트 연결
  function bind() {
    $("#start-date").min = A_START; $("#start-date").max = A_END;
    $("#end-date").min = A_START; $("#end-date").max = A_END;
    $("#data-ref").textContent = D.meta.data_ref;
    $("#kospi-err").textContent = D.meta.kospi_max_error_pct.toFixed(2);

    $("#period-presets").addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      const [s, t] = presetRange(b.dataset.preset);
      setRange(s, t, b.dataset.preset);
    });
    $("#start-date").addEventListener("change", (e) => { if (e.target.value) setRange(clampDay(e.target.value), state.end, null); });
    $("#end-date").addEventListener("change", (e) => { if (e.target.value) setRange(state.start, clampDay(e.target.value), null); });
    $("#metric-buttons").addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      state.metric = b.dataset.metric; render();
    });
    $("#series-checks").addEventListener("change", (e) => {
      if (e.target.checked) state.series.add(e.target.value); else state.series.delete(e.target.value);
      render();
    });
    $("#opt-log").addEventListener("change", (e) => { state.log = e.target.checked; render(); });
    $("#opt-events").addEventListener("change", (e) => { state.events = e.target.checked; render(); });
    $("#ma-buttons").addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b || b.disabled) return;
      const w = +b.dataset.ma;
      if (state.ma.has(w)) state.ma.delete(w); else state.ma.add(w);
      render();
    });
    $("#monthly-series").addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      state.monthly = b.dataset.series; render();
    });
    $("#table-toggle").addEventListener("click", (e) => {
      state.showTable = !state.showTable;
      e.target.setAttribute("aria-expanded", String(state.showTable));
      e.target.textContent = state.showTable ? "표 닫기" : "표로 보기";
      $("#chart-table-wrap").hidden = !state.showTable;
      if (state.showTable) renderChartTable();
    });
    $("#filters").addEventListener("submit", (e) => e.preventDefault());

    // 밝기: 운영체제 설정을 따르고, 버튼으로 바꾸면 이 브라우저에만 기억한다
    const root = document.documentElement;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const isDark = () => root.dataset.theme ? root.dataset.theme === "dark" : media.matches;
    const label = () => { $("#theme-toggle").textContent = isDark() ? "밝게" : "어둡게"; };
    try { const saved = localStorage.getItem("theme"); if (saved === "dark" || saved === "light") root.dataset.theme = saved; } catch (err) { /* 저장소를 못 쓰면 OS 설정을 따른다 */ }
    label();
    $("#theme-toggle").addEventListener("click", () => {
      root.dataset.theme = isDark() ? "light" : "dark";
      try { localStorage.setItem("theme", root.dataset.theme); } catch (err) { /* 무시 */ }
      label(); render();
    });
    media.addEventListener("change", () => { label(); render(); });
  }

  // 자동 점검용: 전체 기간 숫자가 파이썬 계산과 같은지 (브라우저 콘솔에서 확인 가능)
  window.__dashboardSelfCheck = function () {
    const s = lowerBound(A_START), e = upperBound(A_END);
    const out = {};
    ORDER.forEach((k) => {
      const st = stats(k, s, e);
      const ref = D.check[k];
      out[k] = {
        return_pct: [st.returnPct, ref.return_pct], ann_vol_pct: [st.volPct, ref.ann_vol_pct], mdd_pct: [st.mddPct, ref.mdd_pct],
      };
    });
    return out;
  };

  renderEvents();
  bind();
  render();
})();
