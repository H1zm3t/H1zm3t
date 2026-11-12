// Kursdaten von der öffentlichen Binance-Schnittstelle (kein Konto und kein
// API-Schlüssel nötig, es werden nur Marktdaten gelesen).
(function (root) {
  'use strict';

  const BASES = ['https://data-api.binance.vision', 'https://api.binance.com'];
  const MAX_LIMIT = 1000;

  const toCandle = (k) => ({ t: k[0], o: +k[1], h: +k[2], l: +k[3], c: +k[4], v: +k[5] });

  // Bis zu 1000 Kerzen, älteste zuerst. Die letzte Kerze läuft meist noch.
  async function fetchKlines(symbol, interval, limit, endTime) {
    let lastError;
    for (const base of BASES) {
      let url = `${base}/api/v3/klines?symbol=${symbol}&interval=${interval}&limit=${limit}`;
      if (endTime) url += `&endTime=${endTime}`;
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return (await res.json()).map(toCandle);
      } catch (err) {
        lastError = err;
      }
    }
    throw new Error('Kursdaten nicht erreichbar (' + lastError.message + ')');
  }

  // Lädt `count` Kerzen rückwärts in Blöcken von 1000.
  async function fetchHistory(symbol, interval, count, onProgress) {
    let all = [];
    let endTime;
    while (all.length < count) {
      const want = Math.min(MAX_LIMIT, count - all.length);
      const batch = await fetchKlines(symbol, interval, want, endTime);
      if (!batch.length) break;
      all = batch.concat(all);
      endTime = batch[0].t - 1;
      if (onProgress) onProgress(Math.min(1, all.length / count));
      if (batch.length < want) break; // ältere Daten gibt es nicht
    }
    return all;
  }

  // Fügt neuere Kerzen in eine bestehende Liste ein (ersetzt gleiche Zeiten).
  // Gibt true zurück, wenn eine neue Kerze dazugekommen ist.
  function mergeCandles(list, fresh) {
    let added = false;
    for (const c of fresh) {
      const last = list[list.length - 1];
      if (!last || c.t > last.t) {
        list.push(c);
        added = true;
      } else {
        for (let k = list.length - 1; k >= 0 && list[k].t >= c.t; k--) {
          if (list[k].t === c.t) list[k] = c;
        }
      }
    }
    return added;
  }

  const api = { fetchKlines, fetchHistory, mergeCandles };
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.DT = Object.assign(root.DT || {}, api);
})(typeof self !== 'undefined' ? self : globalThis);
