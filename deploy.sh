#!/bin/bash
set -e

cd /home/martinus/idx-lq45-ai-bot

echo "📦 Setup virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "🧹 Uninstall pandas-ta lama (jika ada)..."
pip uninstall pandas-ta pandas_ta pandas-ta-classic -y 2>/dev/null || true

echo "📥 Install dependencies..."
pip install -r requirements.txt --quiet

echo "📥 Install ta secara eksplisit..."
pip install ta --quiet

echo "✅ Verifikasi library..."
python3 -c "import ta; print('  ta: OK')"
python3 -c "import yfinance; print(f'  yfinance: {yfinance.__version__}')"
python3 -c "import pandas; print(f'  pandas: {pandas.__version__}')"
python3 -c "import requests; print(f'  requests: {requests.__version__}')"

echo "🔧 Setup file & service..."
touch bot.log && chmod 666 bot.log
cp systemd/lq45-signal-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable lq45-signal-bot
systemctl restart lq45-signal-bot
systemctl status lq45-signal-bot --no-pager

echo "🚀 Deploy complete!"
