"""Field accuracy: compare an extracted Invoice with its label, field by field.

Every field is an exact match after normalising: whitespace collapsed, IBAN without
spaces, dates as dates, amounts as Decimal. Line items count as correct only when
description, quantity, unit price and net amount all match one label line.
Totals are compared as well; they are computed from the lines by the model, so a
wrong line shows up in both the line and the totals score.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from einvoice.model import Invoice

SCALAR_FIELDS = [
    "number",
    "issue_date",
    "due_date",
    "delivery_date",
    "buyer_reference",
    "seller.name",
    "seller.vat_id",
    "buyer.name",
    "buyer.vat_id",
    "iban",
    "bic",
    "net_total",
    "tax_total",
    "gross_total",
]


def _norm_text(value: Any) -> str | None:
    if value is None:
        return None
    s = " ".join(str(value).split())
    return s or None


def _norm_iban(value: Any) -> str | None:
    s = _norm_text(value)
    return s.replace(" ", "").upper() if s else None


def _norm_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _norm_date(value: Any) -> str | None:
    return None if value is None else str(value)


def _get(invoice: Invoice, path: str) -> Any:
    obj: Any = invoice
    for part in path.split("."):
        obj = getattr(obj, part) if obj is not None else None
    return obj


def _normalised(path: str, value: Any) -> Any:
    if path in ("iban",):
        return _norm_iban(value)
    if path in ("net_total", "tax_total", "gross_total"):
        return _norm_decimal(value)
    if path.endswith("date"):
        return _norm_date(value)
    return _norm_text(value)


def _values(invoice: Invoice) -> dict[str, Any]:
    values = {name: _get(invoice, name) for name in SCALAR_FIELDS}
    values["net_total"] = invoice.net_total
    values["tax_total"] = invoice.tax_total
    values["gross_total"] = invoice.gross_total
    return values


def _line_key(line: Any) -> tuple[Any, ...]:
    return (
        _norm_text(line.description),
        _norm_decimal(line.quantity),
        _norm_decimal(line.unit_price),
        _norm_decimal(line.net_amount),
    )


@dataclass
class Score:
    documents: int = 0
    fields_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    fields_correct: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    lines_total: int = 0
    lines_correct: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)

    def add(self, doc_id: str, label: Invoice, pred: Invoice | None) -> None:
        self.documents += 1
        if pred is None:  # extraction failed: every field counts as wrong
            for name in SCALAR_FIELDS:
                self.fields_total[name] += 1
            self.lines_total += len(label.lines)
            self.failures.append({"id": doc_id, "reason": "no extraction"})
            return
        wrong: list[str] = []
        want_values, got_values = _values(label), _values(pred)
        for name in SCALAR_FIELDS:
            want = _normalised(name, want_values[name])
            got = _normalised(name, got_values[name])
            self.fields_total[name] += 1
            if want == got:
                self.fields_correct[name] += 1
            else:
                wrong.append(f"{name}: label={want!r} got={got!r}")
        remaining = [_line_key(line) for line in pred.lines]
        for line in label.lines:
            self.lines_total += 1
            key = _line_key(line)
            if key in remaining:
                remaining.remove(key)
                self.lines_correct += 1
            else:
                wrong.append(f"line {line.line_id} {key[0]!r} not found")
        if wrong:
            self.failures.append({"id": doc_id, "reason": wrong})

    def report(self) -> str:
        out = [f"documents: {self.documents}", "field accuracy (exact after normalising):"]
        for name in SCALAR_FIELDS:
            t = self.fields_total[name]
            c = self.fields_correct[name]
            out.append(f"  {name:<18} {c:>4} of {t:<4} {100 * c / t if t else 0:6.1f} %")
        if self.lines_total:
            out.append(
                f"line items fully correct: {self.lines_correct} of {self.lines_total}"
                f" ({100 * self.lines_correct / self.lines_total:.1f} %)"
            )
        return "\n".join(out)


def run_evaluation(
    data_dir: Path,
    split: str = "dev",
    limit: int = 0,
    model: str | None = None,
    oracle: bool = False,
) -> tuple[Score, list[str]]:
    """Extract every digital PDF in the split and score it. Scans are skipped: they need OCR."""
    from einvoice.extract.llm import extract_invoice
    from einvoice.extract.text import read_pdf_text

    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    docs = [d for d in manifest["documents"] if d["split"] == split and d["variant"] == "digital"]
    if limit:
        docs = docs[:limit]
    score = Score()
    skipped: list[str] = []
    for d in docs:
        label = Invoice.model_validate_json((data_dir / d["label"]).read_text(encoding="utf-8"))
        pdf = data_dir / d["pdf"]
        if oracle:
            pred: Invoice | None = label
        else:
            text = read_pdf_text(pdf)
            if not text.has_text:
                skipped.append(d["id"])
                continue
            try:
                pred = extract_invoice(pdf, text, model=model)
            except Exception as exc:  # one bad document must not stop the run
                pred = None
                score.failures.append({"id": d["id"], "reason": f"error: {str(exc)[:200]}"})
        score.add(d["id"], label, pred)
    return score, skipped
