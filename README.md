# shelly-osmose-reporter

Open-source toolkit for RO/osmosis monitoring with Shelly devices.

German setup guide: `docs/anleitung_de.md`
German quickstart: `docs/quickstart_de.md`

It supports three runtime targets:

1. **Shelly-only** (master script on Zulauf Shelly)
2. **Python service** (scheduler + HTTP endpoints)
3. **Home Assistant package** (sensors + utility_meter + automation)

And three notification channels:

- WhatsApp via **WAHA**
- **Telegram** bot
- **E-Mail** via SMTP

## Project Requirements and Scope

This project is designed for installations where the RO unit has no built-in water/energy metering.

- Water tracking with two counters: `Zulauf` and `Abwasser`
- Net water KPI: `Produktwasser = max(0, Zulauf - Abwasser)`
- Optional power/energy tracking with a **Shelly Plug**
- Daily, weekly, monthly summaries without resetting Shelly counters
- WhatsApp report output including a chart

## Core Logic

- `Zulauf` and `Abwasser` are measured as cumulative liters.
- `Produktwasser = max(0, Zulauf - Abwasser)`.
- Optional `Energie` is measured as cumulative kWh from Shelly Plug.
- Sensor conversion for FL-S402B:
  - Label formula: `F = 23 * Q(L/min)`
  - Pulses per liter: `23 * 60 = 1380`
  - Shelly expression: `xcounts.expr = x/1380`

## Repository Structure

- `shelly/shelly_master_script.js` - Shelly-only master script (water + optional energy)
- `python_service/` - Python collector, scheduler, report API
- `notifiers/` - WAHA, Telegram, SMTP adapters
- `home_assistant/package.yaml` - HA sensors + utility meters + daily automation
- `examples/config.example.toml` - multi-channel Python config template
- `docs/schaltplan.md` - wiring/schematic and setup notes
- `docs/anleitung_de.md` - complete German step-by-step guide
- `docs/quickstart_de.md` - German 5-minute quickstart
- `config_example.ini` - legacy INI example (kept for backwards compatibility)

## Quick Start

### A) Shelly-only

1. Configure both Shelly counters (`input:2`) to liters:
   - `xcounts.expr = x/1380`
   - `xcounts.unit = Liter`
2. (Optional) Add Shelly Plug for energy tracking.
3. Edit `shelly/shelly_master_script.js` `CFG` values:
   - `remoteAblaufStatusUrl`
   - `remotePlugStatusUrl` (optional, for energy)
   - `wahaUrl` / `wahaApiKey` / `waChatId` / `waSession`
   - `dailySendHour` (recommended `6`)
4. Paste script to the **Zulauf Shelly** and enable **Run on startup**.

### B) Python service

1. Copy `examples/config.example.toml` to `config.toml`.
2. Fill Shelly endpoints and notification credentials.
3. Run:
   - `python3 -m python_service.main --config config.toml tick`
   - `python3 -m python_service.main --config config.toml run-scheduler`
4. Optional HTTP API:
   - `python3 -m python_service.main --config config.toml serve`
   - `GET /health`, `GET /report/test`, `GET /report/daily`

### C) Home Assistant

1. Copy `home_assistant/package.yaml` to your HA packages folder.
2. Replace `SHELLY_ZULAUF_IP` and `SHELLY_ABWASSER_IP`.
3. Adjust `notify.notify` target to your desired HA notifier.

## Reporting Rules

- Daily at configured hour: report for **yesterday**
- On Monday: includes **last week**
- On day 1 of month: includes **last month**
- If remote `Abwasser` Shelly is offline, report includes warning
- If `Shelly Plug` is offline, report includes warning

## Security

- No real keys/tokens/chat IDs are stored in repository files.
- Keep local runtime files private (`config.ini`, `config.toml`, `data/*.json`, `.local.js`).

## License

MIT
