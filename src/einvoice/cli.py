"""Command line.

einvoice sample                  hand-made XRechnung + ZUGFeRD invoice
einvoice validate FILE...        KoSIT (.xml) or Mustang (.pdf)
einvoice testset generate        labelled test invoices (needs WeasyPrint/Pango to render)
einvoice testset validate        run KoSIT on every generated XML
einvoice testset real            download the public ZUGFeRD samples with their XML labels
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from einvoice.export.cii import to_cii_xml
from einvoice.export.zugferd import to_zugferd_pdf
from einvoice.samples import craftsman_invoice
from einvoice.validation import (
    ValidationResult,
    validate_xrechnung_many,
    validate_zugferd,
)

GENERATED = Path("data/generated")
REAL = Path("data/real")


def cmd_sample(args: argparse.Namespace) -> int:
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    invoice = craftsman_invoice()
    (out / "xrechnung.xml").write_bytes(to_cii_xml(invoice, profile="xrechnung"))
    (out / "zugferd.pdf").write_bytes(to_zugferd_pdf(invoice))
    print(f"wrote {out / 'xrechnung.xml'} and {out / 'zugferd.pdf'}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    files: list[Path] = args.files
    results: list[ValidationResult] = validate_xrechnung_many(
        [f for f in files if f.suffix.lower() != ".pdf"], args.reports
    )
    results += [validate_zugferd(f, args.reports) for f in files if f.suffix.lower() == ".pdf"]
    for r in results:
        print(r.summary())
    return 0 if all(r.accepted for r in results) else 1


def cmd_testset_generate(args: argparse.Namespace) -> int:
    from einvoice.testset.build import build, write_labels

    if args.labels_only:
        entries = write_labels(args.out, args.n)
    else:
        only = list(range(args.first, min(args.n, args.first + args.limit))) if args.limit else None
        entries = build(args.out, args.n, render=not args.xml_only, only=only)
    counts = Counter((e.split, e.variant) for e in entries)
    print(
        f"{len(entries)} documents in {args.out}: "
        + ", ".join(f"{s}/{v}={c}" for (s, v), c in sorted(counts.items()))
    )
    return 0


def cmd_testset_validate(args: argparse.Namespace) -> int:
    xml_dir: Path = args.dir / "xml"
    files = sorted(xml_dir.glob("*.xml"))
    if not files:
        print(f"no XML in {xml_dir}; run `einvoice testset generate` first")
        return 1
    results = validate_xrechnung_many(files, args.dir / "reports", html=False)
    failed = [r for r in results if not r.accepted]
    for r in failed:
        print(r.summary())
    summary = {
        "validator": "KoSIT",
        "checked": len(results),
        "accepted": len(results) - len(failed),
        "failed": [r.file.name for r in failed],
    }
    (args.dir / "validation.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(f"KoSIT accepted {summary['accepted']} of {summary['checked']} generated XRechnung files")
    return 0 if not failed else 1


def cmd_testset_real(args: argparse.Namespace) -> int:
    from einvoice.testset.real import fetch_corpus

    kept = fetch_corpus(args.out)
    print(f"{len(kept)} real-world samples with labels in {args.out}")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    from einvoice.extract.llm import extract_invoice
    from einvoice.extract.text import read_pdf_text

    text = read_pdf_text(args.file)
    if not text.has_text:
        print(f"{args.file.name}: no text layer (scanned); OCR is not built yet")
        return 2
    invoice = extract_invoice(args.file, text, model=args.model, cache=not args.no_cache)
    print(invoice.model_dump_json(indent=2))
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    from einvoice.evaluate import run_evaluation

    score, skipped = run_evaluation(args.dir, args.split, args.limit, args.model, oracle=args.oracle)
    print(score.report())
    if skipped:
        print(f"skipped {len(skipped)} scanned documents (no text layer; OCR not built yet)")
    if score.failures:
        print(f"\n{len(score.failures)} documents with problems:")
        for f in score.failures[: args.show]:
            print(f"  {f['id']}: {f['reason']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="einvoice")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sample", help="write the hand-made XRechnung and ZUGFeRD invoices")
    p.add_argument("--out", type=Path, default=Path("out"))
    p.set_defaults(func=cmd_sample)

    p = sub.add_parser("validate", help="run KoSIT (.xml) or Mustang (.pdf) on files")
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("--reports", type=Path, default=Path("out/reports"))
    p.set_defaults(func=cmd_validate)

    ts = sub.add_parser("testset", help="build and check the labelled test set").add_subparsers(
        dest="testset_command", required=True
    )
    p = ts.add_parser("generate", help="generate labelled invoice PDFs")
    p.add_argument("--n", type=int, default=300)
    p.add_argument("--out", type=Path, default=GENERATED)
    p.add_argument("--labels-only", action="store_true", help="labels + manifest only, no PDFs")
    p.add_argument("--xml-only", action="store_true", help="labels, manifest and XML; no PDFs (no Pango)")
    p.add_argument("--first", type=int, default=0, help="first invoice index to render")
    p.add_argument("--limit", type=int, default=0, help="render only this many (0 = all)")
    p.set_defaults(func=cmd_testset_generate)

    p = ts.add_parser("validate", help="run KoSIT on all generated XML")
    p.add_argument("--dir", type=Path, default=GENERATED)
    p.set_defaults(func=cmd_testset_validate)

    p = ts.add_parser("real", help="download public ZUGFeRD samples, labels from their embedded XML")
    p.add_argument("--out", type=Path, default=REAL)
    p.set_defaults(func=cmd_testset_real)

    p = sub.add_parser("extract", help="extract one digital invoice PDF to JSON with the LLM")
    p.add_argument("file", type=Path)
    p.add_argument("--model", default=None, help="LiteLLM model string (default: EINVOICE_MODEL)")
    p.add_argument("--no-cache", action="store_true")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("evaluate", help="field accuracy of the extraction against the labels")
    p.add_argument("--dir", type=Path, default=GENERATED)
    p.add_argument("--split", default="dev", choices=["dev", "test"])
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--model", default=None)
    p.add_argument(
        "--oracle", action="store_true", help="score the labels against themselves (must be 100 %)"
    )
    p.add_argument("--show", type=int, default=10, help="how many failures to list")
    p.set_defaults(func=cmd_evaluate)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
