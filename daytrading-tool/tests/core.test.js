'use strict';
// Ausführen mit:  node --test daytrading-tool/tests/core.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const I = require('../js/indicators.js');
const P = require('../js/patterns.js');
const S = require('../js/strategy.js');
const { runBacktest } = require('../js/backtest.js');
const { mergeCandles } = require('../js/data.js');
const { randomWalk, aggregate } = require('./synthetic.js');

const TF = 300000;
const near = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);
const flat = (t, price, v = 100) => ({ t, o: price, h: price + 1, l: price - 1, c: price, v });

test('SMA und EMA', () => {
  assert.deepEqual(I.sma([1, 2, 3, 4, 5], 3), [null, null, 2, 3, 4]);
  const e = I.ema([1, 2, 3, 4, 5], 3);
  assert.deepEqual(e.slice(0, 2), [null, null]);
  near(e[2], 2);
  near(e[3], 3); // 4*0.5 + 2*0.5
  near(e[4], 4);
});

test('RSI: nur Gewinne = 100, nur Verluste = 0, Referenzwert', () => {
  const up = Array.from({ length: 30 }, (_, i) => 100 + i);
  const down = Array.from({ length: 30 }, (_, i) => 100 - i);
  near(I.rsi(up, 14)[29], 100);
  near(I.rsi(down, 14)[29], 0);
  // Bekanntes Lehrbuchbeispiel (Wilder): erster RSI-Wert ca. 70,5
  const closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.1, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28];
  near(I.rsi(closes, 14)[14], 70.46, 0.1);
});

test('ATR, Bollinger und VWAP auf einfachen Daten', () => {
  const cs = Array.from({ length: 30 }, (_, i) => flat(i * TF, 100));
  near(I.atr(cs, 14)[29], 2);
  const bb = I.bollinger(cs.map((c) => c.c), 20, 2);
  near(bb.upper[29], 100);
  near(bb.lower[29], 100);
  // VWAP startet am neuen UTC-Tag neu
  const day = 86400000;
  const v = I.vwap([flat(day - TF, 100), flat(day, 200), flat(day + TF, 200)]);
  near(v[0], 100);
  near(v[1], 200);
});

test('MACD hat nach der Einschwingzeit Werte', () => {
  const m = I.macd(randomWalk(100).map((c) => c.c), 12, 26, 9);
  assert.equal(m.hist[32], null);
  assert.notEqual(m.hist[33], null);
});

test('Kerzenmuster: Hammer und Bullish Engulfing nach Abwärtsbewegung', () => {
  const down = [110, 108, 106, 104].map((p, i) => ({ t: i, o: p + 2, h: p + 2.2, l: p - 0.2, c: p, v: 1 }));
  const hammer = { t: 4, o: 103.5, h: 104.1, l: 100, c: 104, v: 1 };
  assert.deepEqual(P.candlePatterns([...down, hammer], 4).map((x) => x.id), ['hammer']);
  const engulf = { t: 4, o: 103.8, h: 107, l: 103.5, c: 106.5, v: 1 };
  const ids = P.candlePatterns([...down, engulf], 4).map((x) => x.id + x.dir);
  assert.ok(ids.includes('engulfing1'));
});

test('Pivots werden erst nach den rechten Kerzen bestätigt', () => {
  const prices = [10, 11, 12, 15, 12, 11, 10, 9, 10, 11];
  const cs = prices.map((p, i) => ({ t: i, o: p, h: p + 0.5, l: p - 0.5, c: p, v: 1 }));
  const piv = P.findPivots(cs, 3, 3);
  assert.deepEqual(piv.highs.map((x) => [x.i, x.confirm]), [[3, 6]]);
  assert.equal(P.lastPivots(piv.highs, 5, 2).length, 0);
  assert.equal(P.lastPivots(piv.highs, 6, 2).length, 1);
});

test('Doppelboden wird beim Ausbruch über das Zwischenhoch erkannt', () => {
  // Zwei Tiefs bei 90, Zwischenhoch bei 100, danach Ausbruch.
  const path = [100, 97, 94, 90, 94, 97, 100, 97, 94, 90, 93, 96, 99, 99.5, 102];
  const cs = path.map((p, i) => ({ t: i, o: p, h: p + 0.3, l: p - 0.3, c: p, v: 1 }));
  const piv = P.findPivots(cs, 3, 3);
  const last = cs.length - 1;
  const hit = P.doublePattern(cs, piv, last, 2);
  assert.equal(hit && hit.dir, 1);
  assert.equal(P.doublePattern(cs, piv, last - 1, 2), null);
});

test('Unterstützung/Widerstand: nahe Wendepunkte werden gebündelt', () => {
  const pivots = {
    highs: [{ i: 5, price: 100, confirm: 8 }, { i: 20, price: 100.4, confirm: 23 }],
    lows: [{ i: 12, price: 90, confirm: 15 }, { i: 40, price: 99.8, confirm: 43 }],
  };
  const lv = P.levels(pivots, 50, 2, 300);
  assert.equal(lv.length, 1);
  assert.equal(lv[0].touches, 3);
  near(lv[0].price, (100 + 100.4 + 99.8) / 3);
  // Zum Zeitpunkt 30 ist der dritte Punkt noch nicht bekannt.
  assert.equal(P.levels(pivots, 30, 2, 300)[0].touches, 2);
});

