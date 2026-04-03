#!/usr/bin/env bash
#
# scan_cloudinary.sh
#
# Scan the repository for references to external Cloudinary assets.  The
# presence of cloudinary.com URLs indicates that not all media files are
# being served locally.  The script exits with a non‑zero status if any
# references are found.

set -euo pipefail

MATCHES=$(grep -R -n -i -e "cloudinary" -e "res.cloudinary" . || true)
if [ -n "$MATCHES" ]; then
  echo "❌ Cloudinary references found:"
  echo "$MATCHES"
  exit 1
else
  echo "✅ No Cloudinary references found in the project"
fi