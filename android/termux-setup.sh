#!/data/data/com.termux/files/usr/bin/bash
# Installerar Marknadsradar i Termux (Android). Körs en gång: bash android/termux-setup.sh
set -e
cd "$(dirname "$0")/.."
echo "== 1/4 Systempaket"
pkg update -y
pkg install -y python python-numpy tur-repo libxml2 libxslt
pkg install -y python-pandas
pkg install -y python-pydantic || true
echo "== 2/4 Virtuell miljö (delar systempaketen numpy/pandas)"
python -m venv --system-site-packages "$HOME/.marknadsradar-venv"
. "$HOME/.marknadsradar-venv/bin/activate"
pip install --upgrade pip
echo "== 3/4 Webbserver"
pip install fastapi uvicorn
echo "== 4/4 Kursdata (yfinance)"
if pip install "yfinance>=0.2.50"; then
  echo "yfinance installerades."
else
  echo "yfinance krävde ett paket som inte kan byggas på Android (curl_cffi). Provar utan det."
  pip install --no-deps yfinance
  pip install requests multitasking platformdirs pytz frozendict peewee beautifulsoup4 protobuf websockets || true
fi
echo
echo "== Kontroll"
python - <<'PY'
import importlib
for m in ("numpy", "pandas", "fastapi", "uvicorn", "yfinance"):
    try:
        importlib.import_module(m); print("OK     ", m)
    except Exception as e:
        print("SAKNAS ", m, "-", str(e)[:100])
PY
echo
echo "Klart. Starta med:  bash android/start.sh"
echo "Fungerar inte yfinance kan du ändå köra med demodata:  bash android/start.sh --demo"
