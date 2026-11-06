"""Invoice model -> UN/CEFACT CII XML (XRechnung 3.0 or ZUGFeRD EN 16931 profile)."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from drafthorse.models.accounting import ApplicableTradeTax
from drafthorse.models.document import Document
from drafthorse.models.note import IncludedNote
from drafthorse.models.party import TaxRegistration, TradeParty
from drafthorse.models.payment import PaymentMeans, PaymentTerms
from drafthorse.models.tradelines import LineItem as CiiLineItem

from einvoice.model import Invoice, Party

Profile = Literal["xrechnung", "en16931"]

GUIDELINE_IDS: dict[Profile, str] = {
    "xrechnung": "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0",
    "en16931": "urn:cen.eu:en16931:2017",
}
PEPPOL_BILLING = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
SEPA_CREDIT_TRANSFER = "58"  # UNTDID 4461


def _fill_party(target: TradeParty, party: Party) -> None:
    target.name = party.name
    target.address.line_one = party.address.street
    target.address.postcode = party.address.postcode
    target.address.city_name = party.address.city
    target.address.country_id = party.address.country_code
    target.electronic_address.uri_ID = ("EM", party.electronic_address)
    if party.vat_id:
        target.tax_registrations.add(TaxRegistration(id=("VA", party.vat_id)))
    if party.contact:
        target.contact.person_name = party.contact.name
        target.contact.telephone.number = party.contact.phone
        target.contact.email.address = party.contact.email


def build_document(invoice: Invoice, profile: Profile = "xrechnung") -> Document:
    doc = Document()
    doc.context.business_parameter.id = PEPPOL_BILLING
    doc.context.guideline_parameter.id = GUIDELINE_IDS[profile]

    doc.header.id = invoice.number
    doc.header.type_code = invoice.type_code
    doc.header.issue_date_time = invoice.issue_date
    if invoice.note:
        doc.header.notes.add(IncludedNote(content=invoice.note))

    agreement = doc.trade.agreement
    agreement.buyer_reference = invoice.buyer_reference
    _fill_party(agreement.seller, invoice.seller)
    _fill_party(agreement.buyer, invoice.buyer)

    if invoice.delivery_date:
        doc.trade.delivery.event.occurrence = invoice.delivery_date

    for line in invoice.lines:
        li = CiiLineItem()
        li.document.line_id = line.line_id
        li.product.name = line.description
        li.agreement.net.amount = line.unit_price
        li.delivery.billed_quantity = (line.quantity, line.unit_code)
        li.settlement.trade_tax.type_code = "VAT"
        li.settlement.trade_tax.category_code = line.vat_category
        li.settlement.trade_tax.rate_applicable_percent = line.vat_rate
        li.settlement.monetary_summation.total_amount = line.net_amount
        doc.trade.items.add(li)

    settlement = doc.trade.settlement
    settlement.currency_code = invoice.currency

    means = PaymentMeans()
    means.type_code = SEPA_CREDIT_TRANSFER
    means.payee_account.iban = invoice.iban
    if invoice.bic:
        means.payee_institution.bic = invoice.bic
    settlement.payment_means.add(means)

    for vat in invoice.vat_breakdown():
        tax = ApplicableTradeTax()
        tax.calculated_amount = vat.tax
        tax.basis_amount = vat.basis
        tax.type_code = "VAT"
        tax.category_code = vat.category
        tax.rate_applicable_percent = vat.rate
        settlement.trade_tax.add(tax)

    if invoice.payment_terms or invoice.due_date:
        terms = PaymentTerms()
        if invoice.payment_terms:
            terms.description = invoice.payment_terms
        if invoice.due_date:
            terms.due = invoice.due_date
        settlement.terms.add(terms)

    sums = settlement.monetary_summation
    sums.line_total = invoice.net_total
    sums.charge_total = Decimal("0.00")
    sums.allowance_total = Decimal("0.00")
    sums.tax_basis_total = invoice.net_total
    sums.tax_total = (invoice.tax_total, invoice.currency)
    sums.grand_total = invoice.gross_total
    sums.due_amount = invoice.gross_total
    return doc


def to_cii_xml(invoice: Invoice, profile: Profile = "xrechnung") -> bytes:
    """Serialize and check against the Factur-X EN 16931 XSD (drafthorse does the XSD step)."""
    return bytes(build_document(invoice, profile).serialize(schema="FACTUR-X_EN16931"))
