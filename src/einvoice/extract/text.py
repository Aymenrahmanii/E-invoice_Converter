"""Digital PDF -> text plus word positions (pdfplumber).

Word boxes are kept so that each extracted value can later point back to where it
was read (the review screen in week 5). A scanned PDF has no text layer: `has_text`
is False and the caller must route it to OCR (not built yet).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber


@dataclass(frozen=True)
class Word:
    page: int
    text: str
    x0: float
    top: float
    x1: float
    bottom: float


@dataclass
class DocumentText:
    pages: list[str] = field(default_factory=list)
    words: list[Word] = field(default_factory=list)

    @property
    def has_text(self) -> bool:
        return any(p.strip() for p in self.pages)

    def as_prompt(self) -> str:
        return "\n\n".join(f"--- Seite {i} ---\n{text}" for i, text in enumerate(self.pages, start=1))


def read_pdf_text(path: Path) -> DocumentText:
    doc = DocumentText()
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            doc.pages.append(page.extract_text(layout=True) or "")
            for w in page.extract_words(keep_blank_chars=False):
                doc.words.append(
                    Word(
                        page_no,
                        w["text"],
                        float(w["x0"]),
                        float(w["top"]),
                        float(w["x1"]),
                        float(w["bottom"]),
                    )
                )
    return doc
