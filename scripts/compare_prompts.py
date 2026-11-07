"""Compare two prompt versions on the documents both extracted (cached results only, no API calls).

uv run python scripts/compare_prompts.py v1 v2
"""

import hashlib
import json
import sys
from pathlib import Path

from einvoice.evaluate import Score
from einvoice.extract.llm import cache_key
from einvoice.model import Invoice

DATA = Path("data/generated")


def cached(pdf: Path, model: str, version: str) -> Invoice | None:
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    path = cache_key(sha, model)
    path = path.with_name(path.name.replace("-v2.json", f"-{version}.json"))
    return Invoice.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None


def main(a: str, b: str, model: str = "groq/openai/gpt-oss-120b") -> None:
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    docs = [d for d in manifest["documents"] if d["split"] == "dev" and d["variant"] == "digital"]
    common = []
    for d in docs:
        label = Invoice.model_validate_json((DATA / d["label"]).read_text(encoding="utf-8"))
        pa, pb = cached(DATA / d["pdf"], model, a), cached(DATA / d["pdf"], model, b)
        if pa and pb:
            common.append((d["id"], label, pa, pb))
    print(f"documents extracted by both {a} and {b}: {len(common)}")
    for version, idx in ((a, 2), (b, 3)):
        score = Score()
        for row in common:
            score.add(row[0], row[1], row[idx])
        print(f"\n== {version}")
        print("\n".join(line for line in score.report().splitlines() if " of " in line))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
