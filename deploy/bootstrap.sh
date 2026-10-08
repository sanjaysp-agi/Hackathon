#!/bin/bash
# =============================================================================
# Intelligent Workflow Manager — one-shot EC2 setup (Amazon Linux 2023)
#
# Installs everything, builds the DB from the workbook, builds the React app,
# runs the FastAPI backend under systemd, and serves it all through nginx.
# Bedrock auth uses the EC2 instance role (no keys on disk).
#
# CODE TRANSPORT: the code arrives as a tarball. CloudFormation passes its
# location in /etc/iwm.conf as CODE_URL (a presigned S3 URL) — no git, no
# GitHub, no AWS CLI needed on the box. A git REPO_URL is still supported as a
# fallback for the manual path documented in the README.
#
# AUTH: when an ALB + Cognito sits in front (AUTH_MODE=cognito), nginx does NOT
# add Basic Auth — the load balancer already authenticated the user. When
# AUTH_MODE=basic (no load balancer), nginx gates the site with Basic Auth.
# =============================================================================
set -euxo pipefail

# shellcheck disable=SC1091
source /etc/iwm.conf 2>/dev/null || true
APP_REGION="${APP_REGION:-us-east-1}"
AUTH_MODE="${AUTH_MODE:-basic}"
BASIC_USER="${BASIC_USER:-admin}"
BASIC_PASS="${BASIC_PASS:-changeme}"
CODE_URL="${CODE_URL:-}"
REPO_URL="${REPO_URL:-}"
APP_DIR=/opt/iwm

# --- a little swap so the node build never OOMs on a small instance ----------
if [ ! -f /swapfile ]; then
  dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
fi

# --- packages ----------------------------------------------------------------
dnf -y update
dnf -y install tar gzip nginx python3.11 python3.11-pip httpd-tools
dnf -y install nodejs npm || { curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -; dnf -y install nodejs; }

# --- get the code ------------------------------------------------------------
# Preferred: a code tarball via presigned S3 URL (CODE_URL). Fallback: git.
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"
if [ -n "$CODE_URL" ]; then
  curl -fSL "$CODE_URL" -o /tmp/iwm-code.tgz
  tar -xzf /tmp/iwm-code.tgz -C "$APP_DIR"
  rm -f /tmp/iwm-code.tgz
elif [ -n "$REPO_URL" ]; then
  dnf -y install git
  git clone "$REPO_URL" "$APP_DIR"
else
  echo "FATAL: neither CODE_URL nor REPO_URL set" >&2
  exit 1
fi
cd "$APP_DIR"

# --- backend: venv + deps + build the SQLite DB from the workbook ------------
python3.11 -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip
backend/.venv/bin/pip install -r backend/requirements.txt gunicorn
( cd backend && .venv/bin/python -m app.lsmv )      # builds backend/lsmv.db from the .xlsb

# --- frontend: build the static site ----------------------------------------
( cd frontend && (npm ci || npm install) && npm run build )   # outputs frontend/dist

# --- backend as a service (single worker: SQLite is a single-writer DB) ------
cat >/etc/systemd/system/iwm.service <<EOF
[Unit]
Description=Intelligent Workflow Manager API
After=network.target

[Service]
WorkingDirectory=$APP_DIR/backend
Environment=AWS_REGION=$APP_REGION
ExecStart=$APP_DIR/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now iwm

# --- optional login gate (only when there's no ALB+Cognito in front) --------
AUTH_BLOCK=""
if [ "$AUTH_MODE" = "basic" ]; then
  htpasswd -cb /etc/nginx/.htpasswd "$BASIC_USER" "$BASIC_PASS"
  AUTH_BLOCK='auth_basic "LSMV Control Tower"; auth_basic_user_file /etc/nginx/.htpasswd;'
fi

# --- nginx: serve the built app + proxy /api + a /healthz for the ALB -------
cat >/etc/nginx/nginx.conf <<NGINX
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log;
pid /run/nginx.pid;
events { worker_connections 1024; }
http {
  include /etc/nginx/mime.types;
  default_type application/octet-stream;
  sendfile on;
  server {
    listen 80 default_server;
    server_name _;
    root /opt/iwm/frontend/dist;
    index index.html;

    # ALB health check — must stay unauthenticated
    location = /healthz { auth_basic off; default_type text/plain; return 200 "ok\n"; }

    $AUTH_BLOCK

    location /api/ {
      proxy_pass http://127.0.0.1:8000;
      proxy_http_version 1.1;
      proxy_set_header Host \$host;
      proxy_set_header X-Real-IP \$remote_addr;
      proxy_buffering off;          # keep the agent chat (SSE) streaming
      proxy_read_timeout 300s;
    }
    location / { try_files \$uri /index.html; }
  }
}
NGINX

systemctl enable nginx
nginx -t
systemctl restart nginx

echo "=== IWM is up. ==="
