// Backtest: spielt das Regelwerk Kerze für Kerze über historische Daten.
// Annahmen (bewusst vorsichtig):
// - Einstieg zum Eröffnungskurs der Kerze NACH dem Signal.
// - Werden Stop und Ziel in derselben Kerze berührt, zählt der Stop.
// - Gebühren werden bei Kauf und Verkauf abgezogen.
// - Immer nur eine Position gleichzeitig.
(function (root) {
  'use strict';
  const isNode = typeof module === 'object' && module.exports;
  const S = isNode ? require('./strategy.js') : root.DT;

  function runBacktest(candles, htf, tfMs, options) {
    const o = Object.assign({}, S.DEFAULTS, options);
    const ctx = S.prepare(candles, htf, tfMs);
    const fee = o.feePct / 100;
    const risk = o.riskPct / 100;
    const n = candles.length;
    const trades = [];
    let equity = 1;
    let equityGross = 1;
    let peak = 1;
    let maxDrawdown = 0;
    const curve = n ? [{ t: candles[Math.min(S.WARMUP, n - 1)].t, equity: 1 }] : [];

    let i = S.WARMUP;
    while (i < n - 1) {
      const sig = S.evaluate(ctx, i, o);
      if (!sig || !sig.dir) {
        i++;
        continue;
      }
      const dir = sig.dir;
      const entry = candles[i + 1].o;
      const dist = sig.stopDist;
      const stop = entry - dir * dist;
      const target = entry + dir * dist * o.rr;
      let exit = null;
      let how = '';
      let j = i + 1;
      for (; j < n; j++) {
        const c = candles[j];
        const hitStop = dir > 0 ? c.l <= stop : c.h >= stop;
        const hitTarget = dir > 0 ? c.h >= target : c.l <= target;
        if (hitStop) {
          exit = stop;
          how = 'stop';
          break;
        }
        if (hitTarget) {
          exit = target;
          how = 'target';
          break;
        }
        if (j - i >= o.maxHold) {
          exit = c.c;
          how = 'time';
          break;
        }
      }
      if (exit === null) break; // Position am Datenende noch offen: nicht werten

      const riskFrac = dist / entry; // Stop-Abstand als Anteil des Kurses
      const gross = (dir * (exit - entry)) / entry;
      const rGross = gross / riskFrac;
      const r = (gross - 2 * fee) / riskFrac;
      equity *= 1 + risk * r;
      equityGross *= 1 + risk * rGross;
      peak = Math.max(peak, equity);
      maxDrawdown = Math.max(maxDrawdown, 1 - equity / peak);
      curve.push({ t: candles[j].t, equity });
      trades.push({
        dir,
        entryTime: candles[i + 1].t,
        exitTime: candles[j].t,
        entry,
        exit,
        how,
        r,
        rGross,
        score: sig.score,
        rules: sig.reasons.filter((x) => x.dir === dir).map((x) => x.id),
      });
      i = j; // frühestens an der Ausstiegskerze wieder ein Signal suchen
    }

    return { trades, curve, stats: summarize(trades, equity, equityGross, maxDrawdown, candles) };
  }

  function summarize(trades, equity, equityGross, maxDrawdown, candles) {
    const wins = trades.filter((t) => t.r > 0);
    const sumPos = wins.reduce((a, t) => a + t.r, 0);
    const sumNeg = trades.filter((t) => t.r <= 0).reduce((a, t) => a - t.r, 0);
    const totalR = sumPos - sumNeg;
    const byRule = {};
    for (const t of trades) {
      for (const id of new Set(t.rules)) {
        const s = (byRule[id] = byRule[id] || { n: 0, wins: 0, sumR: 0 });
        s.n++;
        if (t.r > 0) s.wins++;
        s.sumR += t.r;
      }
    }
    const first = candles[Math.min(S.WARMUP, candles.length - 1)];
    const last = candles[candles.length - 1];
    return {
      trades: trades.length,
      winRate: trades.length ? wins.length / trades.length : 0,
      avgR: trades.length ? totalR / trades.length : 0,
      avgRGross: trades.length ? trades.reduce((a, t) => a + t.rGross, 0) / trades.length : 0,
      totalR,
      profitFactor: sumNeg > 0 ? sumPos / sumNeg : sumPos > 0 ? Infinity : 0,
      returnPct: (equity - 1) * 100,
      returnGrossPct: (equityGross - 1) * 100,
      maxDrawdownPct: maxDrawdown * 100,
      buyHoldPct: first && last ? (last.c / first.c - 1) * 100 : 0,
      byRule,
    };
  }

  const api = { runBacktest };
  if (isNode) module.exports = api;
  root.DT = Object.assign(root.DT || {}, api);
})(typeof self !== 'undefined' ? self : globalThis);
