#!/bin/bash
# Packs the app, a shortcut to Applications and the English instructions into
# one disk image, so the download already shows where the app has to go.
set -euo pipefail

APP="$1"
OUT="$2"
HERE="$(cd "$(dirname "$0")" && pwd)"

STAGE="$RUNNER_TEMP/coco-dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE"
ditto "$APP" "$STAGE/$(basename "$APP")"
ln -s /Applications "$STAGE/Applications"
cp "$HERE/READ ME FIRST.txt" "$STAGE/READ ME FIRST.txt"

# hdiutil on the hosted runners fails now and then with "Resource busy"
for attempt in 1 2 3 4 5; do
  if hdiutil create -volname "Coco Whisper" -srcfolder "$STAGE" -fs HFS+ \
      -format UDZO -ov "$OUT"; then
    ls -lh "$OUT"
    exit 0
  fi
  echo "hdiutil failed, attempt $attempt, trying again"
  sleep 5
done
exit 1
