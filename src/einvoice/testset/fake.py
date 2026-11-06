"""Random but realistic invoice data, seeded so every invoice is reproducible on its own.

Each invoice uses `random.Random(seed)` and a Faker seeded with the same value, so
invoice 17 is the same whether 20 or 300 invoices are generated. The data is plain
Python (no rendering), which lets tests regenerate labels and check they did not drift.
"""

from __future__ import annotations

import random
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from faker import Faker
from stdnum.iso7064 import mod_11_10, mod_97_10

from einvoice.model import Address, Contact, Invoice, LineItem, Party

Business = Literal["craftsman", "agency", "wholesaler", "freelancer", "grocer"]
Language = Literal["de", "en"]


@dataclass(frozen=True)
class Article:
    description: str
    unit_code: str
    price_range: tuple[float, float]
    vat_rate: int = 19
    quantity_step: str = "1"  # Decimal step; "0.5" for hours, "0.001" for kg
    quantity_max: int = 10


CATALOG: dict[Business, list[Article]] = {
    "craftsman": [
        Article("Arbeitszeit Geselle", "HUR", (48, 62), quantity_step="0.5", quantity_max=40),
        Article("Arbeitszeit Meister", "HUR", (62, 78), quantity_step="0.5", quantity_max=16),
        Article("Arbeitszeit Auszubildender", "HUR", (28, 36), quantity_step="0.5", quantity_max=24),
        Article("Anfahrtspauschale", "LS", (25, 65), quantity_max=3),
        Article("Wandfarbe weiß, 10 l Eimer", "C62", (39, 69), quantity_max=12),
        Article("Tiefengrund LF, 5 l", "C62", (18, 32), quantity_max=6),
        Article("Abdeckfolie 4 x 5 m", "C62", (3, 8), quantity_max=20),
        Article("Malerkrepp 50 mm", "C62", (4, 9), quantity_max=15),
        Article("Raufaser Tapete Körnung mittel", "C62", (6, 14), quantity_max=30),
        Article("Fliesenkleber flexibel, 25 kg", "C62", (19, 34), quantity_max=10),
        Article("Silikon sanitär, transparent", "C62", (7, 13), quantity_max=8),
        Article("Kupferrohr 15 mm", "MTR", (9, 16), quantity_step="0.5", quantity_max=40),
        Article("Verlegung Laminat", "MTK", (14, 28), quantity_step="0.5", quantity_max=80),
        Article("Entsorgung Bauschutt", "LS", (45, 180), quantity_max=2),
        Article("Gerüststellung pro Tag", "DAY", (55, 120), quantity_max=10),
    ],
    "agency": [
        Article("Konzeption und Strategie-Workshop", "DAY", (900, 1600), quantity_step="0.5", quantity_max=4),
        Article("UX-Design Startseite", "HUR", (85, 130), quantity_step="0.5", quantity_max=40),
        Article("Frontend-Entwicklung", "HUR", (80, 125), quantity_step="0.5", quantity_max=80),
        Article("Backend-Entwicklung", "HUR", (85, 135), quantity_step="0.5", quantity_max=60),
        Article("Projektmanagement", "HUR", (75, 110), quantity_step="0.5", quantity_max=20),
        Article("Texterstellung Produktseiten", "C62", (60, 180), quantity_max=12),
        Article("Fotoshooting inkl. Bildbearbeitung", "DAY", (800, 1500), quantity_max=2),
        Article("Hosting und Wartung", "MON", (49, 199), quantity_max=12),
        Article("Social-Media-Betreuung", "MON", (450, 1200), quantity_max=3),
        Article("SEO-Analyse", "LS", (400, 1200), quantity_max=1),
        Article("Logo-Entwicklung inkl. 3 Entwürfe", "LS", (900, 2500), quantity_max=1),
    ],
    "wholesaler": [
        Article("Schraube Senkkopf 4 x 40 mm, 500 Stk.", "C62", (9, 15), quantity_max=40),
        Article("Dübel Nylon 8 mm, 100 Stk.", "C62", (4, 8), quantity_max=60),
        Article("Kabel NYM-J 3x1,5 mm²", "MTR", (0.6, 1.4), quantity_step="1", quantity_max=500),
        Article("Steckdose Unterputz weiß", "C62", (2.5, 6), quantity_max=100),
        Article("Arbeitshandschuhe Gr. 10", "PR", (2, 5), quantity_max=80),
        Article("Baustahlmatte Q188", "C62", (38, 62), quantity_max=30),
        Article("Zement CEM II 25 kg", "C62", (5, 9), quantity_max=120),
        Article("Quarzsand gewaschen", "KGM", (0.15, 0.4), quantity_step="0.5", quantity_max=2000),
        Article("Hydrauliköl HLP 46", "LTR", (2.2, 4.5), quantity_max=200),
        Article("Kanthölzer KVH 60 x 80 mm", "MTR", (3.5, 7), quantity_max=200),
        Article("Werkzeugkoffer Set 108-tlg.", "SET", (49, 129), quantity_max=10),
        Article("LED-Panel 62 x 62 cm", "C62", (24, 49), quantity_max=50),
        Article("Isolierband schwarz 19 mm", "C62", (0.9, 2.2), quantity_max=200),
        Article("Silikonspray 400 ml", "C62", (4, 8), quantity_max=48),
        Article("Wasserwaage Alu 80 cm", "C62", (12, 29), quantity_max=20),
        Article("Akku-Bohrschrauber 18 V", "C62", (89, 189), quantity_max=8),
        Article("Gipskartonplatte 12,5 mm", "MTK", (2.5, 4.8), quantity_step="0.5", quantity_max=400),
        Article("Fugenspachtel 5 kg", "C62", (9, 16), quantity_max=40),
    ],
    "freelancer": [
        Article("Beratungsleistung", "HUR", (70, 150), quantity_step="0.5", quantity_max=60),
        Article("Softwareentwicklung", "HUR", (75, 140), quantity_step="0.5", quantity_max=160),
        Article("Übersetzung Deutsch-Englisch", "C62", (0.12, 0.2), quantity_max=12000),
        Article("Lektorat", "HUR", (45, 75), quantity_step="0.5", quantity_max=30),
        Article("Schulung vor Ort", "DAY", (900, 1800), quantity_step="0.5", quantity_max=5),
        Article("Pauschale Projektabschluss", "LS", (300, 2500), quantity_max=1),
    ],
    "grocer": [
        Article("Kaffee Bohnen 1 kg", "C62", (12, 24), vat_rate=7, quantity_max=20),
        Article("Mineralwasser 12 x 1 l", "C62", (4, 8), vat_rate=19, quantity_max=40),
        Article("Apfelsaft naturtrüb 6 x 1 l", "C62", (7, 13), vat_rate=19, quantity_max=20),
        Article("Butterbrezeln", "C62", (0.6, 1.2), vat_rate=7, quantity_max=200),
        Article("Obstkorb gemischt", "C62", (15, 35), vat_rate=7, quantity_max=10),
        Article("Milch 3,5 % 1 l", "LTR", (0.9, 1.6), vat_rate=7, quantity_max=60),
        Article("Fachbuch Buchhaltung", "C62", (24, 59), vat_rate=7, quantity_max=5),
        Article("Tageszeitung Abo", "MON", (35, 65), vat_rate=7, quantity_max=12),
        Article("Reinigungsmittel 5 l", "C62", (9, 19), vat_rate=19, quantity_max=12),
        Article("Papierhandtücher Karton", "C62", (19, 39), vat_rate=19, quantity_max=10),
        Article("Catering Buffet pro Person", "C62", (18, 35), vat_rate=19, quantity_max=80),
        Article("Kuchenplatte", "C62", (25, 45), vat_rate=7, quantity_max=6),
    ],
}

