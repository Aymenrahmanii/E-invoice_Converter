"""Invoice model -> ZUGFeRD 2.3 EN 16931: a PDF/A-3 with the CII XML embedded.

PDF/A-3 needs every font embedded and a colour OutputIntent. The visual page is
drawn with reportlab using its bundled (embeddable) Vera fonts, an sRGB
OutputIntent is added, and drafthorse attaches factur-x.xml with the XMP metadata.
"""

from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path

import reportlab
from drafthorse.pdf import attach_xml
from PIL import ImageCms
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from einvoice.export.cii import to_cii_xml
from einvoice.model import Invoice

_FONT_DIR = Path(reportlab.__file__).parent / "fonts"
FONT, FONT_BOLD = "Vera", "VeraBd"


def _register_fonts() -> None:
    if FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT, str(_FONT_DIR / "Vera.ttf")))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(_FONT_DIR / "VeraBd.ttf")))


def _eur(value: Decimal) -> str:
    """German number format: 1.234,56 €"""
    s = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} €"


def _de_num(value: Decimal) -> str:
    return f"{value.normalize():f}".replace(".", ",")


def render_invoice_pdf(invoice: Invoice) -> bytes:
    """Draw a plain one-page invoice. Week 1 only needs a valid visual; layouts come in week 2."""
    _register_fonts()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=True)
    c.setTitle(f"Rechnung {invoice.number}")
    c.setAuthor(invoice.seller.name)
    width, height = A4
    left, right = 20 * mm, width - 20 * mm
    y = height - 25 * mm

    s, b = invoice.seller, invoice.buyer
    c.setFont(FONT_BOLD, 14)
    c.drawString(left, y, s.name)
    c.setFont(FONT, 9)
    c.drawString(left, y - 5 * mm, f"{s.address.street} · {s.address.postcode} {s.address.city}")
    if s.vat_id:
        c.drawString(left, y - 9 * mm, f"USt-IdNr.: {s.vat_id}")

    y -= 25 * mm
    c.setFont(FONT, 10)
    for i, text in enumerate([b.name, b.address.street, f"{b.address.postcode} {b.address.city}"]):
        c.drawString(left, y - i * 5 * mm, text)
    meta = [
        ("Rechnungsnummer", invoice.number),
        ("Rechnungsdatum", invoice.issue_date.strftime("%d.%m.%Y")),
        ("Leistungsdatum", invoice.delivery_date.strftime("%d.%m.%Y") if invoice.delivery_date else "-"),
        ("Fällig am", invoice.due_date.strftime("%d.%m.%Y") if invoice.due_date else "-"),
        ("Ihre Referenz", invoice.buyer_reference),
    ]
    for i, (label, value) in enumerate(meta):
        c.drawString(right - 75 * mm, y - i * 5 * mm, label)
        c.drawRightString(right, y - i * 5 * mm, value)

    y -= 35 * mm
    c.setFont(FONT_BOLD, 13)
    c.drawString(left, y, f"Rechnung {invoice.number}")

    y -= 10 * mm
    cols = [left, left + 10 * mm, right - 80 * mm, right - 60 * mm, right - 25 * mm, right]
    c.setFont(FONT_BOLD, 9)
    c.drawString(cols[0], y, "Pos.")
    c.drawString(cols[1], y, "Beschreibung")
    c.drawRightString(cols[3], y, "Menge")
    c.drawRightString(cols[4] - 12 * mm, y, "Einzelpreis")
    c.drawRightString(cols[4], y, "USt.")
    c.drawRightString(cols[5], y, "Betrag")
    c.line(left, y - 2 * mm, right, y - 2 * mm)
    c.setFont(FONT, 9)
    for line in invoice.lines:
        y -= 7 * mm
        c.drawString(cols[0], y, line.line_id)
        c.drawString(cols[1], y, line.description)
        c.drawRightString(cols[3], y, f"{_de_num(line.quantity)} {line.unit_code}")
        c.drawRightString(cols[4] - 12 * mm, y, _eur(line.unit_price))
        c.drawRightString(cols[4], y, f"{_de_num(line.vat_rate)} %")
        c.drawRightString(cols[5], y, _eur(line.net_amount))
    c.line(left, y - 3 * mm, right, y - 3 * mm)

    y -= 10 * mm
    totals: list[tuple[str, Decimal]] = [("Nettobetrag", invoice.net_total)]
    totals += [(f"USt. {_de_num(v.rate)} % auf {_eur(v.basis)}", v.tax) for v in invoice.vat_breakdown()]
    for label, amount in totals:
        c.drawString(right - 80 * mm, y, label)
        c.drawRightString(right, y, _eur(amount))
        y -= 5 * mm
    c.setFont(FONT_BOLD, 10)
    c.drawString(right - 80 * mm, y, "Rechnungsbetrag")
    c.drawRightString(right, y, _eur(invoice.gross_total))

    y -= 15 * mm
    c.setFont(FONT, 9)
    if invoice.payment_terms:
        c.drawString(left, y, invoice.payment_terms)
        y -= 5 * mm
    c.drawString(left, y, f"IBAN: {invoice.iban}" + (f"   BIC: {invoice.bic}" if invoice.bic else ""))

    c.showPage()
    c.save()
    return buf.getvalue()


def _add_srgb_output_intent(pdf: bytes) -> bytes:
    """PDF/A requires an OutputIntent when DeviceRGB is used; embed a generated sRGB profile."""
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf)))
    profile = DecodedStreamObject()
    profile.set_data(icc)
    profile.update({NameObject("/N"): NumberObject(3)})
    intent = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/OutputIntent"),
            NameObject("/S"): NameObject("/GTS_PDFA1"),
            NameObject("/OutputConditionIdentifier"): TextStringObject("sRGB"),
            NameObject("/Info"): TextStringObject("sRGB IEC61966-2.1"),
            NameObject("/DestOutputProfile"): writer._add_object(profile),
        }
    )
    writer._root_object[NameObject("/OutputIntents")] = ArrayObject([writer._add_object(intent)])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def to_zugferd_pdf(invoice: Invoice, visual_pdf: bytes | None = None) -> bytes:
    """Embed EN 16931 CII XML into a PDF/A-3. `visual_pdf` defaults to a rendered page."""
    xml = to_cii_xml(invoice, profile="en16931")
    base = _add_srgb_output_intent(visual_pdf or render_invoice_pdf(invoice))
    return bytes(attach_xml(base, xml, level="EN 16931", lang="de-DE"))
