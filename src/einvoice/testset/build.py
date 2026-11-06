"""Build the generated test set: PDFs, labels, XRechnung XML and a split manifest.

Layout of `out` (default data/generated):
    labels/<id>.json      the correct values, in the Invoice schema (committed to git)
    manifest.json         one entry per document, with layout, variant, split (committed)
    pdf/<id>.pdf          digital invoice;  pdf/<id>-scan.pdf degraded copy
    xml/<id>.xml          XRechnung CII built from the label (checked by KoSIT)
    html/<id>.html        the rendered HTML, kept for debugging

Invoice i uses layout i % 10 and seed BASE_SEED + i. Degraded copies are made for
every third invoice (100 of 300). The development split is 50 source invoices
(with their scans) chosen by a fixed seed; everything else is held out.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from einvoice.export.cii import to_cii_xml
from einvoice.labels import dumps, invoice_label
from einvoice.model import Invoice
from einvoice.testset.fake import random_invoice
from einvoice.testset.render import LAYOUTS, Layout, html_to_pdf, render_html

BASE_SEED = 20261105
DEV_SOURCES = 50
SCAN_EVERY = 3

Split = Literal["dev", "test"]
Variant = Literal["digital", "scan"]


@dataclass
class Entry:
    id: str
    source_id: str
    layout: str
    language: str
    variant: Variant
    split: Split
    seed: int
    pdf: str
    label: str
    label_sha256: str


def doc_id(i: int) -> str:
    return f"gen-{i:04d}"


def layout_for(i: int) -> Layout:
    return LAYOUTS[i % len(LAYOUTS)]


def invoice_for(i: int) -> Invoice:
    layout = layout_for(i)
    return random_invoice(BASE_SEED + i, layout.business, layout.lines, layout.language, layout.mixed_vat)


def label_json(invoice: Invoice) -> str:
    return dumps(invoice_label(invoice))


def dev_sources(n: int) -> set[int]:
    rng = random.Random(BASE_SEED)
    return set(rng.sample(range(n), min(DEV_SOURCES, n)))


def manifest_entries(n: int) -> list[Entry]:
    """Pure function of n: no files touched, so tests can recompute and compare."""
    dev = dev_sources(n)
    entries: list[Entry] = []
    for i in range(n):
        layout = layout_for(i)
        label = label_json(invoice_for(i))
        sha = hashlib.sha256(label.encode("utf-8")).hexdigest()
        split: Split = "dev" if i in dev else "test"
        variants: list[Variant] = ["digital", "scan"] if i % SCAN_EVERY == 0 else ["digital"]
        for variant in variants:
            suffix = "-scan" if variant == "scan" else ""
            entries.append(
                Entry(
                    id=doc_id(i) + suffix,
                    source_id=doc_id(i),
                    layout=layout.name,
                    language=layout.language,
                    variant=variant,
                    split=split,
                    seed=BASE_SEED + i,
                    pdf=f"pdf/{doc_id(i)}{suffix}.pdf",
                    label=f"labels/{doc_id(i)}.json",
                    label_sha256=sha,
                )
            )
    return entries


def write_labels(out: Path, n: int) -> list[Entry]:
    """Labels and manifest only: plain Python, works without WeasyPrint."""
    (out / "labels").mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (out / "labels" / f"{doc_id(i)}.json").write_text(label_json(invoice_for(i)), encoding="utf-8")
    entries = manifest_entries(n)
    manifest = {"base_seed": BASE_SEED, "count": n, "documents": [asdict(e) for e in entries]}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return entries


def build(out: Path, n: int = 300, render: bool = True, only: list[int] | None = None) -> list[Entry]:
    from einvoice.testset.degrade import degrade_pdf  # numpy/pdfium only needed here

    entries = write_labels(out, n)
    for sub in ("pdf", "xml", "html"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    for i in only if only is not None else range(n):
        invoice = invoice_for(i)
        (out / "xml" / f"{doc_id(i)}.xml").write_bytes(to_cii_xml(invoice, profile="xrechnung"))
        if not render:
            continue
        html = render_html(invoice, layout_for(i), BASE_SEED + i)
        (out / "html" / f"{doc_id(i)}.html").write_text(html, encoding="utf-8")
        pdf = html_to_pdf(html)
        (out / "pdf" / f"{doc_id(i)}.pdf").write_bytes(pdf)
        if i % SCAN_EVERY == 0:
            (out / "pdf" / f"{doc_id(i)}-scan.pdf").write_bytes(degrade_pdf(pdf, BASE_SEED + i))
        print(f"{doc_id(i)} {layout_for(i).name}", flush=True)
    return entries
