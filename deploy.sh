#!/bin/bash
cd /root/idx-lq45-ai-bot
git pull origin main
source venv/bin/activate
pip install -r requirements.txt -q
systemctl restart idx-ai-bot
systemctl status idx-ai-bot --no-pager
