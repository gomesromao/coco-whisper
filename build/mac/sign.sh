#!/bin/bash
# Signs the bundle with the team certificate, the same one on every build.
#
# Ad hoc signing gave each version a new identity, so macOS treated every
# update as a stranger: the Accessibility switch from the previous version
# stayed on in System Settings while the new one was refused. With a fixed
# certificate the designated requirement names the certificate instead of the
# hash of this build, and the switch survives updates.
#
# The certificate is self signed. That is enough for the permission to stick,
# not for Gatekeeper, which still asks once per download (Open Anyway).
set -euo pipefail

APP="$1"

if [ -z "${MAC_SIGNING_P12:-}" ]; then
  if [[ "${GITHUB_REF:-}" == refs/tags/* ]]; then
    echo "::error::MAC_SIGNING_P12 is not set. A release signed ad hoc brings back the permission that resets on every update."
    exit 1
  fi
  echo "no signing certificate here, signing ad hoc"
  codesign --force --deep --sign - "$APP"
  exit 0
fi

KC="$RUNNER_TEMP/coco-signing.keychain-db"
KC_PASS="$(openssl rand -hex 16)"
P12="$RUNNER_TEMP/coco-signing.p12"

security create-keychain -p "$KC_PASS" "$KC"
security set-keychain-settings -lut 21600 "$KC"
security unlock-keychain -p "$KC_PASS" "$KC"
printf '%s' "$MAC_SIGNING_P12" | base64 --decode > "$P12"
security import "$P12" -k "$KC" -P "$MAC_SIGNING_PASSWORD" -T /usr/bin/codesign
rm -f "$P12"
# without this codesign stops at a password prompt nobody can answer
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KC_PASS" "$KC" >/dev/null
security list-keychains -d user -s "$KC" $(security list-keychains -d user | tr -d '"')

# Not trusted by anything, so -v would hide it. The hash picks it anyway.
HASH="$(security find-identity -p codesigning "$KC" | awk '/Coco Whisper Signing/ {print $2; exit}')"
if [ -z "$HASH" ]; then
  echo "::error::the signing identity did not show up in the keychain"
  security find-identity -p codesigning "$KC"
  exit 1
fi

codesign --force --deep --keychain "$KC" --sign "$HASH" "$APP"
codesign --verify --deep --strict "$APP"

# The whole point: the requirement has to name the certificate. A cdhash here
# means this build would lose the permission on the next update.
REQ="$(codesign -d -r- "$APP" 2>&1)"
echo "$REQ"
if echo "$REQ" | grep -q 'cdhash' || ! echo "$REQ" | grep -q 'certificate'; then
  echo "::error::the designated requirement does not name the certificate"
  exit 1
fi
