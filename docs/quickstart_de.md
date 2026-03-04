# Quickstart (Deutsch, 5 Minuten)

## Warum dieses Projekt?

In diesem Anwendungsfall wird eine **Osmofresh FusionPro** genutzt, die **keinen integrierten Wasserzaehler** besitzt.  
Darum wurde diese Loesung gebaut:

- Messung von **Zulauf** und **Abwasser** mit zwei externen Sensoren
- Berechnung von **Produktwasser = Zulauf - Abwasser**
- automatische Tages-/Wochen-/Monatsauswertung
- taeglicher Report per WhatsApp/Telegram/E-Mail

## Schnelle Inbetriebnahme (Shelly-only)

1. Beide FL-S402B Sensoren an je einen Shelly Plus Uni anschliessen.
2. Auf beiden Shellys fuer den Count-Eingang setzen:
   - `xcounts.expr = x/1380`
   - `xcounts.unit = Liter`
3. Auf dem **Zulauf-Shelly** das Script `shelly/shelly_master_script.js` einfuegen.
4. Im `CFG` anpassen:
   - `remoteAblaufStatusUrl`
   - `wahaUrl`, `wahaApiKey`, `waChatId`, `waSession`
   - `dailySendTime = "06:00"`
   - optional `tickSeconds = 3600`
5. Script aktivieren:
   - `Enable` an
   - `Run on startup` an

## Ergebnis

- Taeglicher Bericht um 06:00 mit Werten vom **Vortag**
- Montags zusaetzlich **letzte Woche**
- Am 1. zusaetzlich **letzter Monat**
- Warnhinweis im Report, falls der Abwasser-Shelly nicht erreichbar ist

## Weiterfuehrend

- Ausfuehrliche Anleitung: `docs/anleitung_de.md`
- Schaltplan und Verdrahtung: `docs/schaltplan.md`
