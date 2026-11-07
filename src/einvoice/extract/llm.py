"""LLM extraction: document text -> Invoice (validated by the Pydantic model).

The model is chosen with EINVOICE_MODEL, a LiteLLM model string, e.g.
    groq/openai/gpt-oss-120b           (Groq free tier, development)
    gemini/gemini-2.0-flash            (Google AI Studio free tier)
    ollama/qwen2.5:7b                  (local, the privacy option)
Keys come from the environment or the gitignored .env file.

Responses are cached by (PDF sha256, model, prompt version), so re-running an
evaluation costs no tokens and a prompt change is a new cache key.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Protocol

from dotenv import load_dotenv
from pydantic import ValidationError

from einvoice.extract.text import DocumentText
from einvoice.model import Invoice

PROMPT_VERSION = "v2"
DEFAULT_MODEL = "groq/openai/gpt-oss-120b"
CACHE_DIR = Path(".cache/extract")

SYSTEM = """Du extrahierst Daten aus deutschen (oder englischen) Rechnungen in das vorgegebene JSON-Schema.
Antworte ausschließlich mit einem JSON-Objekt. Verwende genau die Feldnamen des Schemas.

Parteien
- seller.name und buyer.name: nur der Firmenname mit Rechtsform (z. B. "Sölzer Bau GmbH & Co. KG"). Keine Namen von Personen, keine Adresszeilen, keine Großschreibung ändern.
- Eine Ansprechperson (Frau/Herr, Kontakt, Ansprechpartner, Sachbearbeiter) gehört nach seller.contact.name, nie in seller.name.
- seller.vat_id und buyer.vat_id: nur die Nummer, z. B. "DE123456789". Stehen meist bei "USt-IdNr.", "USt-ID", "Steuer-ID" oder "VAT ID", oft in der Fußzeile. Ohne die Bezeichnung.

Nummern und Referenzen (nur der Wert, ohne Bezeichnung)
- number: Rechnungsnummer, z. B. bei "Rechnungsnummer", "Rechnungs-Nr.", "Rechnung Nr.", "Beleg-Nr.", "RECHNUNGS-NR.".
- buyer_reference: Bei "Leitweg-ID" nur die Kennung (z. B. "04011000-12345-34"). Bei "Ihre Bestellnummer", "Bestell-Nr.", "Ihre Referenz" nur die Nummer.

Datumsangaben
- Alle Daten als ISO-Datum JJJJ-MM-TT. Deutsche Formate wie 10.04.2026 umwandeln.
- issue_date: Rechnungsdatum, Datum, vom.
- delivery_date: Leistungsdatum, Lieferdatum, "Leistung erbracht am", "Lieferung am", "Ausführung", "Leistungszeitraum", "Service date". Wenn es nur einen Zeitraum gibt, das Enddatum nehmen. Null, wenn es fehlt.
- due_date: Fälligkeitsdatum, "Fällig am", "Zahlbar bis", "Fällig zum".

Positionen (lines)
- description: nur die Leistungsbezeichnung wie auf der Rechnung. Datumsangaben wie "(erbracht am 10.04.2026)" und Artikelnummern gehören NICHT in die Beschreibung.
- quantity, unit_price, net_amount: Zahlen, Punkt als Dezimaltrenner, ohne Währungszeichen. unit_price ist der Einzelpreis.
- seller_item_id: Artikelnummer / Art.-Nr. / SKU, sonst null.
- vat_rate: Zahl (19, 7, 0). vat_category: "S" bei Regelsatz, "Z" bei 0 %, "E" bei steuerfrei.
- unit_code: UN/ECE-Code: C62 Stück, HUR Stunden, DAY Tage, LS Pauschale, KGM kg, LTR Liter, MTR Meter, MTK Quadratmeter, MON Monat, SET Set, PR Paar.
- Jede Zeile der Rechnung ist eine Position, in Reihenfolge übernommen. Keine Summen oder Zwischensummen als Position.

Beträge
- Nettosummen und Steuerbeträge so übernehmen, wie sie auf der Rechnung stehen. Nichts selbst berechnen.
- iban und bic ohne Leerzeichen.

Allgemein
- Felder, die im Dokument nicht vorkommen, auf null setzen (bei Listen: []). Nichts erfinden.
- Rechnungstyp 380 für Handelsrechnungen.
"""


class Completer(Protocol):
    def __call__(self, model: str, messages: list[dict[str, str]]) -> str: ...


def configured_model() -> str:
    load_dotenv()
    return os.environ.get("EINVOICE_MODEL", DEFAULT_MODEL)


def _litellm_completer(model: str, messages: list[dict[str, str]]) -> str:
    import time

    import litellm  # imported lazily: slow to load and not needed for the cache or the scorer

    # Free tiers rate-limit hard (Groq: tokens per minute). Wait and retry instead of failing.
    bad_json = 0
    for attempt in range(12):
        try:
            resp = litellm.completion(
                model=model,
                messages=messages,
                temperature=0,
                response_format={"type": "json_object"},
            )
            time.sleep(float(os.environ.get("EINVOICE_PAUSE", "1.5")))
            return str(resp.choices[0].message.content)
        except litellm.exceptions.RateLimitError:
            time.sleep(min(90, 15 * (attempt + 1)))
        except litellm.exceptions.BadRequestError as exc:
            # Groq rejects output that is not valid JSON; sampling again usually works.
            bad_json += 1
            if bad_json > 2 or "json" not in str(exc).lower():
                raise
            time.sleep(2)
    raise ExtractionError(f"rate limited by {model} after 12 attempts")


def build_messages(text: DocumentText) -> list[dict[str, str]]:
    schema = json.dumps(Invoice.model_json_schema(), ensure_ascii=False)
    return [
        {"role": "system", "content": SYSTEM + "\nSchema:\n" + schema},
        {"role": "user", "content": "Rechnungstext:\n\n" + text.as_prompt()},
    ]


def cache_key(pdf_sha: str, model: str) -> Path:
    safe = model.replace("/", "_").replace(":", "_")
    return CACHE_DIR / f"{pdf_sha}-{safe}-{PROMPT_VERSION}.json"


class ExtractionError(RuntimeError):
    pass


def extract_invoice(
    pdf: Path,
    text: DocumentText,
    model: str | None = None,
    completer: Completer | None = None,
    cache: bool = True,
) -> Invoice:
    """Return the extracted invoice. Retries once with the validation error if the JSON is invalid."""
    model = model or configured_model()
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    path = cache_key(sha, model)
    if cache and path.exists():
        return Invoice.model_validate_json(path.read_text(encoding="utf-8"))

    call = completer or _litellm_completer
    messages = build_messages(text)
    last_error: str = ""
    for attempt in range(2):
        if attempt == 1:
            fix = {
                "role": "user",
                "content": f"Die Antwort war ungültig: {last_error}. Bitte korrigiere sie.",
            }
            messages = [*messages, fix]
        raw = call(model, messages)
        try:
            invoice = Invoice.model_validate(_loads(raw))
        except (ValidationError, ValueError) as exc:
            last_error = str(exc)[:1500]
            continue
        if cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(invoice.model_dump_json(indent=2), encoding="utf-8")
        return invoice
    raise ExtractionError(f"no valid invoice from {model} for {pdf.name}: {last_error[:300]}")


def _loads(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("response is not a JSON object")
    return data
