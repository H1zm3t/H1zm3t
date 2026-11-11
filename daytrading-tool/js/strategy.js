// Regelwerk: wertet an einer geschlossenen Kerze alle Regeln aus, addiert die
// Gewichte zu einem Score und leitet daraus ein Setup (Long / Short / Abwarten)
// mit Einstieg, Stop und Ziel ab.
(function (root) {
  'use strict';
  const isNode = typeof module === 'object' && module.exports;
  const I = isNode ? require('./indicators.js') : root.DT;
  const P = isNode ? require('./patterns.js') : root.DT;

  // type 'state'   = Umfeld (gilt über viele Kerzen),
  // type 'trigger' = Auslöser (Ereignis an genau dieser Kerze).
  // Ein Setup braucht genug Score UND mindestens einen Auslöser.
  const RULES = [
    { id: 'htf_trend', label: '1h-Trend (EMA 50)', weight: 2, type: 'state' },
    { id: 'ema_trend', label: 'EMA 20 / EMA 50 Trend', weight: 1, type: 'state' },
    { id: 'vwap', label: 'Kurs über/unter VWAP', weight: 1, type: 'state' },
    { id: 'ema_cross', label: 'EMA-Kreuzung 20/50', weight: 2, type: 'trigger' },
    { id: 'rsi', label: 'RSI dreht aus Extrembereich', weight: 2, type: 'trigger' },
    { id: 'macd', label: 'MACD kreuzt Signallinie', weight: 2, type: 'trigger' },
    { id: 'bollinger', label: 'Rückkehr ins Bollinger-Band', weight: 1.5, type: 'trigger' },
    { id: 'hammer', label: 'Hammer', weight: 1.5, type: 'trigger' },
    { id: 'shooting_star', label: 'Shooting Star', weight: 1.5, type: 'trigger' },
    { id: 'engulfing', label: 'Engulfing', weight: 2, type: 'trigger' },
    { id: 'star', label: 'Morning / Evening Star', weight: 2, type: 'trigger' },
    { id: 'breakout', label: 'Ausbruch mit Volumen', weight: 2, type: 'trigger' },
    { id: 'double', label: 'Doppelboden / Doppeltop', weight: 2.5, type: 'trigger' },
    { id: 'head_shoulders', label: 'Schulter-Kopf-Schulter', weight: 2.5, type: 'trigger' },
    { id: 'sr_bounce', label: 'Abpraller an Unterstützung / Widerstand', weight: 1.5, type: 'trigger' },
    { id: 'volume', label: 'Hohes Volumen in Kerzenrichtung', weight: 1, type: 'trigger' },
  ];
  const RULE_MAP = Object.fromEntries(RULES.map((r) => [r.id, r]));

  const DEFAULTS = {
    threshold: 7, // Mindest-Score für ein Setup
    rr: 2, // Chance-Risiko-Verhältnis (Ziel = rr × Stop-Abstand)
    atrMult: 1.5, // Stop-Abstand in ATR
    trendFilter: true, // keine Setups gegen den 1h-Trend
    longOnly: false, // nur Kauf-Setups
    disabled: {}, // { regelId: true } schaltet eine Regel ab
    feePct: 0.1, // Gebühr pro Seite in Prozent (Backtest)
    riskPct: 1, // Risiko pro Trade in Prozent des Kontos (Backtest)
    maxHold: 48, // maximale Haltedauer in Kerzen (Backtest)
  };
  const WARMUP = 60;
  const HTF_MS = 3600000;

  // Trend im Stundenchart je Stundenkerze: +1, -1 oder 0.
  function htfTrendSeries(htf) {
    const closes = htf.map((c) => c.c);
    const e = I.ema(closes, 50);
    return htf.map((c, k) => {
      if (k < 3 || e[k] === null || e[k - 3] === null) return 0;
      if (c.c > e[k] && e[k] > e[k - 3]) return 1;
      if (c.c < e[k] && e[k] < e[k - 3]) return -1;
      return 0;
    });
  }

  // Rechnet alle Indikatoren einmal vor. `htf` sind 1h-Kerzen (darf leer sein).
  function prepare(candles, htf, tfMs) {
    const closes = candles.map((c) => c.c);
    const ctx = {
      candles,
      tfMs,
      ema20: I.ema(closes, 20),
      ema50: I.ema(closes, 50),
      rsi: I.rsi(closes, 14),
      macd: I.macd(closes, 12, 26, 9),
      bb: I.bollinger(closes, 20, 2),
      atr: I.atr(candles, 14),
      vwap: I.vwap(candles),
      volSma: I.sma(candles.map((c) => c.v), 20),
      pivots: P.findPivots(candles, 3, 3),
      htfTrend: new Array(candles.length).fill(0),
    };
    // Jeder Kerze den Trend der letzten Stundenkerze zuordnen, die zum
    // Schluss dieser Kerze bereits fertig war (kein Blick in die Zukunft).
    if (htf && htf.length) {
      const trend = htfTrendSeries(htf);
      let k = -1;
      for (let i = 0; i < candles.length; i++) {
        const closeTime = candles[i].t + tfMs;
        while (k + 1 < htf.length && htf[k + 1].t + HTF_MS <= closeTime) k++;
        ctx.htfTrend[i] = k >= 0 ? trend[k] : 0;
      }
    }
    return ctx;
  }

  function evaluate(ctx, i, options) {
    const o = Object.assign({}, DEFAULTS, options);
    const cs = ctx.candles;
    if (i < WARMUP || i >= cs.length) return null;
    const atr = ctx.atr[i];
    if (!(atr > 0)) return null;
    const c = cs[i];
    const p = cs[i - 1];
    const reasons = [];
    const add = (id, dir, text) => {
      if (!dir || (o.disabled && o.disabled[id])) return;
      const rule = RULE_MAP[id];
      reasons.push({ id, dir, weight: rule.weight, type: rule.type, text });
    };

    // --- Umfeld ---
    const ht = ctx.htfTrend[i];
    add('htf_trend', ht, ht > 0 ? '1h-Trend zeigt aufwärts' : '1h-Trend zeigt abwärts');

    const e20 = ctx.ema20[i];
    const e50 = ctx.ema50[i];
    if (e20 > e50 && c.c > e50) add('ema_trend', 1, 'EMA 20 über EMA 50, Kurs darüber');
    if (e20 < e50 && c.c < e50) add('ema_trend', -1, 'EMA 20 unter EMA 50, Kurs darunter');

    const vw = ctx.vwap[i];
    if (c.c > vw) add('vwap', 1, 'Kurs über dem VWAP');
    if (c.c < vw) add('vwap', -1, 'Kurs unter dem VWAP');

    // --- Auslöser: Indikatoren ---
    const e20p = ctx.ema20[i - 1];
    const e50p = ctx.ema50[i - 1];
    if (e20p <= e50p && e20 > e50) add('ema_cross', 1, 'EMA 20 kreuzt EMA 50 nach oben');
    if (e20p >= e50p && e20 < e50) add('ema_cross', -1, 'EMA 20 kreuzt EMA 50 nach unten');

    const r = ctx.rsi[i];
    const rp = ctx.rsi[i - 1];
    if (rp < 30 && r >= 30) add('rsi', 1, 'RSI dreht aus dem überverkauften Bereich (unter 30) nach oben');
    if (rp > 70 && r <= 70) add('rsi', -1, 'RSI dreht aus dem überkauften Bereich (über 70) nach unten');

    const h = ctx.macd.hist[i];
    const hp = ctx.macd.hist[i - 1];
    if (hp !== null && hp <= 0 && h > 0) add('macd', 1, 'MACD kreuzt die Signallinie nach oben');
    if (hp !== null && hp >= 0 && h < 0) add('macd', -1, 'MACD kreuzt die Signallinie nach unten');

    if (p.c < ctx.bb.lower[i - 1] && c.c > ctx.bb.lower[i]) {
      add('bollinger', 1, 'Kurs kehrt von unten ins Bollinger-Band zurück');
    }
    if (p.c > ctx.bb.upper[i - 1] && c.c < ctx.bb.upper[i]) {
      add('bollinger', -1, 'Kurs kehrt von oben ins Bollinger-Band zurück');
    }

    // --- Auslöser: Kerzenmuster ---
    for (const pat of P.candlePatterns(cs, i)) add(pat.id, pat.dir, 'Kerzenmuster: ' + pat.name);

    // --- Auslöser: Formationen ---
    const highVol = ctx.volSma[i] !== null && c.v > 1.5 * ctx.volSma[i];
    let hh = -Infinity;
    let ll = Infinity;
    for (let k = i - 20; k < i; k++) {
      hh = Math.max(hh, cs[k].h);
      ll = Math.min(ll, cs[k].l);
    }
    if (highVol && c.c > hh) add('breakout', 1, 'Ausbruch über das 20-Kerzen-Hoch mit hohem Volumen');
    if (highVol && c.c < ll) add('breakout', -1, 'Ausbruch unter das 20-Kerzen-Tief mit hohem Volumen');

    const dbl = P.doublePattern(cs, ctx.pivots, i, atr);
    if (dbl) add('double', dbl.dir, dbl.name + ' bestätigt');
    const hs = P.headShoulders(cs, ctx.pivots, i, atr);
    if (hs) add('head_shoulders', hs.dir, hs.name + ': Nackenlinie gebrochen');

    const lv = P.levels(ctx.pivots, i, atr, 300);
    for (const L of lv) {
      if (c.l <= L.price + 0.3 * atr && c.c > L.price && p.c > L.price && c.c > c.o) {
        add('sr_bounce', 1, 'Abpraller an Unterstützung (' + L.touches + ' Berührungen)');
        break;
      }
    }
    for (const L of lv) {
      if (c.h >= L.price - 0.3 * atr && c.c < L.price && p.c < L.price && c.c < c.o) {
        add('sr_bounce', -1, 'Abpraller an Widerstand (' + L.touches + ' Berührungen)');
        break;
      }
    }

    if (highVol) add('volume', Math.sign(c.c - c.o), 'Hohes Volumen in Kerzenrichtung');

    // --- Bewertung ---
    let score = 0;
    for (const x of reasons) score += x.dir * x.weight;
    const hasTrigger = (d) => reasons.some((x) => x.type === 'trigger' && x.dir === d);

    let dir = 0;
    let note = '';
    if (score >= o.threshold && hasTrigger(1)) dir = 1;
    else if (score <= -o.threshold && hasTrigger(-1)) dir = -1;
    else if (Math.abs(score) >= o.threshold) note = 'Umfeld passt, aber kein Auslöser an dieser Kerze';

    if (dir && o.trendFilter && ht === -dir) {
      note = 'Setup verworfen: gegen den 1h-Trend';
      dir = 0;
    }
    if (dir === -1 && o.longOnly) {
      note = 'Short-Setup verworfen: Nur-Long ist aktiv';
      dir = 0;
    }

    const dist = atr * o.atrMult;
    return {
      i,
      t: c.t,
      score,
      dir,
      note,
      reasons,
      atr,
      htfTrend: ht,
      levels: lv,
      entry: c.c,
      stopDist: dist,
      stop: dir ? c.c - dir * dist : null,
      target: dir ? c.c + dir * dist * o.rr : null,
    };
  }

  const api = { RULES, DEFAULTS, WARMUP, prepare, evaluate };
  if (isNode) module.exports = api;
  root.DT = Object.assign(root.DT || {}, api);
})(typeof self !== 'undefined' ? self : globalThis);
