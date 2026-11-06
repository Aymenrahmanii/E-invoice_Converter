"""Command line: `einvoice sample` writes the hand-made invoices, `einvoice validate` checks files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from einvoice.export.cii import to_cii_xml
from einvoice.export.zugferd import to_zugferd_pdf
from einvoice.samples import craftsman_invoice
from einvoice.validation import ValidationResult, validate_xrechnung, validate_zugferd


def cmd_sample(args: argparse.Namespace) -> int:
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    invoice = craftsman_invoice()
    (out / "xrechnung.xml").write_bytes(to_cii_xml(invoice, profile="xrechnung"))
    (out / "zugferd.pdf").write_bytes(to_zugferd_pdf(invoice))
    print(f"wrote {out / 'xrechnung.xml'} and {out / 'zugferd.pdf'}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    results: list[ValidationResult] = []
    for f in args.files:
        if f.suffix.lower() == ".pdf":
            results.append(validate_zugferd(f, args.reports))
        else:
            results.append(validate_xrechnung(f, args.reports))
    for r in results:
        print(r.summary())
    return 0 if all(r.accepted for r in results) else 1


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

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
