"""The test set must not drift: labels in git must equal what the generator produces now."""

import json
from collections import Counter
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import pytest
from stdnum import iban
from stdnum.de import vat
from stdnum.iso7064 import mod_97_10

from einvoice.export.cii import to_cii_xml
from einvoice.labels import cii_to_label, invoice_label
from einvoice.model import Invoice
from einvoice.samples import craftsman_invoice
from einvoice.testset.build import BASE_SEED, invoice_for, label_json, layout_for, manifest_entries
from einvoice.testset.render import LAYOUTS, Formatter, render_html

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "data" / "generated"
REAL = ROOT / "data" / "real"
N = 300


def test_committed_labels_match_generator() -> None:
    manifest = json.loads((GENERATED / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["count"] == N
    assert manifest["documents"] == [asdict(e) for e in manifest_entries(N)]
    for i in range(N):
        committed = (GENERATED / "labels" / f"gen-{i:04d}.json").read_text(encoding="utf-8")
        assert committed == label_json(invoice_for(i)), f"label gen-{i:04d} drifted"


def test_split_and_variants() -> None:
    entries = manifest_entries(N)
    assert Counter(e.variant for e in entries) == {"digital": 300, "scan": 100}
    dev_sources = {e.source_id for e in entries if e.split == "dev"}
    assert len(dev_sources) == 50
    for e in entries:  # a scan never sits in another split than its source
        assert (e.source_id in dev_sources) == (e.split == "dev")
    assert {e.layout for e in entries} == {layout.name for layout in LAYOUTS}


@pytest.mark.parametrize("i", range(0, N, 7))
def test_generated_invoice_is_consistent(i: int) -> None:
    inv = invoice_for(i)
    assert iban.is_valid(inv.iban)
    assert inv.seller.vat_id and vat.is_valid(inv.seller.vat_id)
    assert inv.buyer.vat_id is None or vat.is_valid(inv.buyer.vat_id)
    if inv.buyer_reference.count("-") == 2:  # Leitweg-ID check digits
        assert mod_97_10.is_valid(inv.buyer_reference.replace("-", ""))
    assert inv.due_date is None or inv.due_date >= inv.issue_date
    assert inv.delivery_date is None or inv.delivery_date <= inv.issue_date
    assert inv.payment_terms or inv.due_date
    lo, hi = layout_for(i).lines
    assert lo <= len(inv.lines) <= hi
    if layout_for(i).mixed_vat:
        assert {v.rate for v in inv.vat_breakdown()} == {Decimal(7), Decimal(19)}
    # the label round-trips into the model
    label = json.loads(label_json(inv))
    label.pop("totals")
    for line in label["lines"]:
        line.pop("net_amount")
    assert Invoice.model_validate(label) == inv


@pytest.mark.parametrize("layout_index", range(len(LAYOUTS)))
def test_every_layout_shows_the_key_values(layout_index: int) -> None:
    inv = invoice_for(layout_index)
    layout = LAYOUTS[layout_index]
    html = render_html(inv, layout, BASE_SEED + layout_index)
    fmt = Formatter(layout.language, BASE_SEED + layout_index)
    for value in [inv.number, inv.iban, fmt.money(inv.gross_total), fmt.date(inv.issue_date)]:
        assert value.upper() in html.upper(), (layout.name, value)
    for line in inv.lines:
        assert fmt.money(line.net_amount) in html, (layout.name, line.line_id)


def test_cii_reader_round_trips_our_export() -> None:
    inv = craftsman_invoice()
    from_xml = cii_to_label(to_cii_xml(inv, profile="xrechnung"))
    expected = invoice_label(inv)
    for key in [
        "number",
        "issue_date",
        "due_date",
        "delivery_date",
        "buyer_reference",
        "iban",
        "bic",
        "payment_terms",
    ]:
        assert from_xml[key] == expected[key], key
    assert from_xml["seller"]["vat_id"] == expected["seller"]["vat_id"]
    assert from_xml["totals"]["gross_total"] == expected["totals"]["gross_total"]
    assert [Decimal(x["net_amount"]) for x in from_xml["lines"]] == [
        Decimal(x["net_amount"]) for x in expected["lines"]
    ]


def test_real_samples_manifest() -> None:
    manifest = json.loads((REAL / "manifest.json").read_text(encoding="utf-8"))
    docs = manifest["documents"]
    assert 30 <= len(docs) <= 50
    assert Counter(d["split"] for d in docs)["dev"] == 10
    groups: dict[str, set[str]] = {}
    for d in docs:
        groups.setdefault(d["group"], set()).add(d["split"])
        label = json.loads((REAL / d["label"]).read_text(encoding="utf-8"))
        assert label["type_code"] == "380" and label["lines"]
    assert all(len(splits) == 1 for splits in groups.values()), "a group is split across dev and test"
