# Shelly Runtime

`shelly_master_script.js` ist die Standalone-Variante fuer den Zulauf-Shelly.

## Hinweise

- Script nur auf dem Zulauf-Shelly aktivieren (Master).
- Ablauf-Shelly liefert Messwerte per RPC (`Input.GetStatus`).
- `Run on startup` einschalten, damit das Script nach Reboot automatisch startet.
- Für interne/private Zugänge nutze `shelly_master_script.local.js` (gitignored).
