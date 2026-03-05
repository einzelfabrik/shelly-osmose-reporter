# Shelly Runtime

`shelly_master_script.js` ist die Standalone-Variante fuer den Zulauf-Shelly.

## Hinweise

- Script nur auf dem Zulauf-Shelly aktivieren (Master).
- Ablauf-Shelly liefert Wasser-Messwerte per RPC (`Input.GetStatus`).
- Optional kann ein Shelly Plug Energiewerte liefern (`Shelly.GetStatus`).
- `Run on startup` einschalten, damit das Script nach Reboot automatisch startet.
- Fuer interne/private Zugaenge nutze `shelly_master_script.local.js` (gitignored).

## Wichtige CFG-Felder

- `remoteAblaufStatusUrl`: URL zum Ablauf-Shelly
- `remotePlugStatusUrl`: URL zum Shelly Plug (optional)
- `dailySendHour`: Versandstunde (z. B. `6`)
- `sendDailyReportTestOnStart`: Testmodus fuer Chart + Report beim Start
