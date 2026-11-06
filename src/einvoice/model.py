"""Invoice data model: the one structure every step reads and writes.

Amounts are Decimal throughout; floats would produce the 0.01 differences
the EN 16931 rules reject. Field names map to EN 16931 business terms (BT-xx).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, Field

CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    """Round to cents, commercial rounding (half up)."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


class Address(BaseModel):
    street: str  # BT-35 / BT-50
    postcode: str  # BT-38 / BT-53
    city: str  # BT-37 / BT-52
    country_code: str = "DE"  # BT-40 / BT-55, ISO 3166-1 alpha-2


class Contact(BaseModel):
    name: str  # BT-41
    phone: str  # BT-42
    email: str  # BT-43


class Party(BaseModel):
    name: str  # BT-27 / BT-44
    address: Address
    vat_id: str | None = None  # BT-31 / BT-48
    electronic_address: str  # BT-34 / BT-49, sent with scheme EM (email)
    contact: Contact | None = None  # seller contact is mandatory in XRechnung (BR-DE-2)


class LineItem(BaseModel):
    line_id: str  # BT-126
    description: str  # BT-153
    seller_item_id: str | None = None  # BT-155, article number
    quantity: Decimal  # BT-129
    unit_code: str = "C62"  # BT-130, UN/ECE Rec 20 (C62 = piece, HUR = hour)
    unit_price: Decimal  # BT-146, net price
    vat_rate: Decimal  # BT-152
    vat_category: str = "S"  # BT-151, S = standard rate

    @property
    def net_amount(self) -> Decimal:  # BT-131
        return money(self.quantity * self.unit_price)


class VatBreakdown(BaseModel):
    category: str  # BT-118
    rate: Decimal  # BT-119
    basis: Decimal  # BT-116
    tax: Decimal  # BT-117


class Invoice(BaseModel):
    number: str  # BT-1
    issue_date: date  # BT-2
    type_code: str = "380"  # BT-3, commercial invoice
    currency: str = "EUR"  # BT-5
    due_date: date | None = None  # BT-9
    delivery_date: date | None = None  # BT-72
    buyer_reference: str  # BT-10, Leitweg-ID for public-sector buyers
    seller: Party
    buyer: Party
    lines: list[LineItem] = Field(min_length=1)
    iban: str  # BT-84
    bic: str | None = None  # BT-86
    payment_terms: str | None = None  # BT-20
    note: str | None = None  # BT-22

    @property
    def net_total(self) -> Decimal:  # BT-106 (= BT-109 with no allowances/charges)
        return sum((line.net_amount for line in self.lines), Decimal("0.00"))

    def vat_breakdown(self) -> list[VatBreakdown]:
        """One entry per (category, rate); tax is computed on the group sum (BR-CO-17)."""
        groups: dict[tuple[str, Decimal], Decimal] = defaultdict(lambda: Decimal("0.00"))
        for line in self.lines:
            groups[(line.vat_category, line.vat_rate)] += line.net_amount
        return [
            VatBreakdown(category=cat, rate=rate, basis=basis, tax=money(basis * rate / Decimal(100)))
            for (cat, rate), basis in sorted(groups.items(), key=lambda kv: kv[0][1])
        ]

    @property
    def tax_total(self) -> Decimal:  # BT-110
        return sum((v.tax for v in self.vat_breakdown()), Decimal("0.00"))

    @property
    def gross_total(self) -> Decimal:  # BT-112 (= BT-115 when nothing is prepaid)
        return self.net_total + self.tax_total
