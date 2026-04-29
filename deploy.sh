#!/bin/bash
cd /home/martinus/idx-lq45-ai-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt --quiet
touch bot.log && chmod 666 bot.log
cp systemd/lq45-signal-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable lq45-signal-bot
systemctl restart lq45-signal-bot
systemctl status lq45-signal-bot --no-pager
echo "🚀 Deploy complete!"
