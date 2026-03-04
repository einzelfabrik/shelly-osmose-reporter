from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from notifiers.factory import build_notifiers
from python_service.reporting import PeriodValues, build_report_text


def _week_key(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def _month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def _day_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


@dataclass
class Totals:
    in_l: float
    out_l: float

    @property
    def product_l(self) -> float:
        return max(0.0, self.in_l - self.out_l)


class OsmoseService:
    def __init__(self, config: dict[str, Any]) -> None:
        self.cfg = config
        self.state_path = Path(self.cfg["runtime"]["state_file"])
        self.state = self._load_state()
        self.notifiers = build_notifiers(self.cfg.get("notifications", {}))

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=True, indent=2), encoding="utf-8")

    def _fetch_status(self, base_url: str, input_id: int) -> dict[str, Any]:
        timeout = int(self.cfg["shelly"].get("request_timeout_seconds", 8))
        url = f"{base_url.rstrip('/')}/rpc/Input.GetStatus"
        resp = requests.post(url, json={"id": input_id}, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def _to_liters(self, status: dict[str, Any]) -> float:
        counts = status.get("counts", {})
        if isinstance(counts.get("xtotal"), (int, float)):
            return float(counts["xtotal"])
        pulses_per_liter = float(self.cfg["sensor"].get("pulses_per_liter", 1380))
        return float(counts.get("total", 0)) / pulses_per_liter

    def read_totals(self) -> Totals:
        input_id = int(self.cfg["shelly"].get("input_id", 2))
        in_st = self._fetch_status(self.cfg["shelly"]["zulauf_base_url"], input_id)
        out_offline = False
        try:
            out_st = self._fetch_status(self.cfg["shelly"]["ablauf_base_url"], input_id)
            out_l = self._to_liters(out_st)
        except Exception:
            out_l = float(self.state.get("last_totals", {}).get("out_l", 0.0))
            out_offline = True

        in_l = self._to_liters(in_st)
        self.state.setdefault("runtime", {})["remote_offline"] = out_offline
        self.state["last_totals"] = {"in_l": in_l, "out_l": out_l}
        return Totals(in_l=in_l, out_l=out_l)

    def _ensure_anchors(self, now: datetime, totals: Totals) -> None:
        s = self.state
        anchors = s.setdefault("anchors", {})
        current_day = _day_key(now)
        current_week = _week_key(now)
        current_month = _month_key(now)

        if "day" not in anchors:
            anchors["day"] = {"key": current_day, "in_start": totals.in_l, "out_start": totals.out_l}
        if "week" not in anchors:
            anchors["week"] = {"key": current_week, "in_start": totals.in_l, "out_start": totals.out_l}
        if "month" not in anchors:
            anchors["month"] = {"key": current_month, "in_start": totals.in_l, "out_start": totals.out_l}

        # Roll day at first tick after midnight
        if anchors["day"]["key"] != current_day:
            prev = anchors["day"]
            y_in = max(0.0, float(self.state["last_totals"]["in_l"]) - float(prev["in_start"]))
            y_out = max(0.0, float(self.state["last_totals"]["out_l"]) - float(prev["out_start"]))
            self.state["last_day"] = {"key": prev["key"], "in_l": y_in, "out_l": y_out, "product_l": max(0.0, y_in - y_out)}
            anchors["day"] = {"key": current_day, "in_start": totals.in_l, "out_start": totals.out_l}

        if anchors["week"]["key"] != current_week:
            prev = anchors["week"]
            p_in = max(0.0, float(self.state["last_totals"]["in_l"]) - float(prev["in_start"]))
            p_out = max(0.0, float(self.state["last_totals"]["out_l"]) - float(prev["out_start"]))
            self.state["last_week"] = {"key": prev["key"], "in_l": p_in, "out_l": p_out, "product_l": max(0.0, p_in - p_out)}
            anchors["week"] = {"key": current_week, "in_start": totals.in_l, "out_start": totals.out_l}

        if anchors["month"]["key"] != current_month:
            prev = anchors["month"]
            p_in = max(0.0, float(self.state["last_totals"]["in_l"]) - float(prev["in_start"]))
            p_out = max(0.0, float(self.state["last_totals"]["out_l"]) - float(prev["out_start"]))
            self.state["last_month"] = {"key": prev["key"], "in_l": p_in, "out_l": p_out, "product_l": max(0.0, p_in - p_out)}
            anchors["month"] = {"key": current_month, "in_start": totals.in_l, "out_start": totals.out_l}

    def tick(self) -> None:
        now = datetime.now()
        totals = self.read_totals()
        self._ensure_anchors(now, totals)
        self._save_state()

    def build_daily_report(self) -> str | None:
        now = datetime.now()
        last_day = self.state.get("last_day")
        if not last_day:
            return None

        total = self.state.get("last_totals", {"in_l": 0.0, "out_l": 0.0})
        total_vals = PeriodValues(
            in_l=float(total["in_l"]),
            out_l=float(total["out_l"]),
            product_l=max(0.0, float(total["in_l"]) - float(total["out_l"])),
        )
        yesterday = PeriodValues(
            in_l=float(last_day["in_l"]),
            out_l=float(last_day["out_l"]),
            product_l=float(last_day["product_l"]),
        )

        include_week = now.weekday() == 0 and "last_week" in self.state
        include_month = now.day == 1 and "last_month" in self.state
        last_week_vals = None
        last_month_vals = None
        last_week_key = ""
        last_month_key = ""
        if include_week:
            lw = self.state["last_week"]
            last_week_key = str(lw["key"])
            last_week_vals = PeriodValues(float(lw["in_l"]), float(lw["out_l"]), float(lw["product_l"]))
        if include_month:
            lm = self.state["last_month"]
            last_month_key = str(lm["key"])
            last_month_vals = PeriodValues(float(lm["in_l"]), float(lm["out_l"]), float(lm["product_l"]))

        return build_report_text(
            now=now,
            yesterday_key=str(last_day["key"]),
            yesterday=yesterday,
            include_last_week=include_week,
            last_week_key=last_week_key,
            last_week=last_week_vals,
            include_last_month=include_month,
            last_month_key=last_month_key,
            last_month=last_month_vals,
            total=total_vals,
            remote_offline=bool(self.state.get("runtime", {}).get("remote_offline", False)),
        )

    def send_daily_report(self) -> bool:
        report = self.build_daily_report()
        if not report:
            return False
        for notifier in self.notifiers:
            notifier.send(report)
        self.state.setdefault("runtime", {})["last_sent_day"] = _day_key(datetime.now())
        self._save_state()
        return True

    def send_test_report(self) -> None:
        totals = self.state.get("last_totals", {"in_l": 0.0, "out_l": 0.0})
        text = (
            "🧪 *TEST Osmose Report*\n"
            f"🕒 Erstellt: {datetime.now():%Y-%m-%d %H:%M}\n\n"
            "```"
            f"\n{'Zulauf':<14}{float(totals['in_l']):.2f} L"
            f"\n{'Abwasser':<14}{float(totals['out_l']):.2f} L"
            f"\n{'Produktwasser':<14}{max(0.0, float(totals['in_l']) - float(totals['out_l'])):.2f} L"
            "\n```"
        )
        for notifier in self.notifiers:
            notifier.send(text)
