#!/usr/bin/env bash
# BSOBPDF - inicio para Linux y macOS
set -e
cd "$(dirname "$0")"

echo
echo "  BSOBPDF - herramientas PDF en tu computador"
echo "  ------------------------------------------"
echo

PY=""
for cand in python3.12 python3.13 python3.11 python3.10 python3.9 python3; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' 2>/dev/null; then
    PY="$cand"; break
  fi
done
if [ -z "$PY" ]; then
  echo "  No se encontro Python 3.9 o superior. Instalalo (por ejemplo: sudo apt install python3 python3-venv)."
  exit 1
fi

VENV="${XDG_DATA_HOME:-$HOME/.local/share}/bsobpdf/venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "  Preparando BSOBPDF por primera vez. Esto tarda unos minutos..."
  "$PY" -m venv "$VENV"
fi

if ! cmp -s requirements.txt "$VENV/requirements.ok"; then
  echo "  Instalando componentes (necesita internet solo esta vez)..."
  "$VENV/bin/python" -m pip install --upgrade pip --disable-pip-version-check -q
  "$VENV/bin/python" -m pip install -r requirements.txt --disable-pip-version-check
  cp requirements.txt "$VENV/requirements.ok"
fi

echo "  Abriendo BSOBPDF en tu navegador..."
exec "$VENV/bin/python" app.py
