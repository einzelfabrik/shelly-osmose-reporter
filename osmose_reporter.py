import argparse
import configparser
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Tuple

import requests

from waha_helper import send_whatsapp_message


@dataclass
class ShellyConfig:
    zulauf_base_url: str
    ablauf_base_url: str
    input_id: int
    request_timeout_seconds: int


@dataclass
class SensorConfig:
    model: str
    pulses_per_liter: float
    target_expression: str
    target_unit: str


@dataclass
class WhatsappConfig:
    base_url: str
    api_key: str
    empfaenger: str
    session: str
    send_endpoint: str
    retries: int
    retry_delay_seconds: float


@dataclass
class ReportConfig:
    daily_send_time: str
    state_file: str


@dataclass
class AppConfig:
    shelly: ShellyConfig
    sensor: SensorConfig
    whatsapp: WhatsappConfig
    report: ReportConfig


def load_config(config_path: Path) -> AppConfig:
    parser = configparser.ConfigParser()
    parser.read(config_path, encoding="utf-8")

    shelly = ShellyConfig(
        zulauf_base_url=parser["shelly"]["zulauf_base_url"].strip(),
        ablauf_base_url=parser["shelly"]["ablauf_base_url"].strip(),
        input_id=int(parser["shelly"].get("input_id", "2")),
        request_timeout_seconds=int(parser["shelly"].get("request_timeout_seconds", "8")),
    )
    sensor = SensorConfig(
        model=parser["sensor"]["model"].strip(),
        pulses_per_liter=float(parser["sensor"]["pulses_per_liter"]),
        target_expression=parser["sensor"]["target_expression"].strip(),
        target_unit=parser["sensor"].get("target_unit", "Liter").strip(),
    )
    whatsapp = WhatsappConfig(
        base_url=parser["whatsapp"]["base_url"].strip(),
        api_key=parser["whatsapp"]["api_key"].strip(),
        empfaenger=parser["whatsapp"]["empfaenger"].strip(),
        session=parser["whatsapp"]["session"].strip(),
        send_endpoint=parser["whatsapp"].get("send_endpoint", "/sendText").strip(),
        retries=int(parser["whatsapp"].get("retries", "3")),
        retry_delay_seconds=float(parser["whatsapp"].get("retry_delay_seconds", "2")),
    )
    report = ReportConfig(
        daily_send_time=parser["report"].get("daily_send_time", "20:00").strip(),
        state_file=parser["report"].get("state_file", "osmose_state.json").strip(),
    )
    return AppConfig(shelly=shelly, sensor=sensor, whatsapp=whatsapp, report=report)


