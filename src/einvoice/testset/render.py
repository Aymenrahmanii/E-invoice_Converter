"""Render an Invoice to HTML with one of the Jinja2 layouts, then to PDF with WeasyPrint.

WeasyPrint needs the Pango libraries: available on Linux (CI, Docker, WSL), not on
plain Windows. Everything except `html_to_pdf` works without it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

from einvoice.model import Invoice
from einvoice.testset.fake import Business, Language

TEMPLATES = Path(__file__).parent / "layouts"

MONTHS_DE = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]
MONTHS_EN = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

UNITS: dict[Language, dict[str, list[str]]] = {
    "de": {
        "HUR": ["Std.", "h", "Stunden"],
        "DAY": ["Tag(e)", "PT", "Tage"],
        "C62": ["Stk.", "St.", "Stück"],
        "LS": ["pausch.", "Pauschale", "psch."],
        "MTR": ["m", "lfm"],
        "MTK": ["m²", "qm"],
        "LTR": ["l", "Liter"],
        "KGM": ["kg"],
        "MON": ["Monat(e)", "Mon."],
        "SET": ["Set", "Satz"],
        "PR": ["Paar", "Pr."],
    },
    "en": {
        "HUR": ["hrs", "h", "hours"],
        "DAY": ["days", "d"],
        "C62": ["pcs", "units", "ea."],
        "LS": ["lump sum", "flat"],
        "MTR": ["m"],
        "MTK": ["sqm", "m²"],
        "LTR": ["l"],
        "KGM": ["kg"],
        "MON": ["months", "mo."],
        "SET": ["set"],
        "PR": ["pairs"],
    },
}


@dataclass(frozen=True)
class Layout:
    name: str
    business: Business
    lines: tuple[int, int]
    language: Language = "de"
    mixed_vat: bool = False


LAYOUTS: list[Layout] = [
    Layout("craftsman_din", "craftsman", (2, 8)),
    Layout("agency_modern", "agency", (1, 6)),
    Layout("wholesaler_dense", "wholesaler", (8, 20)),
    Layout("one_line", "freelancer", (1, 1)),
    Layout("multipage", "wholesaler", (35, 60)),
    Layout("two_vat", "grocer", (3, 12), mixed_vat=True),
    Layout("english", "agency", (1, 7), language="en"),
    Layout("sidebar", "craftsman", (2, 7)),
    Layout("legacy_mono", "wholesaler", (3, 12)),
    Layout("footer_columns", "freelancer", (1, 5)),
]
LAYOUT_BY_NAME = {layout.name: layout for layout in LAYOUTS}


class Formatter:
    """Locale formatting with a little per-invoice variation (as real tools differ)."""

    def __init__(self, language: Language, seed: int) -> None:
        rng = random.Random(seed * 7919)
        self.language = language
        self.symbol = rng.choice(["€", "EUR"])
        self.long_dates = rng.random() < 0.25
        self.unit_variant = rng.randint(0, 2)

    def money(self, value: Decimal) -> str:
        if self.language == "en":
            return f"€{value:,.2f}" if self.symbol == "€" else f"EUR {value:,.2f}"
        s = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{s} {self.symbol}"

    def number(self, value: Decimal) -> str:
        """Quantities and rates: no trailing zeros; German decimal comma."""
        s = f"{value.normalize():f}"
        return s.replace(".", ",") if self.language == "de" else s

    def date(self, value: date | None) -> str:
        if value is None:
            return ""
        if self.long_dates:
            months = MONTHS_DE if self.language == "de" else MONTHS_EN
            return (
                f"{value.day}. {months[value.month - 1]} {value.year}"
                if self.language == "de"
                else (f"{value.day} {months[value.month - 1]} {value.year}")
            )
        return value.strftime("%d.%m.%Y") if self.language == "de" else value.strftime("%d/%m/%Y")

    def unit(self, code: str) -> str:
        names = UNITS[self.language].get(code, [code])
        return names[self.unit_variant % len(names)]


def css_str(value: str) -> Markup:
    """Text inside a CSS string in a <style> block: no HTML entities there, escape for CSS."""
    return Markup(str(value).replace("\\", "\\\\").replace('"', '\\"').replace("<", "\\3c "))


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        undefined=StrictUndefined,
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["css_str"] = css_str
    return env


def render_html(invoice: Invoice, layout: Layout, seed: int) -> str:
    fmt = Formatter(layout.language, seed)
    ctx: dict[str, Any] = {
        "inv": invoice,
        "fmt": fmt,
        "vat": invoice.vat_breakdown(),
        "leitweg": invoice.buyer_reference.count("-") == 2,
        "css": (TEMPLATES / "base.css").read_text(encoding="utf-8"),
    }
    return _env().get_template(f"{layout.name}.html.j2").render(**ctx)


def html_to_pdf(html: str) -> bytes:
    from weasyprint import HTML  # imported here: needs Pango, see module docstring

    return bytes(HTML(string=html, base_url=str(TEMPLATES)).write_pdf())
