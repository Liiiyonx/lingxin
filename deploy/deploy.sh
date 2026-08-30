#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/lingxin}"
cd "$APP_DIR"

echo "==> Installing system packages"
apt-get update
apt-get install -y python3.10 python3.10-venv python3-pip build-essential nginx

echo "==> Creating virtualenv"
if [ ! -d venv ]; then
  python3.10 -m venv venv
fi
source venv/bin/activate
pip install -U pip
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

if [ ! -f .env ]; then
  cp deploy/.env.production.example .env
  echo "==> Created .env from template; edit it before starting!"
fi

echo "==> Initializing database and demo data"
python -c "from core.database import DatabaseManager; DatabaseManager().init_db()"
python seed_v31.py
python scripts/verify_test_accounts.py

echo "==> Installing systemd service"
cp deploy/lingxin.service /etc/systemd/system/lingxin.service
systemctl daemon-reload
systemctl enable --now lingxin

echo "==> Installing nginx site"
cp deploy/nginx-lingxin.conf /etc/nginx/sites-available/lingxin
ln -sf /etc/nginx/sites-available/lingxin /etc/nginx/sites-enabled/lingxin
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "==> Done. Service status:"
systemctl status lingxin --no-pager | head -20
