# E-Invoice Converter

Turns a German PDF invoice into a valid **XRechnung 3.0 (CII XML)** or **ZUGFeRD 2.3 EN 16931 (PDF/A-3)** e-invoice, checked by the official validators.

From 2027 German companies above €800,000 turnover must issue EN 16931 e-invoices, and from 2028 every business must. A PDF sent by email no longer counts.

> **Status: week 3 of 6.** Extraction runs end to end, and the first baseline is measured on the dev split. Accuracy is improving but still below target; see [Week 3 baseline](#week-3-baseline). OCR for scans is not built yet.

## Week 1 result

| Output | Validator | Result |
|---|---|---|
| `out/xrechnung.xml` | KoSIT 1.6.3 + XRechnung 3.0.2 config 2026-08-31 | accepted, 0 errors, 0 warnings |
| `out/zugferd.pdf` | Mustang 2.26.0 (veraPDF + EN 16931 schematron) | valid: PDF/A-3b compliant, 0 of 125 rules failed |

A negative test (`tests/test_validators.py`) breaks the grand total and checks that KoSIT rejects it with `BR-CO-15`, so a wrapper that always says PASS would fail CI.

## Week 2: the test set

| Part | Count | Dev / held out | Label source |
|---|---|---|---|
| Generated digital invoices | 300 (10 layouts × 30) | 50 / 250 | the generator |
| Degraded "scanned" copies | 100 (every third invoice) | 15 / 85 | same label as the source invoice |
| Real-world samples ([ZUGFeRD corpus](https://github.com/ZUGFeRD/corpus), Apache-2.0) | 42 PDFs of 25 distinct invoices | 10 / 32 | the CII XML embedded in each PDF |

KoSIT accepts **300 of 300** XRechnung files built from the generated labels, with 0 errors and 0 warnings. This is the check that the labels themselves are valid e-invoices.

**Layouts:** `craftsman_din` (DIN 5008 letter), `agency_modern`, `wholesaler_dense` (8–20 lines with article numbers), `one_line` (the line item written as a sentence), `multipage` (35–60 lines over 2 pages, repeated header and page numbers), `two_vat` (7 % and 19 % with A/B tax codes), `english`, `sidebar`, `legacy_mono` (old billing-tool look) and `footer_columns` (seller details in the page footer).

**Variation:** 
- Number formats: `1.234,56 €`, `1.234,56 EUR`, `€1,234.56`.
- Date formats: `02.11.2026`, `2. November 2026`, `02/11/2026`.
- Unit names (`Std.`/`h`/`Stunden`), invoice-number schemes, and optional fields: delivery date, due date, BIC, buyer VAT ID.
- Buyer reference: about 30 % carry a Leitweg-ID with valid check digits, the rest a purchase order number.
- IBANs and VAT IDs have valid check digits.

**Scans:** each page is rendered at 150 dpi, rotated 1–3°, blurred, given grey paper, noise and dust, and JPEG-compressed. The result is an image-only PDF with no text layer.

**What's committed:**
- `data/generated/labels/` and `manifest.json`: id, layout, variant, split, seed and label hash.
- `data/real/labels/`: the JSON label plus the original XML for each real sample.

PDFs are rebuilt from the seeds. Their exact pixels depend on the installed fonts, but their content doesn't. `tests/test_testset.py` regenerates every label and fails if one drifts.

**Real-world samples kept:** type code 380 in the BASIC, EN 16931 or EXTENDED profiles. 36 corpus files are skipped and listed in the manifest with the reason: MINIMUM and BASIC WL have no line items, and credit notes, corrections and similar documents are not type 380. The intarsys (ZUGFeRD 2.0) and symtrax (2.1) folders render the same invoices differently. They are split as groups, so the same invoice never sits in both dev and test.

```bash
uv run einvoice testset generate --n 300 --xml-only   # labels, manifest, XML (any OS)
uv run einvoice testset validate                      # KoSIT on all 300
uv run einvoice testset real                          # download the corpus samples
uv run einvoice testset generate --n 300              # + PDFs and scans (needs Pango)
```

WeasyPrint needs the Pango libraries. On Windows, render under WSL with a separate venv:

```bash
wsl -- bash -lc 'cd "/mnt/c/path/to/E-Invoice Converter" && UV_PROJECT_ENVIRONMENT=.venv-linux uv run einvoice testset generate --n 300'
```

## Week 3 baseline

Digital PDFs, development split (50 documents), model `groq/openai/gpt-oss-120b`. Full outputs: [v1](results/week3-baseline-dev.txt), [v2](results/week3-v2-dev.txt).

Comparing the two prompts on the 42 documents both extracted (the full runs also include Groq failures, see below):

| Field | v1 | v2 |
|---|---|---|
| number | 97.6 % | 97.6 % |
| issue_date | 100 % | 100 % |
| delivery_date | 54.8 % | **100 %** |
| buyer_reference | 83.3 % | **100 %** |
| seller.name | 61.9 % | **85.7 %** |
| seller.vat_id | 78.6 % | **90.5 %** |
| buyer.name | 92.9 % | **95.2 %** |
| iban | 100 % | 100 % |
| net / tax / gross total | 100 % | 95.2 % |
| line items fully correct | 81.4 % | **83.0 %** |

v2 is the default. The totals drop on two documents where the model dropped a line item, so that's the next thing to fix. Targets are 97 % for totals, VAT, IBAN and number, and 90 % for line items. Not met yet.

**Failures outside the prompt:** on the full v2 run, 6 of 50 documents had no extraction at all. Three were invalid JSON from Groq, and three ran out of retries on the rate limit. Those count as wrong in the full-run numbers, which is why they look lower than the common-document comparison.

**Still open:**
- Dropped line items (on two documents), which also drop the totals.
- Seller names in capitals or with a person's name still mismatched (about 14 %).
- Rate-limit and JSON failures on Groq's free tier.

One run takes about 20 minutes. The held-out split is untouched.

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
| 2 | Test invoice generator: 300 labelled PDFs, 10 layouts, degraded scans | done |
| 3 | Extraction: Docling/pdfplumber + LLM structured output, field-accuracy script | – |
| 4 | Rule checks, confidence flags, export + validator per output, held-out numbers | – |
| 5 | FastAPI `POST /convert`, PDF.js review screen, batch CLI, local model | – |
| 6 | Full held-out run, results table, demo, write-up | – |

Targets, fixed before building: on the held-out set, at least 90 % of digital invoices and 75 % of scanned ones pass the validator with no edits. At least 97 % field accuracy on totals, VAT, IBAN and invoice number. At least 95 % of wrong outputs caught before export.

## Limits (version 1)

The tool handles commercial invoices only (type code 380): no credit notes or partial invoices. It doesn't convert XML back to PDF, has no Peppol sending or accounting integration, and doesn't read handwritten invoices.

The generated invoices use German-language article catalogues even in the English layout, as a German company's English invoice would. VAT categories are standard-rated only (19 % and 7 %): no reverse charge or exempt lines yet.

All parties and IDs in the sample and generated invoices are fictitious. Real invoices never go in this repository.
