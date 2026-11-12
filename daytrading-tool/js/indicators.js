// Technische Indikatoren. Alle Funktionen liefern Arrays in der Länge der
// Eingabe; solange ein Indikator noch nicht "eingeschwungen" ist, steht null.
// Kerzenformat überall: { t: Öffnungszeit in ms, o, h, l, c, v }
(function (root) {
  'use strict';

  function sma(values, n) {
    const out = new Array(values.length).fill(null);
    let sum = 0;
    for (let i = 0; i < values.length; i++) {
      sum += values[i];
      if (i >= n) sum -= values[i - n];
      if (i >= n - 1) out[i] = sum / n;
    }
    return out;
  }

  // EMA, gestartet mit dem SMA der ersten n Werte. Führende null-Werte in der
  // Eingabe (z. B. bei der MACD-Signallinie) werden übersprungen.
  function ema(values, n) {
    const out = new Array(values.length).fill(null);
    let start = 0;
    while (start < values.length && values[start] === null) start++;
    if (values.length - start < n) return out;
    const k = 2 / (n + 1);
    let e = 0;
    for (let i = start; i < start + n; i++) e += values[i];
    e /= n;
    out[start + n - 1] = e;
    for (let i = start + n; i < values.length; i++) {
      e = values[i] * k + e * (1 - k);
      out[i] = e;
    }
    return out;
  }

  // RSI nach Wilder.
  function rsi(closes, n) {
    const out = new Array(closes.length).fill(null);
    if (closes.length <= n) return out;
    let gain = 0;
    let loss = 0;
    for (let i = 1; i <= n; i++) {
      const d = closes[i] - closes[i - 1];
      if (d > 0) gain += d;
      else loss -= d;
    }
    gain /= n;
    loss /= n;
    const val = () => (loss === 0 ? 100 : 100 - 100 / (1 + gain / loss));
    out[n] = val();
    for (let i = n + 1; i < closes.length; i++) {
      const d = closes[i] - closes[i - 1];
      gain = (gain * (n - 1) + (d > 0 ? d : 0)) / n;
      loss = (loss * (n - 1) + (d < 0 ? -d : 0)) / n;
      out[i] = val();
    }
    return out;
  }

  function macd(closes, fast, slow, signalN) {
    const f = ema(closes, fast);
    const s = ema(closes, slow);
    const line = closes.map((_, i) => (f[i] === null || s[i] === null ? null : f[i] - s[i]));
    const signal = ema(line, signalN);
    const hist = line.map((v, i) => (v === null || signal[i] === null ? null : v - signal[i]));
    return { macd: line, signal, hist };
  }

  function bollinger(closes, n, mult) {
    const mid = sma(closes, n);
    const upper = new Array(closes.length).fill(null);
    const lower = new Array(closes.length).fill(null);
    for (let i = n - 1; i < closes.length; i++) {
      let sq = 0;
      for (let j = i - n + 1; j <= i; j++) sq += (closes[j] - mid[i]) ** 2;
      const sd = Math.sqrt(sq / n);
      upper[i] = mid[i] + mult * sd;
      lower[i] = mid[i] - mult * sd;
    }
    return { mid, upper, lower };
  }

  // Average True Range nach Wilder.
  function atr(candles, n) {
    const out = new Array(candles.length).fill(null);
    if (candles.length < n) return out;
    let a = 0;
    for (let i = 0; i < candles.length; i++) {
      const c = candles[i];
      const pc = i > 0 ? candles[i - 1].c : c.c;
      const tr = Math.max(c.h - c.l, Math.abs(c.h - pc), Math.abs(c.l - pc));
      if (i < n) {
        a += tr;
        if (i === n - 1) {
          a /= n;
          out[i] = a;
        }
      } else {
        a = (a * (n - 1) + tr) / n;
        out[i] = a;
      }
    }
    return out;
  }

  // Volumengewichteter Durchschnittspreis, startet jeden UTC-Tag neu.
  function vwap(candles) {
    const out = new Array(candles.length).fill(null);
    let pv = 0;
    let vol = 0;
    let day = null;
    for (let i = 0; i < candles.length; i++) {
      const c = candles[i];
      const d = Math.floor(c.t / 86400000);
      if (d !== day) {
        day = d;
        pv = 0;
        vol = 0;
      }
      const tp = (c.h + c.l + c.c) / 3;
      pv += tp * c.v;
      vol += c.v;
      out[i] = vol > 0 ? pv / vol : tp;
    }
    return out;
  }

  const api = { sma, ema, rsi, macd, bollinger, atr, vwap };
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.DT = Object.assign(root.DT || {}, api);
})(typeof self !== 'undefined' ? self : globalThis);