PAYMENT_TERMS: dict[Language, list[str]] = {
    "de": [
        "Zahlbar innerhalb von {days} Tagen ohne Abzug.",
        "Zahlungsziel: {days} Tage netto.",
        "Bitte überweisen Sie den Betrag innerhalb von {days} Tagen.",
        "Zahlbar bis zum Fälligkeitsdatum ohne Abzug.",
    ],
    "en": [
        "Payment due within {days} days.",
        "Net {days} days.",
        "Please transfer the amount within {days} days of the invoice date.",
    ],
}

LEGAL_FORMS = ["GmbH", "GmbH & Co. KG", "AG", "e.K.", "UG (haftungsbeschränkt)", "KG", "OHG"]


def german_vat_id(rng: random.Random) -> str:
    body = str(rng.randint(10_000_000, 99_999_999))
    return f"DE{body}{mod_11_10.calc_check_digit(body)}"


def german_iban(rng: random.Random) -> str:
    bban = f"{rng.randint(10_000_000, 89_999_999)}{rng.randint(0, 9_999_999_999):010d}"
    check = mod_97_10.calc_check_digits(bban + "DE")
    return f"DE{check}{bban}"


def bic(rng: random.Random) -> str:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    bank = "".join(rng.choice(letters) for _ in range(4))
    loc = rng.choice(letters) + rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ0123456789")
    return f"{bank}DE{loc}" + rng.choice(["", "XXX"])


