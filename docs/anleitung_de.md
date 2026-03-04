# Anleitung (Deutsch)

Diese Anleitung zeigt den kompletten Weg von der Verdrahtung bis zum taeglichen Report.

## Warum diese Loesung?

Im konkreten Einsatz wird eine **Osmofresh FusionPro** verwendet, die **keinen eingebauten Wasserzaehler** hat.
Dadurch fehlt ohne Zusatzhardware die Transparenz ueber:

- wie viel Wasser in die Anlage hineingeht (Zulauf),
- wie viel als Abwasser abgeht,
- wie viel als nutzbares Produktwasser uebrig bleibt.

Diese Loesung schliesst genau diese Luecke mit zwei Sensoren + Shelly-Auswertung und taeglichem Report.

## 1) Zielbild

- Zwei `Shelly Plus Uni`:
  - **Zulauf** (Master)
  - **Abwasser** (liefert nur Messwert)
- Zwei DIGTEN `FL-S402B` Sensoren
- Berechnung:
  - `Produktwasser = Zulauf - Abwasser`
- Versand:
  - WhatsApp (WAHA), Telegram oder E-Mail

## 2) Sensorfaktor korrekt setzen

Beim FL-S402B gilt laut Label:

- `F = 23 * Q(L/min)`
- Daraus folgen `1380 pulse/L`

Shelly Counter-Umrechnung:

- `xcounts.expr = x/1380`
- `xcounts.unit = Liter`

Das auf **beiden** Shellys im Count-Input setzen.

## 3) Shelly-only Variante (einfachster Start)

Datei: `shelly/shelly_master_script.js`

### Im Script `CFG` anpassen

- `remoteAblaufStatusUrl` (RPC URL vom Abwasser-Shelly)
- `wahaUrl`, `wahaApiKey`, `waChatId`, `waSession`
- `dailySendTime` (empfohlen `06:00`)
- `tickSeconds` (z. B. `3600` bei wenig Nachtverbrauch)

### Auf dem Zulauf-Shelly aktivieren

1. `Scripts` -> neues Script
2. Inhalt aus `shelly/shelly_master_script.js` einfuegen
3. `Enable` aktivieren
4. **Run on startup** aktivieren
5. Speichern/Starten

## 4) Berichtslogik

- Taeglich um `dailySendTime`: Bericht fuer **Gestern**
- Montag: zusaetzlich **Letzte Woche**
- Am 1. des Monats: zusaetzlich **Letzter Monat**
- Interne Shelly-Zaehler werden nicht zurueckgesetzt

## 5) Python-Service Variante

Wenn du statt Shelly-only lieber extern laufen willst:

1. `examples/config.example.toml` kopieren nach `config.toml`
2. Werte eintragen (Shelly + Notifier)
3. Starten:
   - `python3 -m python_service.main --config config.toml run-scheduler`

Optional mit HTTP:

- `python3 -m python_service.main --config config.toml serve`
- Endpunkte:
  - `/health`
  - `/report/test`
  - `/report/daily`

## 6) Home Assistant Variante

1. `home_assistant/package.yaml` als Package einbinden
2. Shelly-IP Platzhalter ersetzen
3. `notify.notify` in der Automation auf deinen Ziel-Service setzen

## 7) Fehlerfaelle und Verhalten

- Wenn Abwasser-Shelly nicht erreichbar ist:
  - letzter gueltiger Ablaufwert wird temporaer genutzt
  - Report enthaelt Warnhinweis
- Bei Neustart:
  - Script startet automatisch, wenn `Run on startup` aktiv ist
  - Zustand wird in KVS (Shelly) bzw. State-Datei (Python) gehalten

## 8) Empfehlung fuer deinen Betrieb

- `dailySendTime = "06:00"` fuer Vortagsbericht am Morgen
- `tickSeconds = 3600` ist bei euch (nachts kein Verbrauch) sinnvoll
- Testversand nur bei Bedarf aktivieren, danach wieder deaktivieren
