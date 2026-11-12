// Oberfläche: lädt Kurse, zeichnet den Chart, zeigt das aktuelle Setup und
// startet Backtests. Die Rechenlogik liegt in den anderen Dateien (window.DT).
(function () {
  'use strict';
  const DT = window.DT;
  const LW = window.LightweightCharts;
  const $ = (id) => document.getElementById(id);

  const TF_MS = { '1m': 60000, '5m': 300000, '15m': 900000 };
  const LIVE_CANDLES = 1000;
  const HTF_CANDLES = 500;
  const POLL_MS = 5000;
  const OPTION_KEYS = ['threshold', 'rr', 'atrMult', 'feePct'];
  const FLAG_KEYS = ['trendFilter', 'longOnly'];
  const STORE = 'daytrading-assistent';

  const state = {
    symbol: 'BTCUSDT',
    tf: '5m',
    candles: [],
    htf: [],
    loadId: 0,
    timer: null,
    priceLines: [],
    btStats: null,
    opts: Object.assign({}, DT.DEFAULTS, { disabled: {} }),
  };

  // ---------- Einstellungen merken ----------
  function loadSaved() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORE) || '{}');
      if (saved.opts) Object.assign(state.opts, saved.opts);
      if (TF_MS[saved.tf]) state.tf = saved.tf;
      if (saved.symbol === 'BTCUSDT' || saved.symbol === 'ETHUSDT') state.symbol = saved.symbol;
    } catch (e) {
      /* ohne Speicher geht es mit Standardwerten weiter */
    }
  }
  function save() {
    try {
      const o = state.opts;
      const opts = { disabled: o.disabled };
      for (const k of OPTION_KEYS.concat(FLAG_KEYS)) opts[k] = o[k];
      localStorage.setItem(STORE, JSON.stringify({ opts, tf: state.tf, symbol: state.symbol }));
    } catch (e) {
      /* egal */
    }
  }

  // ---------- Formatierung ----------
  const fmtPrice = (v) => v.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtNum = (v, d) => v.toLocaleString('de-DE', { minimumFractionDigits: d, maximumFractionDigits: d });
  const signed = (v, d) => (v > 0 ? '+' : '') + fmtNum(v, d);
  const fmtTime = (t) => new Date(t).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  // Der Chart kennt keine Zeitzonen: Zeit so verschieben, dass Ortszeit angezeigt wird.
  const chartTime = (t) => Math.floor((t - new Date(t).getTimezoneOffset() * 60000) / 1000);

  // ---------- Charts ----------
  const chartLook = {
    autoSize: true,
    layout: { background: { color: '#161b22' }, textColor: '#8b949e' },
    grid: { vertLines: { color: '#21262d' }, horzLines: { color: '#21262d' } },
    rightPriceScale: { borderColor: '#2a313c' },
    timeScale: { borderColor: '#2a313c', timeVisible: true, secondsVisible: false },
    crosshair: { mode: 0 },
  };
  const chart = LW.createChart($('chart'), chartLook);
  const candleSeries = chart.addCandlestickSeries({
    upColor: '#26a69a',
    downColor: '#ef5350',
    borderVisible: false,
    wickUpColor: '#26a69a',
    wickDownColor: '#ef5350',
  });
  const lineLook = { lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false };
  const ema20Series = chart.addLineSeries(Object.assign({ color: '#f0b90b' }, lineLook));
  const ema50Series = chart.addLineSeries(Object.assign({ color: '#2f81f7' }, lineLook));
  const vwapSeries = chart.addLineSeries(Object.assign({ color: '#b480f0' }, lineLook));
  let equityChart = null;
  let equitySeries = null;

  const toBar = (c) => ({ time: chartTime(c.t), open: c.o, high: c.h, low: c.l, close: c.c });
  const toLine = (candles, values) => {
    const out = [];
    for (let i = 0; i < candles.length; i++) {
      if (values[i] !== null) out.push({ time: chartTime(candles[i].t), value: values[i] });
    }
    return out;
  };

  function setStatus(text, isError) {
    $('status').textContent = text;
    $('status').classList.toggle('error', !!isError);
  }

  // Kerzen, die bereits geschlossen sind (die letzte läuft meist noch).
  function closedCandles() {
    const tfMs = TF_MS[state.tf];
    const cs = state.candles;
    let n = cs.length;
    while (n > 0 && cs[n - 1].t + tfMs > Date.now()) n--;
    return cs.slice(0, n);
  }

  // ---------- Auswertung und Anzeige ----------
  function render(fit) {
    const closed = closedCandles();
    if (closed.length <= DT.WARMUP) return;
    const ctx = DT.prepare(closed, state.htf, TF_MS[state.tf]);

    candleSeries.setData(state.candles.map(toBar));
    ema20Series.setData(toLine(closed, ctx.ema20));
    ema50Series.setData(toLine(closed, ctx.ema50));
    vwapSeries.setData(toLine(closed, ctx.vwap));

    // Pfeile für alle Setups im geladenen Zeitraum (nur der Beginn einer Serie).
    const markers = [];
    let prevDir = 0;
    let current = null;
    for (let i = DT.WARMUP; i < closed.length; i++) {
      const s = DT.evaluate(ctx, i, state.opts);
      if (s.dir && s.dir !== prevDir) {
        markers.push({
          time: chartTime(s.t),
          position: s.dir > 0 ? 'belowBar' : 'aboveBar',
          color: s.dir > 0 ? '#26a69a' : '#ef5350',
          shape: s.dir > 0 ? 'arrowUp' : 'arrowDown',
          text: s.dir > 0 ? 'L' : 'S',
        });
      }
      prevDir = s.dir;
      current = s;
    }
    candleSeries.setMarkers(markers);

    // Waagerechte Linien: Unterstützung/Widerstand, dazu Stop und Ziel.
    for (const pl of state.priceLines) candleSeries.removePriceLine(pl);
    state.priceLines = [];
    const addLine = (price, color, title, style) =>
      state.priceLines.push(
        candleSeries.createPriceLine({ price, color, title, lineWidth: 1, lineStyle: style, axisLabelVisible: !!title })
      );
    const price = state.candles[state.candles.length - 1].c;
    const near = current.levels
      .slice()
      .sort((a, b) => Math.abs(a.price - price) - Math.abs(b.price - price))
      .slice(0, 6);
    for (const L of near) addLine(L.price, '#6e7681', '', 2);
    if (current.dir) {
      addLine(current.stop, '#ef5350', 'Stop', 0);
      addLine(current.target, '#26a69a', 'Ziel', 0);
    }

    renderSignal(current);
    renderPrice();
    if (fit) chart.timeScale().setVisibleLogicalRange({ from: state.candles.length - 150, to: state.candles.length + 5 });
  }

  function renderPrice() {
    const last = state.candles[state.candles.length - 1];
    if (last) $('price').textContent = fmtPrice(last.c);
  }

  function renderSignal(s) {
    const o = state.opts;
    const label = $('sig-label');
    label.className = 'sig-label ' + (s.dir > 0 ? 'long' : s.dir < 0 ? 'short' : 'wait');
    label.textContent = s.dir > 0 ? 'LONG-Setup' : s.dir < 0 ? 'SHORT-Setup' : 'Abwarten';
    $('sig-time').textContent = 'Kerze ' + fmtTime(s.t);

    $('score').textContent = signed(s.score, 1);
    $('score-need').textContent = '(Setup ab ±' + fmtNum(o.threshold, 1) + ' mit Auslöser)';
    const scale = Math.max(10, o.threshold);
    const pct = (Math.min(Math.abs(s.score), scale) / scale) * 50;
    const fill = $('score-fill');
    fill.style.width = pct + '%';
    fill.style.left = s.score >= 0 ? '50%' : 50 - pct + '%';
    fill.style.background = s.score >= 0 ? 'var(--green)' : 'var(--red)';
    $('sig-note').textContent = s.note || '';

    $('plan').hidden = !s.dir;
    if (s.dir) {
      const pctOf = (v) => signed(((v - s.entry) / s.entry) * 100, 2) + ' %';
      $('p-entry').textContent = fmtPrice(s.entry);
      $('p-stop').textContent = fmtPrice(s.stop);
      $('p-stop-pct').textContent = pctOf(s.stop);
      $('p-target').textContent = fmtPrice(s.target);
      $('p-target-pct').textContent = pctOf(s.target);
      // Hin- und Rückgebühr im Verhältnis zum Stop-Abstand.
      const feeShare = ((2 * o.feePct) / 100 / (s.stopDist / s.entry)) * 100;
      $('p-fee').textContent = fmtNum(feeShare, 0) + ' %';
      $('p-fee').className = feeShare > 25 ? 'neg' : '';
    }

    const list = $('reasons');
    list.textContent = '';
    const sorted = s.reasons.slice().sort((a, b) => b.dir * b.weight - a.dir * a.weight);
    for (const r of sorted) {
      const li = document.createElement('li');
      li.className = r.dir > 0 ? 'up' : 'down';
      const w = document.createElement('span');
      w.className = 'w';
      w.textContent = signed(r.dir * r.weight, 1);
      const txt = document.createElement('span');
      txt.textContent = r.text;
      li.append(w, txt);
      list.append(li);
    }
    if (!sorted.length) {
      const li = document.createElement('li');
      li.className = 'muted';
      li.textContent = 'Keine Regel schlägt an.';
      list.append(li);
    }
    $('htf').textContent = s.htfTrend > 0 ? 'aufwärts' : s.htfTrend < 0 ? 'abwärts' : 'neutral';
  }

  // ---------- Daten laden und aktuell halten ----------
  async function loadAll() {
    const id = ++state.loadId;
    clearTimeout(state.timer);
    setStatus('Lade Kurse …');
    try {
      const [candles, htf] = await Promise.all([
        DT.fetchHistory(state.symbol, state.tf, LIVE_CANDLES),
        DT.fetchHistory(state.symbol, '1h', HTF_CANDLES),
      ]);
      if (id !== state.loadId) return;
      state.candles = candles;
      state.htf = htf;
      render(true);
      setStatus('Live · aktualisiert ' + fmtTime(Date.now()));
    } catch (err) {
      if (id !== state.loadId) return;
      setStatus(err.message + ' – neuer Versuch in Kürze', true);
    }
    state.timer = setTimeout(() => poll(id), POLL_MS);
  }

  async function poll(id) {
    if (id !== state.loadId) return;
    try {
      if (!state.candles.length) return loadAll();
      const closedBefore = closedCandles().length;
      const fresh = await DT.fetchKlines(state.symbol, state.tf, 3);
      if (id !== state.loadId) return;
      DT.mergeCandles(state.candles, fresh);
      if (state.candles.length > LIVE_CANDLES + 500) state.candles.splice(0, 500);
      if (closedCandles().length !== closedBefore) {
        // Neue Kerze geschlossen: Stundenkerzen nachziehen und neu bewerten.
        DT.mergeCandles(state.htf, await DT.fetchKlines(state.symbol, '1h', 3));
        if (id !== state.loadId) return;
        render(false);
      } else {
        candleSeries.update(toBar(state.candles[state.candles.length - 1]));
        renderPrice();
      }
      setStatus('Live · aktualisiert ' + fmtTime(Date.now()));
    } catch (err) {
      if (id !== state.loadId) return;
      setStatus(err.message, true);
    }
    state.timer = setTimeout(() => poll(id), POLL_MS);
  }

  // ---------- Backtest ----------
  async function runBacktest() {
    const btn = $('bt-run');
    const status = $('bt-status');
    const days = +$('bt-days').value;
    const tfMs = TF_MS[state.tf];
    const symbol = state.symbol;
    const tf = state.tf;
    btn.disabled = true;
    try {
      const count = Math.ceil((days * 86400000) / tfMs) + 1;
      const candles = await DT.fetchHistory(symbol, tf, count, (p) => {
        status.textContent = 'Lade Kurse … ' + Math.round(p * 100) + ' %';
      });
      // 300 Stunden Vorlauf, damit der 1h-Trend von Anfang an steht.
      const htf = await DT.fetchHistory(symbol, '1h', days * 24 + 300);
      status.textContent = 'Rechne …';
      await new Promise((r) => setTimeout(r, 20));
      const closed = candles.filter((c) => c.t + tfMs <= Date.now());
      const res = DT.runBacktest(closed, htf, tfMs, state.opts);
      state.btStats = res.stats;
      renderBacktest(res, days, symbol, tf);
      status.textContent = '';
    } catch (err) {
      status.textContent = 'Fehler: ' + err.message;
    }
    btn.disabled = false;
  }

  function renderBacktest(res, days, symbol, tf) {
    const s = res.stats;
    $('bt-result').hidden = false;

    const verdict = $('bt-verdict');
    let text;
    let cls = '';
    const head = `${symbol}, ${tf}-Kerzen, ${days} Tage: `;
    if (s.trades < 30) {
      text = head + `nur ${s.trades} Trades. Das sind zu wenige für eine belastbare Aussage.`;
    } else if (s.avgR > 0) {
      cls = 'good';
      text = head + `im Testzeitraum nach Gebühren im Plus (Ø ${signed(s.avgR, 2)} R pro Trade). ` +
        'Das ist keine Garantie für die Zukunft; prüfe auch andere Zeiträume.';
    } else {
      cls = 'bad';
      text = head + `im Testzeitraum nach Gebühren im Minus (Ø ${signed(s.avgR, 2)} R pro Trade` +
        (s.avgRGross > 0 ? `, vor Gebühren ${signed(s.avgRGross, 2)} R). Die Gebühren fressen den Vorteil auf.` : ').');
    }
    verdict.className = 'verdict ' + cls;
    verdict.textContent = text;

    const tiles = [
      ['Trades', String(s.trades), ''],
      ['Trefferquote', fmtNum(s.winRate * 100, 1) + ' %', ''],
      ['Ø Ergebnis je Trade', signed(s.avgR, 2) + ' R', s.avgR],
      ['Ø vor Gebühren', signed(s.avgRGross, 2) + ' R', s.avgRGross],
      ['Profit-Faktor', isFinite(s.profitFactor) ? fmtNum(s.profitFactor, 2) : '∞', s.profitFactor - 1],
      ['Kontoverlauf', signed(s.returnPct, 1) + ' %', s.returnPct],
      ['Größter Rückgang', '−' + fmtNum(s.maxDrawdownPct, 1) + ' %', ''],
      ['Kaufen und Halten', signed(s.buyHoldPct, 1) + ' %', s.buyHoldPct],
    ];
    const box = $('bt-tiles');
    box.textContent = '';
    for (const [k, v, sign] of tiles) {
      const el = document.createElement('div');
      el.className = 'tile';
      const kEl = document.createElement('div');
      kEl.className = 'k';
      kEl.textContent = k;
      const vEl = document.createElement('div');
      vEl.className = 'v' + (sign === '' ? '' : sign > 0 ? ' pos' : sign < 0 ? ' neg' : '');
      vEl.textContent = v;
      el.append(kEl, vEl);
      box.append(el);
    }

    if (!equityChart) {
      equityChart = LW.createChart($('equity'), chartLook);
      equitySeries = equityChart.addLineSeries({ color: '#2f81f7', lineWidth: 2, priceLineVisible: false });
    }
    equitySeries.setData(res.curve.map((p) => ({ time: chartTime(p.t), value: (p.equity - 1) * 100 })));
    equityChart.timeScale().fitContent();
    renderRules();
  }

  // ---------- Regel-Tabelle ----------
  function renderRules() {
    const body = $('rules').querySelector('tbody');
    body.textContent = '';
    for (const rule of DT.RULES) {
      const tr = document.createElement('tr');
      const st = state.btStats && state.btStats.byRule[rule.id];
      const box = document.createElement('input');
      box.type = 'checkbox';
      box.checked = !state.opts.disabled[rule.id];
      box.setAttribute('aria-label', rule.label);
      box.addEventListener('change', () => {
        if (box.checked) delete state.opts.disabled[rule.id];
        else state.opts.disabled[rule.id] = true;
        save();
        render(false);
      });
      const cells = [
        box,
        rule.label + (rule.type === 'state' ? ' (Umfeld)' : ''),
        fmtNum(rule.weight, 1),
        st ? String(st.n) : '–',
        st ? fmtNum((st.wins / st.n) * 100, 0) + ' %' : '–',
        st ? signed(st.sumR / st.n, 2) : '–',
      ];
      cells.forEach((cell, k) => {
        const td = document.createElement('td');
        td.append(cell);
        if (k === 5 && st) td.className = st.sumR > 0 ? 'pos' : 'neg';
        tr.append(td);
      });
      body.append(tr);
    }
  }

  // ---------- Start ----------
  function init() {
    loadSaved();
    $('symbol').value = state.symbol;
    $('tf').value = state.tf;
    for (const k of OPTION_KEYS) {
      const el = $('o-' + k);
      el.value = state.opts[k];
      el.addEventListener('change', () => {
        const v = parseFloat(el.value);
        if (isFinite(v) && v >= +el.min && v <= +el.max) state.opts[k] = v;
        el.value = state.opts[k];
        save();
        render(false);
      });
    }
    for (const k of FLAG_KEYS) {
      const el = $('o-' + k);
      el.checked = !!state.opts[k];
      el.addEventListener('change', () => {
        state.opts[k] = el.checked;
        save();
        render(false);
      });
    }
    const reload = () => {
      state.symbol = $('symbol').value;
      state.tf = $('tf').value;
      state.btStats = null;
      $('bt-result').hidden = true;
      renderRules();
      save();
      loadAll();
    };
    $('symbol').addEventListener('change', reload);
    $('tf').addEventListener('change', reload);
    $('bt-run').addEventListener('click', runBacktest);
    renderRules();
    loadAll();
  }

  init();
})();