test('Kein Blick in die Zukunft: Signal ändert sich nicht durch spätere Kerzen', () => {
  const cs = randomWalk(1500, { seed: 7 });
  const htf = aggregate(cs, 3600000);
  const full = S.prepare(cs, htf, TF);
  let checked = 0;
  for (let i = 100; i < 1400; i += 37) {
    const part = cs.slice(0, i + 1);
    const cut = S.prepare(part, aggregate(part, 3600000), TF);
    const a = S.evaluate(full, i);
    const b = S.evaluate(cut, i);
    assert.equal(a.score, b.score, 'Score an Kerze ' + i);
    assert.equal(a.dir, b.dir);
    assert.deepEqual(a.reasons.map((r) => r.id + r.dir), b.reasons.map((r) => r.id + r.dir));
    checked++;
  }
  assert.ok(checked > 30);
});

test('Regelwerk: Setup braucht Auslöser, Filter und Optionen greifen', () => {
  const cs = randomWalk(3000, { seed: 3 });
  const ctx = S.prepare(cs, aggregate(cs, 3600000), TF);
  let setups = 0;
  for (let i = S.WARMUP; i < cs.length; i++) {
    const s = S.evaluate(ctx, i);
    if (s.dir) {
      setups++;
      assert.ok(Math.abs(s.score) >= S.DEFAULTS.threshold);
      assert.ok(s.reasons.some((r) => r.type === 'trigger' && r.dir === s.dir));
      assert.notEqual(s.htfTrend, -s.dir);
      near(Math.abs(s.target - s.entry), 2 * Math.abs(s.entry - s.stop), 1e-6);
      assert.ok(s.dir > 0 ? s.stop < s.entry : s.stop > s.entry);
    }
    assert.notEqual(S.evaluate(ctx, i, { longOnly: true }).dir, -1);
    const off = S.evaluate(ctx, i, { disabled: { vwap: true } });
    assert.ok(!off.reasons.some((r) => r.id === 'vwap'));
  }
  assert.ok(setups > 0, 'es sollte mindestens ein Setup geben');
});

test('Backtest-Mechanik: Ziel, Stop, Gebühren', () => {
  // Signal künstlich erzwingen: Schwelle 0 gibt es nicht ohne Auslöser, daher
  // prüfen wir die Buchhaltung an echten Trades eines Zufallslaufs.
  const cs = randomWalk(6000, { seed: 11 });
  const htf = aggregate(cs, 3600000);
  const res = runBacktest(cs, htf, TF, { feePct: 0.1 });
  const free = runBacktest(cs, htf, TF, { feePct: 0 });
  assert.ok(res.trades.length > 5);
  assert.equal(res.trades.length, free.trades.length);
  for (let k = 0; k < res.trades.length; k++) {
    const t = res.trades[k];
    assert.ok(t.exitTime >= t.entryTime);
    assert.ok(t.r < t.rGross, 'Gebühren verschlechtern jeden Trade');
    near(free.trades[k].r, t.rGross, 1e-9);
    if (t.how === 'target') near(t.rGross, 2, 1e-9);
    if (t.how === 'stop') near(t.rGross, -1, 1e-9);
    if (k > 0) assert.ok(t.entryTime > res.trades[k - 1].exitTime, 'nur eine Position gleichzeitig');
  }
  const s = res.stats;
  assert.equal(s.trades, res.trades.length);
  assert.ok(s.winRate >= 0 && s.winRate <= 1);
  assert.ok(s.maxDrawdownPct >= 0);
  assert.ok(s.returnPct < s.returnGrossPct);
  const n = Object.values(s.byRule).reduce((a, r) => Math.max(a, r.n), 0);
  assert.ok(n <= s.trades);
});

test('Backtest: Stop zählt, wenn Stop und Ziel in derselben Kerze liegen', () => {
  const cs = randomWalk(4000, { seed: 5 });
  const first = runBacktest(cs, [], TF, { feePct: 0 }).trades[0];
  assert.ok(first);
  // Die Einstiegskerze riesig machen: Stop und Ziel werden beide berührt.
  const wide = cs.map((c) => (c.t === first.entryTime ? { ...c, h: c.h * 1.1, l: c.l * 0.9 } : c));
  const again = runBacktest(wide, [], TF, { feePct: 0 }).trades[0];
  assert.equal(again.entryTime, first.entryTime);
  assert.equal(again.exitTime, first.entryTime);
  assert.equal(again.how, 'stop');
});

test('mergeCandles ersetzt die laufende Kerze und hängt neue an', () => {
  const list = [flat(0, 1), flat(TF, 2)];
  assert.equal(mergeCandles(list, [flat(TF, 3)]), false);
  assert.equal(list[1].c, 3);
  assert.equal(mergeCandles(list, [flat(TF, 4), flat(2 * TF, 5)]), true);
  assert.deepEqual(list.map((c) => c.c), [1, 4, 5]);
});
