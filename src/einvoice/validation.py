"""Run the official validators: KoSIT (XRechnung) and Mustang (ZUGFeRD + PDF/A).

The validators are Java tools fetched by scripts/fetch_validators.sh into tools/.
Paths can be overridden with EINVOICE_TOOLS and JAVA (path to the java binary).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[2]


def _nodes(node: etree._Element | etree._ElementTree, path: str, ns: dict[str, str]) -> list[etree._Element]:
    """xpath() returns a wide union type; keep only elements."""
    result = node.xpath(path, namespaces=ns)
    return [r for r in result if isinstance(r, etree._Element)] if isinstance(result, list) else []


def _text(el: etree._Element) -> str:
    return " ".join("".join(str(t) for t in el.itertext()).split())


def tools_dir() -> Path:
    return Path(os.environ.get("EINVOICE_TOOLS", ROOT / "tools"))


def java() -> str:
    found = os.environ.get("JAVA") or shutil.which("java")
    if not found:
        raise RuntimeError("Java not found: install a JRE (17+) or set JAVA=/path/to/java")
    return found


@dataclass
class ValidationResult:
    validator: str
    file: Path
    accepted: bool
    errors: list[str] = field(default_factory=list)
    report: Path | None = None  # stored report file

    def summary(self) -> str:
        status = "PASS" if self.accepted else "FAIL"
        lines = [f"[{status}] {self.validator}: {self.file.name} ({len(self.errors)} errors)"]
        lines += [f"    - {e}" for e in self.errors]
        if self.report:
            lines.append(f"    report: {self.report}")
        return "\n".join(lines)


def validate_xrechnung(xml_file: Path, report_dir: Path | None = None) -> ValidationResult:
    """KoSIT validator with the XRechnung configuration; error = any failed assert of level error/fatal."""
    return validate_xrechnung_many([xml_file], report_dir)[0]


def validate_xrechnung_many(
    xml_files: list[Path], report_dir: Path | None = None, html: bool = True, chunk: int = 50
) -> list[ValidationResult]:
    """One JVM per chunk of files: starting KoSIT costs seconds, checking a file milliseconds."""
    config = tools_dir() / "xrechnung-config"
    out = Path(report_dir or tempfile.mkdtemp(prefix="kosit-")).resolve()
    out.mkdir(parents=True, exist_ok=True)
    files = [f.resolve() for f in xml_files]
    results: list[ValidationResult] = []
    for start in range(0, len(files), chunk):
        batch = files[start : start + chunk]
        for f in batch:  # never read a stale report from an earlier run
            (out / f"{f.stem}-report.xml").unlink(missing_ok=True)
        cmd = [java(), "-jar", str(tools_dir() / "validator.jar")]
        cmd += ["-s", str(config / "scenarios.xml"), "-r", str(config), "-o", str(out)]
        if html:
            cmd.append("-h")  # also write an HTML report next to the XML report
        proc = subprocess.run(cmd + [str(f) for f in batch], capture_output=True, text=True, check=False)
        for f in batch:
            report = out / f"{f.stem}-report.xml"
            if report.exists():
                results.append(_parse_kosit_report(f, report))
            else:
                results.append(ValidationResult("KoSIT", f, False, [(proc.stdout + proc.stderr)[-2000:]]))
    return results


def _parse_kosit_report(xml_file: Path, report: Path) -> ValidationResult:
    tree = etree.parse(str(report))
    ns = {
        "rep": "http://www.xoev.de/de/validator/varl/1",
        "svrl": "http://purl.oclc.org/dsdl/svrl",
        "s": "http://www.xoev.de/de/validator/framework/1/scenarios",
    }
    accepted = bool(_nodes(tree, "//rep:assessment/rep:accept", ns))
    errors: list[str] = []
    # Schema (XSD) messages
    for msg in _nodes(tree, "//rep:message[@level='error']", ns):
        errors.append(f"{msg.get('code', 'XSD')}: {_text(msg)}")
    # Schematron failed asserts of level error/fatal
    for fa in _nodes(tree, "//svrl:failed-assert", ns):
        if fa.get("flag", "error") in ("error", "fatal"):
            errors.append(f"{fa.get('id')}: {_text(fa)}")
    return ValidationResult("KoSIT", xml_file, accepted and not errors, errors, report)


def validate_zugferd(pdf_file: Path, report_dir: Path | None = None) -> ValidationResult:
    """Mustang CLI: checks PDF/A-3 (veraPDF), the embedded XML (XSD + EN 16931 schematron)."""
    pdf_file = pdf_file.resolve()
    cmd = [
        java(),
        "-jar",
        str(tools_dir() / "mustang.jar"),
        "--no-notices",
        "--action",
        "validate",
        "--source",
        str(pdf_file),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    match = re.search(r"<validation.*</validation>", proc.stdout, re.S)
    if not match:
        return ValidationResult("Mustang", pdf_file, False, [proc.stdout[-2000:] + proc.stderr[-2000:]])
    xml = match.group(0)
    report: Path | None = None
    if report_dir:
        report_dir.mkdir(parents=True, exist_ok=True)
        report = report_dir / f"{pdf_file.stem}-mustang-report.xml"
        report.write_text(xml, encoding="utf-8")
    root = etree.fromstring(xml.encode("utf-8"))
    status = root.xpath("string(/validation/summary/@status)")
    errors = [_text(e) for e in _nodes(root, "//error", {})]
    errors = list(dict.fromkeys(e for e in errors if e))  # dedupe, keep order
    return ValidationResult("Mustang", pdf_file, status == "valid" and not errors, errors, report)
