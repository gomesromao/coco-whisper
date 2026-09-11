#!/bin/bash
# Pulls a few Tagalog utterances with reference transcripts for accuracy testing.
OUT="$TEMP/fleurs.json"
for i in $(seq 1 20); do
  curl -s "https://datasets-server.huggingface.co/rows?dataset=google%2Ffleurs&config=tl_ph&split=test&offset=0&length=8" -o "$OUT"
  if grep -q '"rows"' "$OUT" 2>/dev/null; then echo "sucesso na tentativa $i"; exit 0; fi
  ping -n 31 127.0.0.1 >/dev/null 2>&1
done
echo "falhou apos 20 tentativas"; exit 1
