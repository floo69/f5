#!/usr/bin/env bash
# Environment check for ThumbShield. Prints fixes; exits non-zero if anything is missing.
ok=0

if command -v tesseract >/dev/null 2>&1; then
  langs=$(tesseract --list-langs 2>/dev/null)
  for l in eng mal; do
    if grep -qx "$l" <<<"$langs"; then echo "[ok]   tesseract lang $l"
    else echo "[miss] tesseract lang $l -> sudo apt install tesseract-ocr-$l"; ok=1; fi
  done
else
  echo "[miss] tesseract -> sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-mal"; ok=1
fi

if command -v node >/dev/null 2>&1; then
  major=$(node -p 'process.versions.node.split(".")[0]')
  if [ "$major" -ge 20 ]; then echo "[ok]   node $(node --version)"
  else echo "[miss] node >= 20 required (found $(node --version))"; ok=1; fi
else
  echo "[miss] node >= 20 -> install via nvm"; ok=1
fi

pw_cache="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"
if ls -d "$pw_cache"/chromium* >/dev/null 2>&1; then echo "[ok]   playwright chromium ($pw_cache)"
else echo "[miss] playwright chromium -> npx playwright install chromium"; ok=1; fi

if command -v uv >/dev/null 2>&1; then echo "[ok]   uv $(uv --version | cut -d' ' -f2)"
else echo "[miss] uv -> curl -LsSf https://astral.sh/uv/install.sh | sh"; ok=1; fi

exit $ok
