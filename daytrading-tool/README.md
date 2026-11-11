# Daytrading-Assistent

Ein Analyse-Tool für Bitcoin und Ethereum (gegen USDT). Es lädt Live-Kurse, wendet feste Regeln der
Chartanalyse an, zeigt ein Setup (Long, Short oder Abwarten) mit Einstieg, Stop und Ziel und prüft die
Regeln per Backtest an vergangenen Kursen.

**Keine Anlageberatung.** Das Tool handelt nicht selbst und kann Kurse nicht vorhersagen. Die meisten
privaten Daytrader verlieren Geld.

## Starten

`index.html` im Browser öffnen (Doppelklick genügt). Es ist keine Installation, kein Konto und kein
API-Schlüssel nötig; das Tool liest nur öffentliche Binance-Marktdaten.

Für die Nutzung am Handy: im GitHub-Repository unter *Settings → Pages* die Veröffentlichung aus dem
Branch aktivieren und dann `…/daytrading-tool/` aufrufen.

## Wie die Bewertung funktioniert

Jede Regel, die an der letzten geschlossenen Kerze anschlägt, zählt mit ihrem Gewicht positiv (bullisch)
oder negativ (bärisch). Die Summe ist der Score. Ein Setup entsteht nur, wenn

1. der Score die Schwelle erreicht (Standard ±7),
2. mindestens ein Auslöser in dieselbe Richtung zeigt (Umfeld allein reicht nicht),
3. das Setup nicht gegen den 1-Stunden-Trend läuft (abschaltbar).

| Art | Regeln |
| --- | --- |
| Umfeld | 1h-Trend (EMA 50), EMA 20/50, Kurs zum VWAP |
| Auslöser: Indikatoren | EMA-Kreuzung, RSI dreht aus Extrembereich, MACD-Kreuzung, Rückkehr ins Bollinger-Band |
| Auslöser: Kerzenmuster | Hammer, Shooting Star, Engulfing, Morning/Evening Star |
| Auslöser: Formationen | Ausbruch mit Volumen, Doppelboden/Doppeltop, Schulter-Kopf-Schulter, Abpraller an Unterstützung/Widerstand |

Stop = 1,5 × ATR vom Einstieg, Ziel = 2 × Stop-Abstand. Alles ist in den Einstellungen änderbar, jede
Regel lässt sich einzeln abschalten.

Nicht enthalten: Dreiecke, Flaggen, Trendlinien, Nachrichten, Orderbuch.

## Backtest

- Einstieg zum Eröffnungskurs der Kerze nach dem Signal.
- Liegen Stop und Ziel in derselben Kerze, zählt der Stop.
- Gebühren (Standard 0,1 % je Seite) werden abgezogen, Slippage nicht.
- Eine Position gleichzeitig, 1 % Kontorisiko pro Trade, höchstens 48 Kerzen Haltedauer.
- „R“ ist das Ergebnis als Vielfaches des Risikos: +2 R = Ziel erreicht, −1 R = ausgestoppt.

Wichtig: Bei kurzen Kerzen ist der Stop-Abstand klein, und die Gebühren machen oft einen großen Teil
des Risikos aus. Die Signal-Karte zeigt diesen Anteil an. Die Standardgewichte sind Startwerte und
nicht an echten Kursen optimiert.

Short-Setups lassen sich am normalen Spot-Markt nicht handeln; dafür gibt es die Option „Nur Long“.

## Aufbau

| Datei | Inhalt |
| --- | --- |
| `js/indicators.js` | SMA, EMA, RSI, MACD, Bollinger, ATR, VWAP |
| `js/patterns.js` | Kerzenmuster, Wendepunkte, Unterstützung/Widerstand, Formationen |
| `js/strategy.js` | Regelwerk, Gewichte, Score, Setup |
| `js/backtest.js` | Backtest und Kennzahlen |
| `js/data.js` | Abruf der Binance-Kursdaten |
| `js/app.js` | Oberfläche |
| `tests/` | Tests: `node --test daytrading-tool/tests/core.test.js` |

Chart: [TradingView Lightweight Charts™](https://github.com/tradingview/lightweight-charts) (Apache 2.0,
Lizenz in `vendor/`).
