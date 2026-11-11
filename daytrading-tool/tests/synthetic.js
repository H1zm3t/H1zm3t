// Simulierte Kurse für Tests (Zufallsbewegung mit festem Startwert, damit
// jeder Lauf dieselben Daten liefert). Keine echten Marktdaten.
'use strict';

function rng(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function randomWalk(n, { seed = 1, tfMs = 300000, start = 50000, vol = 0.0015, t0 = 1750000000000 } = {}) {
  const rand = rng(seed);
  const gauss = () => {
    let u = 0;
    for (let k = 0; k < 6; k++) u += rand();
    return u - 3;
  };
  const out = [];
  let price = start;
  t0 -= t0 % tfMs;
  for (let i = 0; i < n; i++) {
    const o = price;
    const c = o * (1 + gauss() * vol);
    const h = Math.max(o, c) * (1 + rand() * vol * 0.6);
    const l = Math.min(o, c) * (1 - rand() * vol * 0.6);
    out.push({ t: t0 + i * tfMs, o, h, l, c, v: 50 + rand() * 100 + (rand() > 0.9 ? 200 : 0) });
    price = c;
  }
  return out;
}

// Fasst Kerzen zu größeren Kerzen zusammen (z. B. 5 min -> 1 h).
function aggregate(candles, ms) {
  const out = [];
  for (const c of candles) {
    const t = c.t - (c.t % ms);
    const last = out[out.length - 1];
    if (last && last.t === t) {
      last.h = Math.max(last.h, c.h);
      last.l = Math.min(last.l, c.l);
      last.c = c.c;
      last.v += c.v;
    } else {
      out.push({ t, o: c.o, h: c.h, l: c.l, c: c.c, v: c.v });
    }
  }
  return out;
}

module.exports = { randomWalk, aggregate };
