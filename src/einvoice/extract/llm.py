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

PROMPT_VERSION = "v1"
DEFAULT_MODEL = "groq/openai/gpt-oss-120b"
CACHE_DIR = Path(".cache/extract")

SYSTEM = """Du extrahierst Daten aus deutschen (oder englischen) Rechnungen.
Antworte ausschließlich mit einem JSON-Objekt, das dem Schema entspricht.
Regeln:
- Beträge und Mengen als Zahlen mit Punkt als Dezimaltrenner (z. B. 1234.56), ohne Währungszeichen.
- Datumsangaben als ISO-Datum JJJJ-MM-TT.
- VAT-Sätze als Zahl (19, 7, 0). Kategorie "S" bei Regelsatz, "Z" bei 0 %, "E" bei steuerfrei.
- Felder, die im Dokument nicht vorkommen, auf null setzen. Nichts erfinden.
- Zeilen so übernehmen, wie sie auf der Rechnung stehen; keine Summen selbst berechnen.
- unit_code: UN/ECE-Code (C62 für Stück, HUR für Stunden, LS für Pauschale, DAY für Tage, KGM, LTR, MTR, MON).
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
