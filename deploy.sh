#!/bin/bash
cd /root/lq45-signal-bot
pip3 install -r requirements.txt --quiet
cp systemd/lq45-signal-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable lq45-signal-bot
systemctl restart lq45-signal-bot
systemctl status lq45-signal-bot --no-pager
echo "🚀 Deploy complete!"
