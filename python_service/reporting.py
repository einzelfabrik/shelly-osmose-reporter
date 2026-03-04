from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class PeriodValues:
    in_l: float
    out_l: float
    product_l: float

    @property
    def yield_pct(self) -> float:
        if self.in_l <= 0:
            return 0.0
        return (self.product_l / self.in_l) * 100.0


def _fmt(v: float) -> str:
    return f"{v:.2f}"


def table_row(label: str, value: str) -> str:
    return f"{label:<14}{value}"


def build_report_text(
    now: datetime,
    yesterday_key: str,
    yesterday: PeriodValues,
    include_last_week: bool,
    last_week_key: str,
    last_week: PeriodValues | None,
    include_last_month: bool,
    last_month_key: str,
    last_month: PeriodValues | None,
    total: PeriodValues,
    remote_offline: bool,
) -> str:
    lines: list[str] = [
        "💧 *Osmose Report*",
        f"🕒 Erstellt: {now:%Y-%m-%d %H:%M}",
        "",
        f"📅 *Gestern* ({yesterday_key})",
        "```",
        table_row("Zulauf", f"{_fmt(yesterday.in_l)} L"),
        table_row("Abwasser", f"{_fmt(yesterday.out_l)} L"),
        table_row("Produktwasser", f"{_fmt(yesterday.product_l)} L"),
        table_row("Ausbeute", f"{_fmt(yesterday.yield_pct)} %"),
        "```",
    ]

    if include_last_week and last_week is not None:
        lines += [
            "",
            f"📆 *Letzte Woche* ({last_week_key})",
            "```",
            table_row("Zulauf", f"{_fmt(last_week.in_l)} L"),
            table_row("Abwasser", f"{_fmt(last_week.out_l)} L"),
            table_row("Produktwasser", f"{_fmt(last_week.product_l)} L"),
            table_row("Ausbeute", f"{_fmt(last_week.yield_pct)} %"),
            "```",
        ]

    if include_last_month and last_month is not None:
        lines += [
            "",
            f"🗓️ *Letzter Monat* ({last_month_key})",
            "```",
            table_row("Zulauf", f"{_fmt(last_month.in_l)} L"),
            table_row("Abwasser", f"{_fmt(last_month.out_l)} L"),
            table_row("Produktwasser", f"{_fmt(last_month.product_l)} L"),
            table_row("Ausbeute", f"{_fmt(last_month.yield_pct)} %"),
            "```",
        ]

    lines += [
        "",
        "🏁 *Gesamt seit Start*",
        "```",
        table_row("Zulauf", f"{_fmt(total.in_l)} L"),
        table_row("Abwasser", f"{_fmt(total.out_l)} L"),
        table_row("Produktwasser", f"{_fmt(total.product_l)} L"),
        table_row("Ausbeute", f"{_fmt(total.yield_pct)} %"),
        "```",
    ]

    if remote_offline:
        lines += [
            "",
            "⚠️ *Hinweis*",
            "Ablauf-Shelly ist derzeit nicht erreichbar.",
            "Der letzte bekannte Ablaufwert wurde verwendet.",
        ]

    return "\n".join(lines)
