#!/data/data/com.termux/files/usr/bin/bash
# Startar Marknadsradar i Termux och öppnar den i webbläsaren. Skicka med --demo för demodata.
cd "$(dirname "$0")/.."
. "$HOME/.marknadsradar-venv/bin/activate" 2>/dev/null || { echo "Kör först: bash android/termux-setup.sh"; exit 1; }
command -v termux-wake-lock >/dev/null && termux-wake-lock   # håller processen vid liv när skärmen släcks
PORT=8000
( sleep 3; URL="http://localhost:$PORT"
  if command -v termux-open-url >/dev/null; then termux-open-url "$URL"; else am start -a android.intent.action.VIEW -d "$URL" >/dev/null 2>&1; fi ) &
echo "Marknadsradar körs på http://localhost:$PORT  (avsluta med Ctrl+C)"
python run.py --no-browser --port $PORT "$@"
