from decimal import Decimal

from einvoice.model import money
from einvoice.samples import craftsman_invoice


def test_totals_are_exact() -> None:
    inv = craftsman_invoice()
    # 12.5 h * 58.00 + 4 * 49.90 + 24.95
    assert inv.net_total == Decimal("949.55")
    breakdown = {v.rate: v for v in inv.vat_breakdown()}
    assert breakdown[Decimal("19")].basis == Decimal("924.60")
    assert breakdown[Decimal("19")].tax == Decimal("175.67")
    assert breakdown[Decimal("7")].tax == Decimal("1.75")
    assert inv.tax_total == Decimal("177.42")
    assert inv.gross_total == inv.net_total + inv.tax_total == Decimal("1126.97")


def test_money_rounds_half_up() -> None:
    assert money(Decimal("0.005")) == Decimal("0.01")
    assert money(Decimal("1.745")) == Decimal("1.75")
