# E-Invoice Converter

Turns a German PDF invoice into a valid **XRechnung 3.0 (CII XML)** or **ZUGFeRD 2.3 EN 16931 (PDF/A-3)** e-invoice, checked by the official validators.

From 2027 German companies above €800,000 turnover must issue EN 16931 e-invoices, and from 2028 every business must. A PDF sent by email no longer counts.

> **Status: week 1 of 6.** The validators run, and one hand-made invoice passes both. PDF extraction is not built yet. See the [project plan](#plan).

## Week 1 result

| Output | Validator | Result |
|---|---|---|
| `out/xrechnung.xml` | KoSIT 1.6.3 + XRechnung 3.0.2 config 2026-08-31 | accepted, 0 errors, 0 warnings |
| `out/zugferd.pdf` | Mustang 2.26.0 (veraPDF + EN 16931 schematron) | valid: PDF/A-3b compliant, 0 of 125 rules failed |

A negative test (`tests/test_validators.py`) breaks the grand total and checks that KoSIT rejects it with `BR-CO-15`, so a wrapper that always says PASS would fail CI.

## Quick start

Needs Python 3.12, [uv](https://docs.astral.sh/uv/) and Java 17 or newer.

```bash
uv sync
bash scripts/fetch_validators.sh   # downloads the pinned validators into tools/
make check                          # lint, mypy strict, tests, then validate both sample files
```

Without `make`:

```bash
uv run einvoice sample --out out
uv run einvoice validate out/xrechnung.xml out/zugferd.pdf
```

If `java` isn't on your PATH, set `JAVA=/path/to/java`. Validator reports go to `out/reports/`.

With Docker:

```bash
docker compose up --build
```

This runs the app container, which builds and validates the samples. It also starts the KoSIT validator as an HTTP service on `localhost:8081`.

## How the export works

1. `einvoice.model.Invoice` is a Pydantic model whose fields map to EN 16931 business terms (BT-1, BT-2, …). Totals and the VAT breakdown are computed with `Decimal` and half-up rounding.
2. `einvoice.export.cii` builds CII XML with [drafthorse](https://github.com/pretix/drafthorse) and checks it against the Factur-X EN 16931 XSD. The `xrechnung` and `en16931` profiles differ only in the guideline ID.
3. `einvoice.export.zugferd` draws the visible page with reportlab, using embedded Vera fonts. It then adds an sRGB OutputIntent and has drafthorse attach `factur-x.xml` with the PDF/A-3 XMP metadata.
4. `einvoice.validation` runs KoSIT and Mustang, parses their reports and stores them.

## Pinned versions

| Tool | Version |
|---|---|
| KoSIT validator | 1.6.3 |
| XRechnung validator configuration | v2026-08-31 (XRechnung 3.0.2) |
| Mustang CLI | 2.26.0 |
| drafthorse | 2025.2.0 |

The versions are set in `scripts/fetch_validators.sh` and `docker/validator.Dockerfile`. A new XRechnung release means bumping them deliberately.

## Plan

| Week | Deliverable | Status |
|---|---|---|
| 1 | Validators in CI, a hand-made XRechnung and ZUGFeRD that pass | done |
| 2 | Test invoice generator: 300 labelled PDFs, 10 layouts, degraded scans | – |
| 3 | Extraction: Docling/pdfplumber + LLM structured output, field-accuracy script | – |
| 4 | Rule checks, confidence flags, export + validator per output, held-out numbers | – |
| 5 | FastAPI `POST /convert`, PDF.js review screen, batch CLI, local model | – |
| 6 | Full held-out run, results table, demo, write-up | – |

Targets, fixed before building: on the held-out set, at least 90 % of digital invoices and 75 % of scanned ones pass the validator with no edits. At least 97 % field accuracy on totals, VAT, IBAN and invoice number. At least 95 % of wrong outputs caught before export.

## Limits (version 1)

The tool handles commercial invoices only (type code 380): no credit notes or partial invoices. It doesn't convert XML back to PDF, has no Peppol sending or accounting integration, and doesn't read handwritten invoices.

All parties and IDs in the sample invoice are fictitious. Real invoices never go in this repository.