def shelly_rpc(base_url: str, method: str, params: Dict[str, Any], timeout_seconds: int) -> Dict[str, Any]:
    response = requests.post(
        f"{base_url.rstrip('/')}/rpc/{method}",
        json=params,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def get_count_config(base_url: str, input_id: int, timeout_seconds: int) -> Dict[str, Any]:
    return shelly_rpc(base_url, "Input.GetConfig", {"id": input_id}, timeout_seconds)


def get_count_status(base_url: str, input_id: int, timeout_seconds: int) -> Dict[str, Any]:
    return shelly_rpc(base_url, "Input.GetStatus", {"id": input_id}, timeout_seconds)


def set_count_expression(
    base_url: str,
    input_id: int,
    expr: str,
    unit: str,
    timeout_seconds: int,
) -> Dict[str, Any]:
    params = {
        "id": input_id,
        "config": {
            "xcounts": {"expr": expr, "unit": unit},
            "xfreq": {"expr": "x/23", "unit": "L/min"},
        },
    }
    return shelly_rpc(base_url, "Input.SetConfig", params, timeout_seconds)


def liters_from_status(status: Dict[str, Any], pulses_per_liter: float) -> float:
    counts = status.get("counts", {})
    if isinstance(counts.get("xtotal"), (int, float)):
        return float(counts["xtotal"])
    return float(counts.get("total", 0.0)) / pulses_per_liter


def read_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_state(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=True, indent=2)


def day_key(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def week_key(now: datetime) -> str:
    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def month_key(now: datetime) -> str:
    return now.strftime("%Y-%m")


def ensure_period_anchor(
    state: Dict[str, Any],
    period_name: str,
    key: str,
    zulauf_total: float,
    ablauf_total: float,
) -> Dict[str, float]:
    period = state.get(period_name, {})
    if period.get("key") != key:
        period = {
            "key": key,
            "zulauf_start_l": zulauf_total,
            "ablauf_start_l": ablauf_total,
        }
        state[period_name] = period
    return period


def calculate_period_values(
    current_zulauf_l: float,
    current_ablauf_l: float,
    anchor: Dict[str, float],
) -> Tuple[float, float, float]:
    zulauf = max(0.0, current_zulauf_l - float(anchor["zulauf_start_l"]))
    ablauf = max(0.0, current_ablauf_l - float(anchor["ablauf_start_l"]))
    trinken = max(0.0, zulauf - ablauf)
    return zulauf, ablauf, trinken


def fetch_totals(config: AppConfig) -> Tuple[float, float]:
    in_status = get_count_status(
        config.shelly.zulauf_base_url,
        config.shelly.input_id,
        config.shelly.request_timeout_seconds,
    )
    out_status = get_count_status(
        config.shelly.ablauf_base_url,
        config.shelly.input_id,
        config.shelly.request_timeout_seconds,
    )
    zulauf_l = liters_from_status(in_status, config.sensor.pulses_per_liter)
    ablauf_l = liters_from_status(out_status, config.sensor.pulses_per_liter)
    return zulauf_l, ablauf_l


def run_check(config: AppConfig) -> None:
    expected_expr = config.sensor.target_expression
    print(f"[Check] Sensor-Modell: {config.sensor.model}")
    print(f"[Check] Erwarteter Umrechnungsfaktor: {expected_expr}")
    print(f"[Check] Aktuelle Formel x/2160 waere nur korrekt bei 2160 pulse/L.")
    print("[Check] Bei FL-S402B gilt laut Aufdruck F=23*Q(L/min) -> 1380 pulse/L.")

    for label, base_url in (("Zulauf", config.shelly.zulauf_base_url), ("Ablauf", config.shelly.ablauf_base_url)):
        cfg = get_count_config(base_url, config.shelly.input_id, config.shelly.request_timeout_seconds)
        status = get_count_status(base_url, config.shelly.input_id, config.shelly.request_timeout_seconds)
        expr = cfg.get("xcounts", {}).get("expr")
        unit = cfg.get("xcounts", {}).get("unit")
        total_pulses = status.get("counts", {}).get("total", 0)
        total_liters = liters_from_status(status, config.sensor.pulses_per_liter)
        print(f"[{label}] URL={base_url}")
        print(f"[{label}] xcounts.expr={expr}, unit={unit}")
        print(f"[{label}] total pulses={total_pulses}, total liters={total_liters:.3f}")
        if expr != expected_expr:
            print(f"[{label}] WARNUNG: Ausdruck ist nicht {expected_expr}")


def run_apply_expression(config: AppConfig) -> None:
    for label, base_url in (("Zulauf", config.shelly.zulauf_base_url), ("Ablauf", config.shelly.ablauf_base_url)):
        result = set_count_expression(
            base_url,
            config.shelly.input_id,
            config.sensor.target_expression,
            config.sensor.target_unit,
            config.shelly.request_timeout_seconds,
        )
        print(f"[{label}] Input.SetConfig Ergebnis: {result}")
    print("[Apply] xcounts/xfreq wurden aktualisiert.")


def create_daily_report_text(
    yesterday_vals: Tuple[float, float, float],
    week_vals: Tuple[float, float, float],
    month_vals: Tuple[float, float, float],
) -> str:
    y_in, y_out, y_drink = yesterday_vals
    w_in, w_out, w_drink = week_vals
    m_in, m_out, m_drink = month_vals
    efficiency = (y_drink / y_in * 100.0) if y_in > 0 else 0.0

    return (
        "Osmose Report (gestern)\n"
        f"- Zulauf: {y_in:.2f} L\n"
        f"- Ablauf: {y_out:.2f} L\n"
        f"- Trinkwasser: {y_drink:.2f} L\n"
        f"- Effizienz: {efficiency:.1f} %\n\n"
        "Laufende Woche\n"
        f"- Zulauf: {w_in:.2f} L\n"
        f"- Ablauf: {w_out:.2f} L\n"
        f"- Trinkwasser: {w_drink:.2f} L\n\n"
        "Laufender Monat\n"
        f"- Zulauf: {m_in:.2f} L\n"
        f"- Ablauf: {m_out:.2f} L\n"
        f"- Trinkwasser: {m_drink:.2f} L"
    )


def run_send_daily_report(config: AppConfig) -> None:
    now = datetime.now()
    state_path = Path(config.report.state_file)
    state = read_state(state_path)

    zulauf_l, ablauf_l = fetch_totals(config)
    update_day_tracking(state, now, zulauf_l, ablauf_l)
    week_anchor = ensure_period_anchor(state, "weekly_anchor", week_key(now), zulauf_l, ablauf_l)
    month_anchor = ensure_period_anchor(state, "monthly_anchor", month_key(now), zulauf_l, ablauf_l)

    yesterday = now - timedelta(days=1)
    yesterday_key = day_key(yesterday)
    report_day_data = state.get("daily_rollover", {}).get(yesterday_key)
    if not report_day_data:
        print(f"[Report] Kein Tagesabschluss fuer {yesterday_key} vorhanden. Fuehre nur Snapshot-Update aus.")
        state.setdefault("last_seen", {})["zulauf_l"] = zulauf_l
        state.setdefault("last_seen", {})["ablauf_l"] = ablauf_l
        write_state(state_path, state)
        return

    yesterday_vals = (
        float(report_day_data["zulauf_l"]),
        float(report_day_data["ablauf_l"]),
        float(report_day_data["trinken_l"]),
    )
    week_vals = calculate_period_values(zulauf_l, ablauf_l, week_anchor)
    month_vals = calculate_period_values(zulauf_l, ablauf_l, month_anchor)
    text = create_daily_report_text(yesterday_vals, week_vals, month_vals)

    send_whatsapp_message(
        base_url=config.whatsapp.base_url,
        api_key=config.whatsapp.api_key,
        message=text,
        empfaenger=config.whatsapp.empfaenger,
        session=config.whatsapp.session,
        endpoint=config.whatsapp.send_endpoint,
        retries=config.whatsapp.retries,
        retry_delay_seconds=config.whatsapp.retry_delay_seconds,
    )

    write_state(state_path, state)
    print("[Report] Tagesreport wurde versendet.")


def update_day_tracking(state: Dict[str, Any], now: datetime, zulauf_l: float, ablauf_l: float) -> None:
    tracker = state.setdefault("day_tracker", {})
    current_key = day_key(now)

    if "current_day_key" not in tracker:
        tracker["current_day_key"] = current_key
        tracker["day_start_zulauf_l"] = zulauf_l
        tracker["day_start_ablauf_l"] = ablauf_l
        tracker["last_total_zulauf_l"] = zulauf_l
        tracker["last_total_ablauf_l"] = ablauf_l
        return

    previous_day_key = tracker["current_day_key"]
    if previous_day_key != current_key:
        y_in = max(0.0, float(tracker["last_total_zulauf_l"]) - float(tracker["day_start_zulauf_l"]))
        y_out = max(0.0, float(tracker["last_total_ablauf_l"]) - float(tracker["day_start_ablauf_l"]))
        y_drink = max(0.0, y_in - y_out)
        roll = state.setdefault("daily_rollover", {})
        roll[previous_day_key] = {
            "zulauf_l": round(y_in, 4),
            "ablauf_l": round(y_out, 4),
            "trinken_l": round(y_drink, 4),
        }
        tracker["current_day_key"] = current_key
        tracker["day_start_zulauf_l"] = zulauf_l
        tracker["day_start_ablauf_l"] = ablauf_l

    tracker["last_total_zulauf_l"] = zulauf_l
    tracker["last_total_ablauf_l"] = ablauf_l


def run_rollover(config: AppConfig) -> None:
    now = datetime.now()
    state_path = Path(config.report.state_file)
    state = read_state(state_path)
    zulauf_l, ablauf_l = fetch_totals(config)
    update_day_tracking(state, now, zulauf_l, ablauf_l)
    write_state(state_path, state)
    print("[Rollover] Tages-Tracking aktualisiert.")


def run_scheduler(config: AppConfig) -> None:
    daily_time = config.report.daily_send_time
    print(f"[Scheduler] Aktiv. Taeglicher Versand um {daily_time}.")
    print("[Scheduler] Zum Stoppen: Ctrl+C")
    while True:
        now = datetime.now()
        hhmm = now.strftime("%H:%M")
        state_path = Path(config.report.state_file)
        state = read_state(state_path)
        zulauf_l, ablauf_l = fetch_totals(config)
        update_day_tracking(state, now, zulauf_l, ablauf_l)
        write_state(state_path, state)
        if hhmm == daily_time:
            run_send_daily_report(config)
            time.sleep(65)
        else:
            time.sleep(30)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Osmose Wasserreport (Shelly + WAHA)")
    parser.add_argument(
        "-c",
        "--config",
        default="config.ini",
        help="Pfad zur INI-Konfiguration (Default: config.ini)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="Prueft Shelly-Formeln und zeigt aktuelle Literwerte")
    subparsers.add_parser("apply-expression", help="Setzt xcounts/xfreq auf beiden Shellys")
    subparsers.add_parser("rollover", help="Speichert Tages-Snapshot in State-Datei")
    subparsers.add_parser("send-daily-report", help="Versendet den Report ueber WAHA")
    subparsers.add_parser("run-scheduler", help="Startet lokalen Scheduler (Dauerschleife)")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config(Path(args.config))

    if args.command == "check":
        run_check(config)
    elif args.command == "apply-expression":
        run_apply_expression(config)
    elif args.command == "rollover":
        run_rollover(config)
    elif args.command == "send-daily-report":
        run_send_daily_report(config)
    elif args.command == "run-scheduler":
        run_scheduler(config)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
