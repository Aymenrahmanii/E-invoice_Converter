import io
from decimal import Decimal

from lxml import etree
from pypdf import PdfReader

from einvoice.export.cii import GUIDELINE_IDS, to_cii_xml
from einvoice.export.zugferd import to_zugferd_pdf
from einvoice.samples import craftsman_invoice

NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
}


def _xpath(xml: bytes, path: str) -> str:
    return str(etree.fromstring(xml).xpath(f"string({path})", namespaces=NS))


def test_xrechnung_header_and_totals() -> None:
    xml = to_cii_xml(craftsman_invoice(), profile="xrechnung")
    assert (
        _xpath(xml, "//ram:GuidelineSpecifiedDocumentContextParameter/ram:ID") == GUIDELINE_IDS["xrechnung"]
    )
    assert _xpath(xml, "//rsm:ExchangedDocument/ram:ID") == "RE-2026-0001"
    assert _xpath(xml, "//ram:BuyerReference") == "04011000-12345-34"
    assert Decimal(_xpath(xml, "//ram:GrandTotalAmount")) == Decimal("1126.97")
    assert _xpath(xml, "//ram:IBANID") == "DE89370400440532013000"


def test_zugferd_embeds_factur_x_xml() -> None:
    pdf = to_zugferd_pdf(craftsman_invoice())
    reader = PdfReader(io.BytesIO(pdf))
    assert "factur-x.xml" in reader.attachments
    xml = reader.attachments["factur-x.xml"][0]
    assert _xpath(xml, "//ram:GuidelineSpecifiedDocumentContextParameter/ram:ID") == GUIDELINE_IDS["en16931"]
    assert "/OutputIntents" in reader.root_object