def leitweg_id(rng: random.Random) -> str:
    """Leitweg-ID: coarse-fine-check; check digits are ISO 7064 Mod 97-10 over the rest."""
    coarse = f"{rng.randint(1, 16):02d}{rng.randint(0, 999999):06d}"[: rng.choice([2, 5, 8])]
    fine = str(rng.randint(1000, 99999))
    return f"{coarse}-{fine}-{mod_97_10.calc_check_digits(coarse + fine)}"


def _slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:30] or "firma"


def _company(fake: Faker, rng: random.Random) -> str:
    name = fake.last_name()
    kind = rng.choice(
        ["{n}", "{n} & {m}", "{n} Handel", "{n} Service", "{n} Bau", "{n} Digital", "{n} Technik"]
    )
    return f"{kind.format(n=name, m=fake.last_name())} {rng.choice(LEGAL_FORMS)}"


def _party(fake: Faker, rng: random.Random, name: str, with_contact: bool, with_vat: bool) -> Party:
    domain = f"{_slug(name.split(' ')[0])}.example"
    return Party(
        name=name,
        address=Address(street=fake.street_address(), postcode=fake.postcode(), city=fake.city()),
        vat_id=german_vat_id(rng) if with_vat else None,
        electronic_address=f"{rng.choice(['rechnung', 'buchhaltung', 'invoice', 'info'])}@{domain}",
        contact=Contact(
            name=fake.name(), phone=fake.phone_number(), email=f"{_slug(fake.first_name())}@{domain}"
        )
        if with_contact
        else None,
    )


def _quantity(rng: random.Random, art: Article) -> Decimal:
    step = Decimal(art.quantity_step)
    max_steps = int(Decimal(art.quantity_max) / step)
    return (step * rng.randint(1, max(1, max_steps))).normalize() + Decimal("0")


def _invoice_number(rng: random.Random, issue: date) -> str:
    n = rng.randint(1, 9999)
    return rng.choice(
        [
            f"RE-{issue.year}-{n:04d}",
            f"{issue.year}/{n:04d}",
            f"R{issue.year % 100}-{n:05d}",
            f"INV-{rng.randint(10000, 99999)}",
            f"{issue.year}{issue.month:02d}-{n:03d}",
            str(rng.randint(100000, 999999)),
        ]
    )


def random_invoice(
    seed: int,
    business: Business,
    lines: tuple[int, int] = (1, 8),
    language: Language = "de",
    mixed_vat: bool = False,
) -> Invoice:
    rng = random.Random(seed)
    fake = Faker("de_DE")
    fake.seed_instance(seed)

    issue = date(2026, 1, 1) + timedelta(days=rng.randint(0, 303))
    days = rng.choice([7, 10, 14, 14, 30, 30])
    catalog = CATALOG[business]
    if mixed_vat:  # make sure both rates appear
        pool = [a for a in catalog if a.vat_rate == 7], [a for a in catalog if a.vat_rate == 19]
        picks = [rng.choice(pool[0]), rng.choice(pool[1])]
    else:
        picks = []
    n_lines = rng.randint(*lines)
    rest = [a for a in catalog if a not in picks]
    rng.shuffle(rest)
    picks += rest[: max(0, n_lines - len(picks))]
    while len(picks) < n_lines:  # long invoices repeat articles (e.g. several deliveries)
        picks.append(rng.choice(catalog))
    rng.shuffle(picks)

    with_item_ids = business == "wholesaler" or rng.random() < 0.2
    items = [
        LineItem(
            line_id=str(i),
            description=art.description,
            seller_item_id=f"{rng.choice(['A', 'ART', '', 'SKU-'])}{rng.randint(1000, 999999)}"
            if with_item_ids
            else None,
            quantity=_quantity(rng, art),
            unit_code=art.unit_code,
            unit_price=Decimal(str(round(rng.uniform(*art.price_range), 2))).quantize(Decimal("0.01")),
            vat_rate=Decimal(art.vat_rate),
        )
        for i, art in enumerate(picks, start=1)
    ]

    terms = rng.choice(PAYMENT_TERMS[language]).format(days=days)
    return Invoice(
        number=_invoice_number(rng, issue),
        issue_date=issue,
        due_date=issue + timedelta(days=days) if rng.random() < 0.8 else None,
        delivery_date=issue - timedelta(days=rng.randint(0, 14)) if rng.random() < 0.85 else None,
        buyer_reference=leitweg_id(rng) if rng.random() < 0.3 else str(rng.randint(4500000000, 4599999999)),
        seller=_party(fake, rng, _company(fake, rng), with_contact=True, with_vat=True),
        buyer=_party(fake, rng, _company(fake, rng), with_contact=False, with_vat=rng.random() < 0.6),
        lines=items,
        iban=german_iban(rng),
        bic=bic(rng) if rng.random() < 0.85 else None,
        payment_terms=terms,
    )
