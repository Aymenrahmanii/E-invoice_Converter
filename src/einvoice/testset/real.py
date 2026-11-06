"""Real-world samples: the ZUGFeRD 2.x example PDFs from github.com/ZUGFeRD/corpus (Apache-2.0).

Each sample carries its correct CII XML inside, which becomes the label. Kept are
commercial invoices (type code 380) in the BASIC, EN 16931 or EXTENDED profiles,
because MINIMUM and BASIC WL have no line items. The PDFs are not committed;
`data/real/manifest.json` and `data/real/labels/` are.

The intarsys (ZUGFeRD 2.0) and symtrax (2.1) sets contain the same invoices with
different renderings, so samples are grouped by invoice name and split by group.
"""

from __future__ import annotations

import io
import json
import random
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from einvoice.labels import cii_profile, cii_to_label, dumps

CORPUS = "ZUGFeRD/corpus"
COMMIT = "master"
TREE_URL = f"https://api.github.com/repos/{CORPUS}/git/trees/{COMMIT}?recursive=1"
RAW_URL = f"https://raw.githubusercontent.com/{CORPUS}/{COMMIT}/"
PREFIX = "ZUGFeRDv2/correct/"
XML_NAMES = ("factur-x.xml", "zugferd-invoice.xml", "xrechnung.xml", "ZUGFeRD-invoice.xml")
DEV_DOCS = 10  # plan: 10 real samples for prompt tuning, the rest held out
SPLIT_SEED = 20261105

ALLOWED_PROFILES = ("en16931", "basic", "extended", "xrechnung")
EXCLUDED_PROFILES = ("minimum", "basicwl")


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "einvoice-testset"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return bytes(resp.read())


def list_corpus_pdfs() -> list[str]:
    tree = json.loads(_get(TREE_URL))
    return sorted(
        t["path"] for t in tree["tree"] if t["path"].startswith(PREFIX) and t["path"].lower().endswith(".pdf")
    )


def embedded_xml(pdf: bytes) -> bytes | None:
    attachments = PdfReader(io.BytesIO(pdf)).attachments
    for name in XML_NAMES:
        for key, data in attachments.items():
            if key.lower() == name.lower() and data:
                return bytes(data[0])
    return None


def profile_ok(profile: str | None) -> bool:
    p = (profile or "").lower().replace(" ", "").replace("-", "").replace("_", "")
    if any(x in p for x in EXCLUDED_PROFILES):
        return False
    return any(x in p for x in ALLOWED_PROFILES) or p.endswith("urn:cen.eu:en16931:2017")


def group_name(path: str) -> str:
    """'.../zugferd_2p1_EN16931_Einfach.pdf' -> 'EN16931_Einfach' (same invoice, other renderer)."""
    stem = Path(path).stem
    return re.sub(r"^zugferd_2p\d_", "", stem)


def fetch_corpus(out: Path) -> list[dict[str, Any]]:
    (out / "pdf").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    kept: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for path in list_corpus_pdfs():
        doc_id = "real-" + re.sub(r"[^A-Za-z0-9]+", "-", path[len(PREFIX) : -4]).strip("-").lower()
        pdf_file = out / "pdf" / f"{doc_id}.pdf"
        if not pdf_file.exists():
            pdf_file.write_bytes(_get(RAW_URL + urllib.parse.quote(path)))
        xml = embedded_xml(pdf_file.read_bytes())
        if xml is None:
            skipped.append({"path": path, "reason": "no embedded XML"})
            continue
        profile = cii_profile(xml)
        if not profile_ok(profile):
            skipped.append({"path": path, "reason": f"profile {profile}"})
            continue
        label = cii_to_label(xml)
        if label["type_code"] != "380":
            skipped.append({"path": path, "reason": f"type code {label['type_code']}"})
            continue
        if not label["lines"]:
            skipped.append({"path": path, "reason": "no line items"})
            continue
        (out / "labels" / f"{doc_id}.json").write_text(dumps(label), encoding="utf-8")
        (out / "labels" / f"{doc_id}.xml").write_bytes(xml)
        kept.append(
            {
                "id": doc_id,
                "source": f"https://github.com/{CORPUS}/blob/{COMMIT}/{urllib.parse.quote(path)}",
                "group": group_name(path),
                "profile": profile,
                "pdf": f"pdf/{doc_id}.pdf",
                "label": f"labels/{doc_id}.json",
                "label_xml": f"labels/{doc_id}.xml",
            }
        )
    groups = sorted({k["group"] for k in kept})
    random.Random(SPLIT_SEED).shuffle(groups)
    dev: set[str] = set()
    for g in groups:  # whole groups into dev until it holds DEV_DOCS documents
        if sum(k["group"] in dev for k in kept) >= DEV_DOCS:
            break
        dev.add(g)
    for k in kept:
        k["split"] = "dev" if k["group"] in dev else "test"
    manifest = {"corpus": CORPUS, "license": "Apache-2.0", "documents": kept, "skipped": skipped}
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return kept
