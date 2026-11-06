"""Scorer and extraction logic, tested without any network call (fake model)."""

import json
from pathlib import Path

import pytest

from einvoice.evaluate import Score
from einvoice.extract import llm
from einvoice.extract.text import DocumentText
from einvoice.samples import craftsman_invoice


def _pdf(tmp_path: Path) -> Path:
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake bytes for hashing")
    return pdf


def test_perfect_prediction_scores_100() -> None:
    inv = craftsman_invoice()
    score = Score()
    score.add("doc", inv, inv.model_copy(deep=True))
    assert score.failures == []
    assert all(score.fields_correct[f] == score.fields_total[f] for f in score.fields_total)
    assert score.lines_correct == score.lines_total == len(inv.lines)


def test_iban_spacing_and_whitespace_are_normalised() -> None:
    inv = craftsman_invoice()
    pred = inv.model_copy(update={"iban": "DE89 3704 0044 0532 0130 00"})
    pred.seller.name = "  Malerbetrieb   Muster GmbH "
    score = Score()
    score.add("doc", inv, pred)
    assert score.failures == []


def test_wrong_total_and_missing_line_are_reported() -> None:
    inv = craftsman_invoice()
    pred = inv.model_copy(deep=True)
    pred.lines = pred.lines[:-1]  # drop the last line: totals and the line both change
    score = Score()
    score.add("doc", inv, pred)
    reasons = " | ".join(str(r) for r in score.failures[0]["reason"])
    assert "net_total" in reasons
    assert "not found" in reasons
    assert score.fields_correct["iban"] == 1  # other fields still count


def test_failed_extraction_counts_every_field_wrong() -> None:
    inv = craftsman_invoice()
    score = Score()
    score.add("doc", inv, None)
    assert sum(score.fields_correct.values()) == 0
    assert score.lines_correct == 0 and score.lines_total == len(inv.lines)


def test_retry_after_invalid_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path / "cache")
    good = craftsman_invoice()
    replies = iter(["not json at all", json.dumps({"number": "X"})])
    seen: list[list[dict[str, str]]] = []

    def fake(model: str, messages: list[dict[str, str]]) -> str:
        seen.append(messages)
        return next(replies)

    with pytest.raises(llm.ExtractionError):
        llm.extract_invoice(
            _pdf(tmp_path), DocumentText(pages=["x"]), model="fake/m", completer=fake, cache=False
        )
    assert len(seen) == 2  # one retry, with the error message appended
    assert "ungültig" in seen[1][-1]["content"]

    replies = iter([good.model_dump_json()])
    inv = llm.extract_invoice(_pdf(tmp_path), DocumentText(pages=["x"]), model="fake/m", completer=fake)
    assert inv == good


def test_cache_avoids_second_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path / "cache")
    calls = {"n": 0}
    good = craftsman_invoice()

    def fake(model: str, messages: list[dict[str, str]]) -> str:
        calls["n"] += 1
        return good.model_dump_json()

    pdf = _pdf(tmp_path)
    text = DocumentText(pages=["x"])
    first = llm.extract_invoice(pdf, text, model="fake/m", completer=fake)
    second = llm.extract_invoice(pdf, text, model="fake/m", completer=fake)
    assert first == second == good
    assert calls["n"] == 1
