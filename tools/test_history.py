"""Checks that only the newest entries keep their text."""
import json, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, ".")
from app.main import HISTORY_MAX_ENTRIES, HISTORY_TEXT_ENTRIES, trim_history

tmp = Path(tempfile.mkdtemp()) / "history.jsonl"
with tmp.open("w", encoding="utf-8") as fh:
    for i in range(60):
        fh.write(json.dumps({"at": f"entry-{i}", "chars": i, "text": f"secret {i}"}) + "\n")

trim_history(tmp)
rows = [json.loads(l) for l in tmp.read_text(encoding="utf-8").splitlines() if l.strip()]
with_text = [r for r in rows if "text" in r]
print(f"linhas guardadas: {len(rows)} (esperado 60)")
print(f"com texto: {len(with_text)} (esperado {HISTORY_TEXT_ENTRIES})")
print(f"as com texto sao as ultimas: {[r['at'] for r in with_text[:2]]} ... {with_text[-1]['at']}")
assert len(rows) == 60
assert len(with_text) == HISTORY_TEXT_ENTRIES
assert with_text[-1]["at"] == "entry-59"
assert all("text" not in r for r in rows[:40])

# now the cap
with tmp.open("w", encoding="utf-8") as fh:
    for i in range(HISTORY_MAX_ENTRIES + 120):
        fh.write(json.dumps({"at": f"e{i}", "text": "x"}) + "\n")
trim_history(tmp)
rows = [json.loads(l) for l in tmp.read_text(encoding="utf-8").splitlines() if l.strip()]
print(f"apos o teto: {len(rows)} linhas (teto {HISTORY_MAX_ENTRIES}), mais antiga = {rows[0]['at']}")
assert len(rows) == HISTORY_MAX_ENTRIES
print("\nPASSOU")
