"""Labels: the correct values for one invoice, as JSON.

Generated labels come from the Invoice model. Real-world labels come from the CII XML
embedded in the sample PDF (see `cii_to_label`): the official XML is the truth there.
Both have the same keys. Real-world labels may have nulls where the XML has no value,
and their stated totals can differ from line sums (allowances, charges, prepayments),
which is why the totals are stored explicitly instead of recomputed.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

from lxml import etree

from einvoice.model import Invoice

NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
}


def invoice_label(invoice: Invoice) -> dict[str, Any]:
    label: dict[str, Any] = json.loads(invoice.model_dump_json())
    label["totals"] = {
        "net_total": str(invoice.net_total),
        "tax_total": str(invoice.tax_total),
        "gross_total": str(invoice.gross_total),
        "due_amount": str(invoice.gross_total),
        "vat_breakdown": [json.loads(v.model_dump_json()) for v in invoice.vat_breakdown()],
    }
    for line, raw in zip(invoice.lines, label["lines"], strict=True):
        raw["net_amount"] = str(line.net_amount)
    return label


def dumps(label: dict[str, Any]) -> str:
    return json.dumps(label, indent=2, ensure_ascii=False) + "\n"


# --- CII XML -> label --------------------------------------------------------------


def _first(node: etree._Element, path: str) -> etree._Element | None:
    found = node.xpath(path, namespaces=NS)
    if isinstance(found, list):
        for item in found:
            if isinstance(item, etree._Element):
                return item
    return None


def _all(node: etree._Element, path: str) -> list[etree._Element]:
    found = node.xpath(path, namespaces=NS)
    return [f for f in found if isinstance(f, etree._Element)] if isinstance(found, list) else []


def _text(node: etree._Element, path: str) -> str | None:
    el = _first(node, path)
    if el is None or el.text is None:
        return None
    return " ".join(el.text.split()) or None


def _date(node: etree._Element, path: str) -> str | None:
    raw = _text(node, path)
    if raw and len(raw) == 8 and raw.isdigit():  # format 102: YYYYMMDD
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:])).isoformat()
    return raw


def _amount(node: etree._Element, path: str) -> str | None:
    raw = _text(node, path)
    return str(Decimal(raw)) if raw else None


def _party(node: etree._Element | None) -> dict[str, Any] | None:
    if node is None:
        return None
    contact = _first(node, "ram:DefinedTradeContact")
    return {
        "name": _text(node, "ram:Name"),
        "address": {
            "street": _text(node, "ram:PostalTradeAddress/ram:LineOne"),
            "postcode": _text(node, "ram:PostalTradeAddress/ram:PostcodeCode"),
            "city": _text(node, "ram:PostalTradeAddress/ram:CityName"),
            "country_code": _text(node, "ram:PostalTradeAddress/ram:CountryID"),
        },
        "vat_id": _text(node, "ram:SpecifiedTaxRegistration/ram:ID[@schemeID='VA']"),
        "electronic_address": _text(node, "ram:URIUniversalCommunication/ram:URIID"),
        "contact": {
            "name": _text(contact, "ram:PersonName"),
            "phone": _text(contact, "ram:TelephoneUniversalCommunication/ram:CompleteNumber"),
            "email": _text(contact, "ram:EmailURIUniversalCommunication/ram:URIID"),
        }
        if contact is not None
        else None,
    }


def _line(node: etree._Element) -> dict[str, Any]:
    charge = _text(node, "ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:ChargeAmount")
    basis = _text(node, "ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:BasisQuantity")
    unit_price = None
    if charge:  # BT-146 is per BT-149 base quantity; the label stores price per single unit
        unit_price = str(Decimal(charge) / Decimal(basis)) if basis and Decimal(basis) != 0 else charge
    qty = _first(node, "ram:SpecifiedLineTradeDelivery/ram:BilledQuantity")
    return {
        "line_id": _text(node, "ram:AssociatedDocumentLineDocument/ram:LineID"),
        "description": _text(node, "ram:SpecifiedTradeProduct/ram:Name"),
        "seller_item_id": _text(node, "ram:SpecifiedTradeProduct/ram:SellerAssignedID"),
        "quantity": str(Decimal(qty.text)) if qty is not None and qty.text else None,
        "unit_code": qty.get("unitCode") if qty is not None else None,
        "unit_price": unit_price,
        "vat_rate": _amount(
            node, "ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax/ram:RateApplicablePercent"
        ),
        "vat_category": _text(
            node, "ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax/ram:CategoryCode"
        ),
        "net_amount": _amount(
            node,
            "ram:SpecifiedLineTradeSettlement/ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount",
        ),
    }


def cii_profile(xml: bytes) -> str | None:
    root = etree.fromstring(xml)
    return _text(root, "//rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID")


def cii_to_label(xml: bytes) -> dict[str, Any]:
    root = etree.fromstring(xml)
    trade = _first(root, "rsm:SupplyChainTradeTransaction")
    if trade is None:
        raise ValueError("not a CII invoice (no SupplyChainTradeTransaction)")
    agreement = _first(trade, "ram:ApplicableHeaderTradeAgreement")
    settlement = _first(trade, "ram:ApplicableHeaderTradeSettlement")
    if agreement is None or settlement is None:
        raise ValueError("CII invoice without header agreement or settlement")
    sums = _first(settlement, "ram:SpecifiedTradeSettlementHeaderMonetarySummation")
    currency = _text(settlement, "ram:InvoiceCurrencyCode")
    means = _first(settlement, "ram:SpecifiedTradeSettlementPaymentMeans")
    tax_total = None
    if sums is not None:  # BT-110 is the TaxTotalAmount in the invoice currency
        tax_total = _amount(sums, f"ram:TaxTotalAmount[@currencyID='{currency}']") or _amount(
            sums, "ram:TaxTotalAmount"
        )
    return {
        "number": _text(root, "rsm:ExchangedDocument/ram:ID"),
        "issue_date": _date(root, "rsm:ExchangedDocument/ram:IssueDateTime/udt:DateTimeString"),
        "type_code": _text(root, "rsm:ExchangedDocument/ram:TypeCode"),
        "currency": currency,
        "due_date": _date(
            settlement, "ram:SpecifiedTradePaymentTerms/ram:DueDateDateTime/udt:DateTimeString"
        ),
        "delivery_date": _date(
            trade,
            "ram:ApplicableHeaderTradeDelivery/ram:ActualDeliverySupplyChainEvent/ram:OccurrenceDateTime/udt:DateTimeString",
        ),
        "buyer_reference": _text(agreement, "ram:BuyerReference"),
        "seller": _party(_first(agreement, "ram:SellerTradeParty")),
        "buyer": _party(_first(agreement, "ram:BuyerTradeParty")),
        "lines": [_line(li) for li in _all(trade, "ram:IncludedSupplyChainTradeLineItem")],
        "iban": _text(means, "ram:PayeePartyCreditorFinancialAccount/ram:IBANID")
        if means is not None
        else None,
        "bic": _text(means, "ram:PayeeSpecifiedCreditorFinancialInstitution/ram:BICID")
        if means is not None
        else None,
        "payment_terms": _text(settlement, "ram:SpecifiedTradePaymentTerms/ram:Description"),
        "note": _text(root, "rsm:ExchangedDocument/ram:IncludedNote/ram:Content"),
        "totals": {
            "net_total": _amount(sums, "ram:LineTotalAmount") if sums is not None else None,
            "tax_total": tax_total,
            "gross_total": _amount(sums, "ram:GrandTotalAmount") if sums is not None else None,
            "due_amount": _amount(sums, "ram:DuePayableAmount") if sums is not None else None,
            "vat_breakdown": [
                {
                    "category": _text(t, "ram:CategoryCode"),
                    "rate": _amount(t, "ram:RateApplicablePercent"),
                    "basis": _amount(t, "ram:BasisAmount"),
                    "tax": _amount(t, "ram:CalculatedAmount"),
                }
                for t in _all(settlement, "ram:ApplicableTradeTax")
            ],
        },
    }
