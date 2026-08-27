"""M2 acceptance: run live classify/extract over prompts/extract_examples.jsonl.
Reports field accuracy and name-resolution safety. Requires OPENAI_API_KEY / OPENAI_MODEL in .env.
usage: python scripts/eval_extract.py [--limit N]
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.change.name_resolver import Staff, resolve  # noqa: E402
from agent.llm.client import LLM  # noqa: E402

EX = Path(__file__).resolve().parents[1] / "prompts" / "extract_examples.jsonl"
STAFF = [Staff("N001", "สมศรี ใจดี", ("ศรี", "พี่ศรี")), Staff("N002", "บุษบา แสงทอง", ("บี", "น้องบี")),
         Staff("N003", "กมล รักงาน", ("กมล",)), Staff("N004", "ศรีวรรณ ดีงาม", ("อ้อ",))]
SWAP_FIELDS = ["swap_type", "a_name", "a_day", "a_month", "a_shift", "b_name", "b_day", "b_month", "b_shift"]
EDIT_FIELDS = ["target_name", "day", "month", "new_shift"]


def main(limit: int | None = None) -> int:
    llm = LLM()
    rows = [json.loads(l) for l in EX.read_text(encoding="utf-8").splitlines() if l.strip()][:limit]
    ok_fields = tot_fields = 0
    intent_ok = intent_tot = 0
    wrong_names = 0
    failures: list[str] = []
    for ex in rows:
        text, exp = ex["text"], ex["expected"]
        today = date.fromisoformat(ex.get("today", "2026-10-01"))
        try:
            if ex["kind"] == "classify":
                got = llm.classify(text)
                intent_tot += 1
                if got.intent == exp["intent"]:
                    intent_ok += 1
                else:
                    failures.append(f"[classify] {text!r}: got {got.intent} ({got.confidence:.2f}) want {exp['intent']}")
                continue
            got = (llm.extract_swap if ex["kind"] == "swap" else llm.extract_edit)(text, ["2569-10", "2569-11"], today)
            g = got.model_dump()
            fields = SWAP_FIELDS if ex["kind"] == "swap" else EDIT_FIELDS
            for f in fields:
                tot_fields += 1
                want = exp.get(f)
                # names: compare by resolution (nickname/prefix variants are fine)
                if f.endswith("name") and want and g.get(f):
                    rw, rg = resolve(want, STAFF), resolve(g[f], STAFF)
                    if rw.ok and rg.ok and rw.staff != rg.staff:
                        wrong_names += 1
                        failures.append(f"[{ex['kind']}] {text!r}: {f} resolved to wrong person {g[f]!r}")
                        continue
                    if (rw.ok and rg.ok) or rw.matches == rg.matches:
                        ok_fields += 1
                        continue
                if g.get(f) == want:
                    ok_fields += 1
                else:
                    failures.append(f"[{ex['kind']}] {text!r}: {f}={g.get(f)!r} want {want!r}")
            # missing must cover the None-required fields
            for f in exp.get("missing", []):
                if f not in got.missing and f != "month_ambiguous":
                    failures.append(f"[{ex['kind']}] {text!r}: missing lacks {f} (got {got.missing})")
        except Exception as e:  # noqa: BLE001
            failures.append(f"[{ex['kind']}] {text!r}: ERROR {type(e).__name__}: {e}")
            if ex["kind"] == "classify":
                intent_tot += 1
            else:
                tot_fields += len(SWAP_FIELDS if ex["kind"] == "swap" else EDIT_FIELDS)
    acc = ok_fields / tot_fields if tot_fields else 0
    print(f"fields: {ok_fields}/{tot_fields} = {acc:.1%}   intents: {intent_ok}/{intent_tot}   wrong-name: {wrong_names}")
    for f in failures:
        print(" -", f)
    return 0 if acc >= 0.9 and wrong_names == 0 else 1


if __name__ == "__main__":
    lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    sys.exit(main(lim))
