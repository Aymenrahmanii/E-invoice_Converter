"""A hand-made invoice with known values, used to prove the export passes the validators.

All parties, IDs and addresses are fictitious. The IBAN is the standard
documentation example (valid check digits); the VAT IDs have valid check digits.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from einvoice.model import Address, Contact, Invoice, LineItem, Party


def craftsman_invoice() -> Invoice:
    """Two VAT rates (19 % labour and material, 7 % book), so the breakdown has two groups."""
    return Invoice(
        number="RE-2026-0001",
        issue_date=date(2026, 11, 2),
        due_date=date(2026, 11, 16),
        delivery_date=date(2026, 10, 30),
        buyer_reference="04011000-12345-34",  # Leitweg-ID format; any reference works for B2B
        seller=Party(
            name="Malerbetrieb Muster GmbH",
            address=Address(street="Hauptstraße 12", postcode="10115", city="Berlin"),
            vat_id="DE136695976",
            electronic_address="rechnung@malerbetrieb-muster.example",
            contact=Contact(
                name="Erika Muster",
                phone="+49 30 1234567",
                email="erika.muster@malerbetrieb-muster.example",
            ),
        ),
        buyer=Party(
            name="Beispiel Immobilien AG",
            address=Address(street="Am Markt 3", postcode="80331", city="München"),
            vat_id="DE129273398",
            electronic_address="eingangsrechnung@beispiel-immobilien.example",
        ),
        lines=[
            LineItem(
                line_id="1",
                description="Malerarbeiten Treppenhaus, Arbeitszeit",
                quantity=Decimal("12.5"),
                unit_code="HUR",
                unit_price=Decimal("58.00"),
                vat_rate=Decimal("19"),
            ),
            LineItem(
                line_id="2",
                description="Wandfarbe weiß, 10 l Eimer",
                quantity=Decimal("4"),
                unit_price=Decimal("49.90"),
                vat_rate=Decimal("19"),
            ),
            LineItem(
                line_id="3",
                description="Farbratgeber (Buch)",
                quantity=Decimal("1"),
                unit_price=Decimal("24.95"),
                vat_rate=Decimal("7"),
            ),
        ],
        iban="DE89370400440532013000",
        bic="COBADEFFXXX",
        payment_terms="Zahlbar innerhalb von 14 Tagen ohne Abzug.",
    )
