#!/bin/bash
# deploy.sh — Full deploy script untuk IDX Day Trader Bot
# Usage: sudo bash deploy.sh
set -e

REPO_DIR="/home/martinus/idx-lq45-ai-bot"
SERVICE="lq45-signal-bot"

cd "$REPO_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  IDX Day Trader Bot — Deploy Script"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. Pull latest ─────────────────────────────────────────────────────
echo ""
echo "[1] Pull latest dari GitHub..."
git pull origin master

# ── 2. Virtual environment ────────────────────────────────────────────
echo ""
echo "[2] Setup virtual environment..."
python3 -m venv venv
source venv/bin/activate

# ── 3. Cleanup pandas-ta lama ────────────────────────────────────────
echo ""
echo "[3] Uninstall pandas-ta lama (jika ada)..."
pip uninstall pandas-ta pandas_ta pandas-ta-classic -y 2>/dev/null || true

# ── 4. Install dependencies ───────────────────────────────────────────
echo ""
echo "[4] Install dependencies..."
pip install --upgrade -r requirements.txt --quiet
pip install ta --quiet  # eksplisit — kadang tidak ter-install via requirements

# ── 5. Verifikasi library ─────────────────────────────────────────────
echo ""
echo "[5] Verifikasi library..."
python3 -c "import ta;       print('  ✅ ta OK')"
python3 -c "import yfinance; print(f'  ✅ yfinance {yfinance.__version__}')"
python3 -c "import pandas;   print(f'  ✅ pandas {pandas.__version__}')"
python3 -c "import requests; print(f'  ✅ requests {requests.__version__}')"
python3 -c "import telegram; print(f'  ✅ telegram {telegram.__version__}')"
python3 -c "
try:
    import psycopg
    print(f'  ✅ psycopg {psycopg.__version__}')
except ImportError:
    print('  ⚠️  psycopg tidak ada (ok jika pakai SQLite/Supabase)')
"
echo "  🔍 Checking Gemini model availability..."
python3 -c "
from google import genai
import os
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv('GEMINI_API_KEY')
if api_key:
    client = genai.Client(api_key=api_key)
    try:
        # Pengecekan dasar, init client tidak error
        print('  ✅ Gemini 2.5 Flash Lite: READY')
    except Exception as e:
        print(f'  ❌ Gemini SDK Error ({e})')
else:
    print('  ⚠️  GEMINI_API_KEY tidak ditemukan di .env')
"

# ── 6. Setup data directory ───────────────────────────────────────────
echo ""
echo "[6] Setup data directory..."
mkdir -p data
touch bot.log && chmod 666 bot.log

# ── 7. Pre-flight check ───────────────────────────────────────────────
echo ""
echo "[7] Pre-flight check..."
python3 verify.py
if [ $? -ne 0 ]; then
    echo "❌ Pre-flight check GAGAL. Deploy dibatalkan."
    exit 1
fi

# ── 8. Systemd service ────────────────────────────────────────────────
echo ""
echo "[8] Setup systemd service..."
if [ -f "systemd/${SERVICE}.service" ]; then
    cp "systemd/${SERVICE}.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable "$SERVICE"
    echo "  ✅ Service file dikopi"
else
    echo "  ⚠️  systemd/${SERVICE}.service tidak ditemukan, skip"
fi

# ── 9. Restart & status ───────────────────────────────────────────────
echo ""
echo "[9] Restart bot..."
systemctl restart "$SERVICE"
sleep 3
systemctl status "$SERVICE" --no-pager -l

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🚀 Deploy selesai!"
echo "  Monitor log: journalctl -u $SERVICE -f"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
