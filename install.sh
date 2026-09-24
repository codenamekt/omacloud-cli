#!/bin/sh
set -eu

echo "==> Downloading OmaCloud CLI..."
TMP_BIN="$(mktemp)"
trap 'rm -f "$TMP_BIN"' EXIT

curl -fsSL https://raw.githubusercontent.com/codenamekt/omacloud-cli/main/omacloud -o "$TMP_BIN"
chmod +x "$TMP_BIN"

echo "==> Installing omacloud to /usr/local/bin/omacloud..."
if [ "$(id -u)" -eq 0 ]; then
    install -m 0755 "$TMP_BIN" /usr/local/bin/omacloud
else
    sudo install -m 0755 "$TMP_BIN" /usr/local/bin/omacloud
fi

echo "✓ OmaCloud CLI successfully installed to /usr/local/bin/omacloud"
echo "Run 'omacloud --help' to get started."
