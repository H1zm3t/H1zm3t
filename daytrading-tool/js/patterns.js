// Kerzenmuster und Chartformationen.
// Wichtig: Jede Funktion schaut nur auf Kerzen bis einschließlich Index i,
// nie in die Zukunft. Wendepunkte (Pivots) gelten erst als bestätigt, wenn
// rechts davon genug Kerzen geschlossen haben.
(function (root) {
  'use strict';

  const body = (c) => Math.abs(c.c - c.o);
  const range = (c) => c.h - c.l;
  const upperWick = (c) => c.h - Math.max(c.o, c.c);
  const lowerWick = (c) => Math.min(c.o, c.c) - c.l;
  const isGreen = (c) => c.c > c.o;
  const isRed = (c) => c.c < c.o;

  // Kerzenmuster an der Kerze i. dir: +1 = bullisch, -1 = bärisch.
  function candlePatterns(candles, i) {
    const out = [];
    if (i < 4) return out;
    const c = candles[i];
    const p = candles[i - 1];
    const pp = candles[i - 2];
    const r = range(c);
    if (r <= 0) return out;
    const b = body(c);
    const declined = p.c < candles[i - 4].c; // vorher gefallen
    const rallied = p.c > candles[i - 4].c; // vorher gestiegen

    if (declined && lowerWick(c) >= 2 * b && upperWick(c) <= 0.25 * r && b <= 0.35 * r) {
      out.push({ id: 'hammer', dir: 1, name: 'Hammer' });
    }
    if (rallied && upperWick(c) >= 2 * b && lowerWick(c) <= 0.25 * r && b <= 0.35 * r) {
      out.push({ id: 'shooting_star', dir: -1, name: 'Shooting Star' });
    }
    if (declined && isRed(p) && isGreen(c) && c.o <= p.c && c.c >= p.o && b > body(p)) {
      out.push({ id: 'engulfing', dir: 1, name: 'Bullish Engulfing' });
    }
    if (rallied && isGreen(p) && isRed(c) && c.o >= p.c && c.c <= p.o && b > body(p)) {
      out.push({ id: 'engulfing', dir: -1, name: 'Bearish Engulfing' });
    }
    // Morning Star / Evening Star: große Kerze, kleine Kerze, Gegenkerze über
    // die Mitte der ersten hinaus.
    const bpp = body(pp);
    if (range(pp) > 0 && bpp >= 0.6 * range(pp) && body(p) <= 0.3 * bpp) {
      const mid = (pp.o + pp.c) / 2;
      if (isRed(pp) && isGreen(c) && c.c > mid) {
        out.push({ id: 'star', dir: 1, name: 'Morning Star' });
      }
      if (isGreen(pp) && isRed(c) && c.c < mid) {
        out.push({ id: 'star', dir: -1, name: 'Evening Star' });
      }
    }
    return out;
  }

  // Wendepunkte: Hoch (Tief), das höher (tiefer) ist als `left` Kerzen links
  // und `right` Kerzen rechts. `confirm` ist der Index, ab dem der Wendepunkt
  // bekannt ist.
  function findPivots(candles, left, right) {
    const highs = [];
    const lows = [];
    for (let j = left; j < candles.length - right; j++) {
      let isHigh = true;
      let isLow = true;
      for (let k = j - left; k <= j + right && (isHigh || isLow); k++) {
        if (k === j) continue;
        // Bei Gleichstand zählt der frühere Punkt.
        if (k < j ? candles[k].h >= candles[j].h : candles[k].h > candles[j].h) isHigh = false;
        if (k < j ? candles[k].l <= candles[j].l : candles[k].l < candles[j].l) isLow = false;
      }
      if (isHigh) highs.push({ i: j, price: candles[j].h, confirm: j + right });
      if (isLow) lows.push({ i: j, price: candles[j].l, confirm: j + right });
    }
    return { highs, lows };
  }

  // Anzahl der Pivots in der (nach Index sortierten) Liste, die bei Kerze i
  // schon bestätigt sind.
  function confirmedCount(list, i) {
    let lo = 0;
    let hi = list.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (list[mid].confirm <= i) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  }

  // Die letzten k bei Kerze i bestätigten Pivots (älteste zuerst).
  function lastPivots(list, i, k) {
    const n = confirmedCount(list, i);
    return list.slice(Math.max(0, n - k), n);
  }

  // Unterstützungs- und Widerstandszonen: Wendepunkte, die preislich nah
  // beieinander liegen (innerhalb 0,5 ATR), werden zu einer Zone gebündelt.
  // Eine Zone zählt ab zwei Berührungen.
  function levels(pivots, i, atr, lookback) {
    const prices = [];
    for (const list of [pivots.highs, pivots.lows]) {
      for (let k = confirmedCount(list, i) - 1; k >= 0 && list[k].i >= i - lookback; k--) {
        prices.push(list[k].price);
      }
    }
    prices.sort((a, b) => a - b);
    const out = [];
    let sum = 0;
    let count = 0;
    const flush = () => {
      if (count >= 2) out.push({ price: sum / count, touches: count });
      sum = 0;
      count = 0;
    };
    for (const p of prices) {
      if (count > 0 && p - sum / count > 0.5 * atr) flush();
      sum += p;
      count++;
    }
    flush();
    return out;
  }

  const maxHigh = (candles, a, b) => {
    let m = -Infinity;
    for (let k = a; k <= b; k++) m = Math.max(m, candles[k].h);
    return m;
  };
  const minLow = (candles, a, b) => {
    let m = Infinity;
    for (let k = a; k <= b; k++) m = Math.min(m, candles[k].l);
    return m;
  };
  // Schlusskurs kreuzt an Kerze i die Marke `level` in Richtung dir.
  const crosses = (candles, i, level, dir) =>
    dir > 0
      ? candles[i].c > level && candles[i - 1].c <= level
      : candles[i].c < level && candles[i - 1].c >= level;

  // Doppelboden (+1) / Doppeltop (-1): zwei etwa gleich tiefe Tiefs, dazwischen
  // ein deutliches Zwischenhoch; Signal ist der Ausbruch über das Zwischenhoch.
  function doublePattern(candles, pivots, i, atr) {
    const maxAge = 60;
    const lows = lastPivots(pivots.lows, i, 2);
    if (lows.length === 2 && lows[1].i - lows[0].i >= 5 && i - lows[1].i <= maxAge) {
      const peak = maxHigh(candles, lows[0].i, lows[1].i);
      const bottom = Math.min(lows[0].price, lows[1].price);
      if (
        Math.abs(lows[0].price - lows[1].price) <= 0.5 * atr &&
        peak - bottom >= 1.5 * atr &&
        crosses(candles, i, peak, 1)
      ) {
        return { dir: 1, name: 'Doppelboden', level: peak };
      }
    }
    const highs = lastPivots(pivots.highs, i, 2);
    if (highs.length === 2 && highs[1].i - highs[0].i >= 5 && i - highs[1].i <= maxAge) {
      const trough = minLow(candles, highs[0].i, highs[1].i);
      const top = Math.max(highs[0].price, highs[1].price);
      if (
        Math.abs(highs[0].price - highs[1].price) <= 0.5 * atr &&
        top - trough >= 1.5 * atr &&
        crosses(candles, i, trough, -1)
      ) {
        return { dir: -1, name: 'Doppeltop', level: trough };
      }
    }
    return null;
  }

  // Schulter-Kopf-Schulter (-1) und die umgekehrte Form (+1). Signal ist der
  // Bruch der Nackenlinie.
  function headShoulders(candles, pivots, i, atr) {
    const maxAge = 60;
    const h = lastPivots(pivots.highs, i, 3);
    if (h.length === 3 && i - h[2].i <= maxAge) {
      const [a, b, c] = h;
      if (
        b.price - a.price >= 0.5 * atr &&
        b.price - c.price >= 0.5 * atr &&
        Math.abs(a.price - c.price) <= atr
      ) {
        const neck = Math.min(minLow(candles, a.i, b.i), minLow(candles, b.i, c.i));
        if (crosses(candles, i, neck, -1)) {
          return { dir: -1, name: 'Schulter-Kopf-Schulter', level: neck };
        }
      }
    }
    const l = lastPivots(pivots.lows, i, 3);
    if (l.length === 3 && i - l[2].i <= maxAge) {
      const [a, b, c] = l;
      if (
        a.price - b.price >= 0.5 * atr &&
        c.price - b.price >= 0.5 * atr &&
        Math.abs(a.price - c.price) <= atr
      ) {
        const neck = Math.max(maxHigh(candles, a.i, b.i), maxHigh(candles, b.i, c.i));
        if (crosses(candles, i, neck, 1)) {
          return { dir: 1, name: 'Umgekehrte Schulter-Kopf-Schulter', level: neck };
        }
      }
    }
    return null;
  }

  const api = { candlePatterns, findPivots, lastPivots, levels, doublePattern, headShoulders };
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.DT = Object.assign(root.DT || {}, api);
})(typeof self !== 'undefined' ? self : globalThis);
