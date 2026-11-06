"""Run the official validators. Skipped when Java or tools/ is missing (run scripts/fetch_validators.sh)."""

from decimal import Decimal
from pathlib import Path

import pytest

from einvoice.export.cii import build_document, to_cii_xml
from einvoice.export.zugferd import to_zugferd_pdf
from einvoice.samples import craftsman_invoice
from einvoice.validation import java, tools_dir, validate_xrechnung, validate_zugferd


def _validators_available() -> bool:
    try:
        java()
    except RuntimeError:
        return False
    return (tools_dir() / "validator.jar").exists() and (tools_dir() / "mustang.jar").exists()


pytestmark = [
    pytest.mark.validator,
    pytest.mark.skipif(not _validators_available(), reason="Java or validator jars not available"),
]


def test_xrechnung_passes_kosit(tmp_path: Path) -> None:
    f = tmp_path / "xrechnung.xml"
    f.write_bytes(to_cii_xml(craftsman_invoice(), profile="xrechnung"))
    result = validate_xrechnung(f, tmp_path / "reports")
    assert result.accepted, result.summary()


def test_kosit_rejects_wrong_total(tmp_path: Path) -> None:
    """Guard against a validator wrapper that always says PASS."""
    doc = build_document(craftsman_invoice(), profile="xrechnung")
    doc.trade.settlement.monetary_summation.grand_total = Decimal("9999.99")
    f = tmp_path / "broken.xml"
    f.write_bytes(bytes(doc.serialize(schema="FACTUR-X_EN16931")))
    result = validate_xrechnung(f, tmp_path / "reports")
    assert not result.accepted
    assert any("BR-CO-15" in e for e in result.errors), result.summary()


def test_zugferd_passes_mustang(tmp_path: Path) -> None:
    f = tmp_path / "zugferd.pdf"
    f.write_bytes(to_zugferd_pdf(craftsman_invoice()))
    result = validate_zugferd(f, tmp_path / "reports")
    assert result.accepted, result.summary()
