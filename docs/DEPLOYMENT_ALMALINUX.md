# Quot PSE — AlmaLinux 8.1 VPS Deployment Guide

**Target:** Single-node AlmaLinux 8.x VPS (8 GB RAM / 4 vCPU / 100 GB SSD minimum for a State-sized tenant; 16 GB / 8 vCPU / 250 GB recommended).
**Stack:** PostgreSQL 15, Redis 7, Python 3.12, Node 20, Gunicorn + systemd, Celery, Nginx, Certbot TLS.
**End state:** A hardened, SSL-terminated, observable production box serving Quot PSE at `https://<state>.quotpse.ng`.

Everything in this guide is idempotent — you can re-run a step without breaking what's already there.

---

## 0. Before you begin

### 0.1 You need

- A fresh AlmaLinux 8.1+ VPS with public IPv4 and root/sudo access.
- A domain you control. At minimum a wildcard record `*.quotpse.ng` pointing to the server's IP.
- SMTP credentials (for transactional emails; Gmail/SES/Postmark all work).
- Optional but recommended: Sentry DSN and a static IP for whitelisting Redis.

### 0.2 Conventions used in this guide

- Commands prefixed `#` run as root (or via `sudo`).
- Commands prefixed `$` run as the application user `quotpse` (created in §2.2).
- Paths: app code lives in `/opt/quotpse`, config in `/etc/quotpse`, logs in `/var/log/quotpse`, backups in `/var/backups/quotpse`.

---

## 1. Server hardening — do this first

```bash
# 1.1 Patch the system
# dnf update -y
# dnf install -y epel-release
# dnf install -y vim wget curl git tar unzip firewalld fail2ban policycoreutils-python-utils

# 1.2 Set hostname + timezone
# hostnamectl set-hostname quotpse-prod-01
# timedatectl set-timezone Africa/Lagos

# 1.3 Swap (only if your VPS has <8 GB RAM or no swap)
# fallocate -l 4G /swapfile && chmod 600 /swapfile
# mkswap /swapfile && swapon /swapfile
# echo '/swapfile none swap sw 0 0' >> /etc/fstab

# 1.4 Firewall — default-deny, allow only what we need
# systemctl enable --now firewalld
# firewall-cmd --permanent --add-service=ssh
# firewall-cmd --permanent --add-service=http
# firewall-cmd --permanent --add-service=https
# firewall-cmd --reload

# 1.5 fail2ban to throttle SSH brute-force
# systemctl enable --now fail2ban

# 1.6 SELinux — keep enforcing, verify
# getenforce            # should print: Enforcing
# setsebool -P httpd_can_network_connect on
```

### 1.7 SSH hardening (recommended)

Edit `/etc/ssh/sshd_config` and set:

```conf
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
```

Then `systemctl restart sshd` — *only after* you've verified you can log in as a sudo user with a key.

---

## 2. Application user + directory layout

```bash
# 2.1 Create a non-login service user
# useradd -r -m -d /home/quotpse -s /bin/bash quotpse
# mkdir -p /opt/quotpse /etc/quotpse /var/log/quotpse /var/backups/quotpse
# chown -R quotpse:quotpse /opt/quotpse /var/log/quotpse /var/backups/quotpse
# chmod 750 /etc/quotpse

# 2.2 Let the app user use sudo for systemd restarts (optional convenience)
# visudo -f /etc/sudoers.d/quotpse
#   quotpse ALL=(root) NOPASSWD: /bin/systemctl restart quotpse-web quotpse-celery quotpse-beat, /bin/systemctl status quotpse-*
```

---

## 3. System dependencies

### 3.1 PostgreSQL 15 (from official PGDG repo)

```bash
# dnf install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-8-x86_64/pgdg-redhat-repo-latest.noarch.rpm
# dnf -qy module disable postgresql   # disable the AppStream PG module
# dnf install -y postgresql15 postgresql15-server postgresql15-contrib postgresql15-devel

# /usr/pgsql-15/bin/postgresql-15-setup initdb
# systemctl enable --now postgresql-15
```

Edit `/var/lib/pgsql/15/data/pg_hba.conf` — change `peer` to `scram-sha-256` for the `quotpse` user on `127.0.0.1/32` and `::1/128`. Edit `postgresql.conf` to set:

```conf
listen_addresses = 'localhost'
shared_buffers = 2GB            # ~25% of RAM for dedicated DB boxes
work_mem = 32MB
maintenance_work_mem = 256MB
effective_cache_size = 6GB      # ~75% of RAM
wal_buffers = 16MB
max_connections = 200
```

Then:

```bash
# systemctl restart postgresql-15

# Create the application role + database
# sudo -u postgres psql <<SQL
CREATE USER quotpse WITH ENCRYPTED PASSWORD 'CHANGE_ME_STRONG';
CREATE DATABASE quot_pse OWNER quotpse;
GRANT ALL PRIVILEGES ON DATABASE quot_pse TO quotpse;
ALTER USER quotpse CREATEDB;    -- django-tenants needs CREATEDB to create schemas
SQL
```

### 3.2 Redis 7

```bash
# dnf module enable -y redis:7
# dnf install -y redis
# systemctl enable --now redis
```

Edit `/etc/redis/redis.conf`:
```conf
bind 127.0.0.1
requirepass CHANGE_ME_REDIS_STRONG
maxmemory 1gb
maxmemory-policy allkeys-lru
```

Then `systemctl restart redis`.

### 3.3 Python 3.12

```bash
# dnf module install -y python39    # fallback: AppStream only ships 3.6/3.8/3.9/3.11 on AL8
# or build 3.12 from source:
# dnf install -y gcc openssl-devel bzip2-devel libffi-devel zlib-devel readline-devel sqlite-devel
# cd /tmp && wget https://www.python.org/ftp/python/3.12.3/Python-3.12.3.tgz
# tar xzf Python-3.12.3.tgz && cd Python-3.12.3
# ./configure --enable-optimizations --prefix=/opt/python3.12
# make -j$(nproc) && make altinstall
# ln -sf /opt/python3.12/bin/python3.12 /usr/local/bin/python3.12
# ln -sf /opt/python3.12/bin/pip3.12 /usr/local/bin/pip3.12
```

### 3.4 Node.js 20 (for the frontend build)

```bash
# dnf module enable -y nodejs:20
# dnf install -y nodejs
# node --version   # should print v20.x
```

### 3.5 Nginx + Certbot

```bash
# dnf install -y nginx certbot python3-certbot-nginx
# systemctl enable nginx
```

### 3.6 Build & system libs

```bash
# dnf install -y gcc gcc-c++ make libffi-devel openssl-devel \
                 libxml2-devel libxslt-devel libjpeg-turbo-devel \
                 cairo pango libpq-devel
```

`libxml2-devel` / `libxslt-devel` are required for `lxml` (statutory XSD validation). `cairo`/`pango` are required for WeasyPrint PDF export.

---

## 4. Deploy the application

### 4.1 Clone the repo

```bash
# su - quotpse
$ cd /opt/quotpse
$ git clone https://github.com/oosadiaye/Quot-PSA.git app
$ cd app
```

### 4.2 Python virtualenv + dependencies

```bash
$ python3.12 -m venv /opt/quotpse/venv
$ source /opt/quotpse/venv/bin/activate
$ pip install --upgrade pip wheel
$ pip install -r requirements.txt
$ pip install gunicorn
```

### 4.3 Environment file

Create `/etc/quotpse/quotpse.env` (root-owned, `0640`, group `quotpse`):

```bash
# DJANGO
DEBUG=false
SECRET_KEY=CHANGE_ME_GENERATE_50_CHAR_RANDOM
ALLOWED_HOSTS=.quotpse.ng,quotpse.ng

# DATABASE
DB_NAME=quot_pse
DB_USER=quotpse
DB_PASSWORD=CHANGE_ME_STRONG
DB_HOST=127.0.0.1
DB_PORT=5432
CONN_MAX_AGE=60

# REDIS / CACHE / CELERY
REDIS_URL=redis://:CHANGE_ME_REDIS_STRONG@127.0.0.1:6379/0
CELERY_BROKER_URL=redis://:CHANGE_ME_REDIS_STRONG@127.0.0.1:6379/1
CELERY_RESULT_BACKEND=redis://:CHANGE_ME_REDIS_STRONG@127.0.0.1:6379/2

# EMAIL (SMTP)
EMAIL_HOST=smtp.yourprovider.com
EMAIL_PORT=587
EMAIL_HOST_USER=postmaster@quotpse.ng
EMAIL_HOST_PASSWORD=CHANGE_ME_SMTP
EMAIL_USE_TLS=true
DEFAULT_FROM_EMAIL=noreply@quotpse.ng
SUPPORT_EMAIL=support@quotpse.ng

# OBSERVABILITY
SENTRY_DSN=
LOG_LEVEL=INFO
LOG_FORMAT=json

# JWT
JWT_ACCESS_TOKEN_LIFETIME_MINUTES=15
JWT_REFRESH_TOKEN_LIFETIME_HOURS=24
```

```bash
# chown root:quotpse /etc/quotpse/quotpse.env && chmod 0640 /etc/quotpse/quotpse.env
```

### 4.4 Django bootstrap

Load the env, then run the standard Django commands:

```bash
$ export $(grep -v '^#' /etc/quotpse/quotpse.env | xargs)
$ cd /opt/quotpse/app
$ python manage.py check --deploy      # must show 0 issues
$ python manage.py migrate_schemas --shared   # creates public schema
$ python manage.py collectstatic --noinput    # → /opt/quotpse/app/staticfiles
$ python manage.py createsuperuser            # platform super-admin
```

### 4.5 Create the first tenant

```bash
$ python manage.py shell <<PY
from tenants.models import Client, Domain
c = Client.objects.create(schema_name='delta_state', name='Delta State Government')
Domain.objects.create(tenant=c, domain='delta.quotpse.ng', is_primary=True)
PY
$ python manage.py migrate_schemas --tenant --schema=delta_state
$ python manage.py tenant_command seed_ncoa --schema=delta_state
$ python manage.py tenant_command seed_accounting_data --schema=delta_state
```

### 4.6 Frontend build

```bash
$ cd /opt/quotpse/app/frontend
$ npm ci
$ npm run build                       # → frontend/dist/
```

---

## 5. systemd services

### 5.1 Gunicorn (web) — `/etc/systemd/system/quotpse-web.service`

```ini
[Unit]
Description=Quot PSE — Gunicorn application server
After=network.target postgresql-15.service redis.service
Requires=postgresql-15.service redis.service

[Service]
Type=notify
User=quotpse
Group=quotpse
WorkingDirectory=/opt/quotpse/app
EnvironmentFile=/etc/quotpse/quotpse.env
RuntimeDirectory=quotpse
RuntimeDirectoryMode=0750
ExecStart=/opt/quotpse/venv/bin/gunicorn \
    --workers 4 \
    --worker-class gthread \
    --threads 4 \
    --timeout 120 \
    --bind unix:/run/quotpse/gunicorn.sock \
    --umask 0007 \
    --access-logfile /var/log/quotpse/access.log \
    --error-logfile  /var/log/quotpse/error.log \
    --capture-output \
    quot_pse.wsgi:application
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

### 5.2 Celery worker — `/etc/systemd/system/quotpse-celery.service`

```ini
[Unit]
Description=Quot PSE — Celery worker
After=network.target redis.service postgresql-15.service
Requires=redis.service postgresql-15.service

[Service]
Type=simple
User=quotpse
Group=quotpse
WorkingDirectory=/opt/quotpse/app
EnvironmentFile=/etc/quotpse/quotpse.env
ExecStart=/opt/quotpse/venv/bin/celery -A quot_pse worker \
    --loglevel=info --concurrency=4 \
    --logfile=/var/log/quotpse/celery.log
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 5.3 Celery beat (scheduled tasks) — `/etc/systemd/system/quotpse-beat.service`

```ini
[Unit]
Description=Quot PSE — Celery beat scheduler
After=network.target redis.service
Requires=redis.service

[Service]
Type=simple
User=quotpse
Group=quotpse
WorkingDirectory=/opt/quotpse/app
EnvironmentFile=/etc/quotpse/quotpse.env
ExecStart=/opt/quotpse/venv/bin/celery -A quot_pse beat \
    --loglevel=info \
    --logfile=/var/log/quotpse/beat.log \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 5.4 Enable + start

```bash
# systemctl daemon-reload
# systemctl enable --now quotpse-web quotpse-celery quotpse-beat
# systemctl status quotpse-web --no-pager
# journalctl -u quotpse-web -n 30
```

---

## 6. Nginx reverse proxy

Write `/etc/nginx/conf.d/quotpse.conf`:

```nginx
upstream quotpse_app {
    server unix:/run/quotpse/gunicorn.sock fail_timeout=0;
}

# ── HTTP → HTTPS redirect (Certbot writes the 443 block) ──
server {
    listen 80;
    listen [::]:80;
    server_name quotpse.ng *.quotpse.ng;

    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://$host$request_uri; }
}

# ── Main HTTPS server ──
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name quotpse.ng *.quotpse.ng;

    # Certbot manages these two lines
    # ssl_certificate /etc/letsencrypt/live/quotpse.ng/fullchain.pem;
    # ssl_certificate_key /etc/letsencrypt/live/quotpse.ng/privkey.pem;

    # Strong TLS defaults
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    client_max_body_size 50M;

    # Frontend build
    root /opt/quotpse/app/frontend/dist;
    index index.html;

    # Static files collected by Django
    location /static/ {
        alias /opt/quotpse/app/staticfiles/;
        expires 30d;
        access_log off;
        add_header Cache-Control "public, immutable";
    }

    # Uploaded files (if any)
    location /media/ {
        alias /opt/quotpse/app/media/;
    }

    # Django API + admin
    location ~ ^/(api|admin|healthz|readyz|metrics)/ {
        proxy_pass http://quotpse_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Tenant-Domain $host;
        proxy_redirect off;
        proxy_read_timeout 120s;
    }

    # Frontend SPA fallback — must be last
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

Test, enable, and obtain a wildcard cert:

```bash
# nginx -t && systemctl reload nginx
# certbot --nginx -d quotpse.ng -d '*.quotpse.ng' --agree-tos -m ops@quotpse.ng
# systemctl enable --now certbot-renew.timer
```

### 6.1 SELinux adjustment

```bash
# semanage permissive -a httpd_t    # optional — only if you see AVC denials
# or more targeted:
# setsebool -P httpd_can_network_connect 1
# semanage fcontext -a -t httpd_sys_content_t "/opt/quotpse/app/staticfiles(/.*)?"
# semanage fcontext -a -t httpd_sys_content_t "/opt/quotpse/app/frontend/dist(/.*)?"
# restorecon -Rv /opt/quotpse/app/staticfiles /opt/quotpse/app/frontend/dist
```

---

## 7. Backups

### 7.1 Backup script (already in the repo)

The repo ships `scripts/backup.sh`. Install it:

```bash
# cp /opt/quotpse/app/scripts/backup.sh /usr/local/bin/quotpse-backup
# chmod 0755 /usr/local/bin/quotpse-backup
# chown root:root /usr/local/bin/quotpse-backup
```

### 7.2 Systemd timer — `/etc/systemd/system/quotpse-backup.service`

```ini
[Unit]
Description=Quot PSE — nightly pg_dump per tenant
After=postgresql-15.service

[Service]
Type=oneshot
User=quotpse
EnvironmentFile=/etc/quotpse/quotpse.env
Environment=BACKUP_DIR=/var/backups/quotpse
ExecStart=/usr/local/bin/quotpse-backup
```

And `/etc/systemd/system/quotpse-backup.timer`:

```ini
[Unit]
Description=Run quotpse-backup nightly at 01:15

[Timer]
OnCalendar=*-*-* 01:15:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
# systemctl enable --now quotpse-backup.timer
# systemctl list-timers | grep quotpse
```

### 7.3 Off-site copy (rclone)

```bash
# dnf install -y rclone
# sudo -u quotpse rclone config   # set up 's3' or 'b2' remote
# crontab -u quotpse -e
#    30 2 * * * rclone sync /var/backups/quotpse s3:quotpse-backups --log-file=/var/log/quotpse/rclone.log
```

---

## 8. Logging & monitoring

### 8.1 Log rotation — `/etc/logrotate.d/quotpse`

```
/var/log/quotpse/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    create 0640 quotpse quotpse
}
```

### 8.2 Prometheus scrape

```yaml
# prometheus.yml
- job_name: 'quotpse'
  metrics_path: /metrics
  scrape_interval: 30s
  static_configs:
    - targets: ['quotpse.ng:443']
  scheme: https
```

### 8.3 Sentry

Set `SENTRY_DSN` in `/etc/quotpse/quotpse.env` and restart the web service.

### 8.4 Health probes

- `GET /healthz` → 200 once systemd is up (liveness)
- `GET /readyz` → 200 once DB + Redis are reachable (readiness)
- `GET /metrics` → Prometheus text format

---

## 9. Smoke-test the deployment

Run these *in order*; each should succeed before you move on:

```bash
# 9.1 Backend up on the socket
# curl --unix-socket /run/quotpse/gunicorn.sock http://localhost/healthz

# 9.2 Nginx proxying
# curl -sSI https://quotpse.ng/healthz | head -1    # → HTTP/2 200

# 9.3 OpenAPI schema
# curl -s https://quotpse.ng/api/schema/ | head -5  # → openapi: 3.0.3 ...

# 9.4 Tenant routing
# curl -sS -H "X-Tenant-Domain: delta.quotpse.ng" https://quotpse.ng/api/v1/core/health-tenant/

# 9.5 Frontend
# curl -sSI https://quotpse.ng/ | head -1           # → HTTP/2 200
# curl -s https://quotpse.ng/ | grep -i 'Quot PSE'

# 9.6 Celery
# journalctl -u quotpse-celery --since "1 minute ago" | grep ready
```

### 9.7 Login

In a browser, go to `https://delta.quotpse.ng/`, log in as the superuser you created in §4.4, and confirm the dashboard renders with the sidebar intact.

---

## 10. Updates & rollback

### 10.1 Zero-downtime update

```bash
$ cd /opt/quotpse/app
$ git fetch origin
$ git log --oneline HEAD..origin/main        # review incoming changes
$ git pull --ff-only
$ source /opt/quotpse/venv/bin/activate
$ pip install -r requirements.txt
$ python manage.py migrate_schemas            # runs public + all tenants
$ python manage.py collectstatic --noinput
$ cd frontend && npm ci && npm run build && cd ..
$ sudo systemctl restart quotpse-web quotpse-celery quotpse-beat
$ curl -sSI https://quotpse.ng/healthz | head -1
```

### 10.2 Rollback

```bash
$ git reset --hard <previous-SHA>
$ pip install -r requirements.txt
$ python manage.py migrate_schemas            # only if migrations are reversible
$ python manage.py collectstatic --noinput
$ cd frontend && npm run build && cd ..
$ sudo systemctl restart quotpse-web quotpse-celery quotpse-beat
```

If you shipped an irreversible migration (data backfill, column drop), **don't reverse it** — forward-fix with a hotfix release instead.

---

## 11. Common post-install issues

| Symptom | Cause | Fix |
|---|---|---|
| `502 Bad Gateway` after install | Nginx can't reach the Gunicorn socket | `sudo chmod 0770 /run/quotpse` — the socket dir must be group-readable. Verify with `ls -la /run/quotpse/`. |
| `502` after reboot only | `/run/quotpse` is tmpfs and gets wiped | Confirm `RuntimeDirectory=quotpse` is in the systemd unit (it is in §5.1). |
| `could not connect to database` | Postgres using `peer` auth but Django using password | Edit `pg_hba.conf`, switch 127.0.0.1 lines to `scram-sha-256`, `systemctl restart postgresql-15`. |
| `OperationalError: FATAL: too many connections` | `max_connections` too low or CONN_MAX_AGE too high | Lower `CONN_MAX_AGE` in `.env` to 30 or install pgbouncer (config in `deploy/pgbouncer.ini`). |
| `403 CSRF verification failed` on the admin | Nginx not forwarding `X-Forwarded-Proto` | Confirm the `proxy_set_header X-Forwarded-Proto $scheme` line is in the location block. |
| `Permission denied` on static files | SELinux context missing | Re-run the `semanage fcontext` + `restorecon` lines in §6.1. |
| Celery logs `AuthenticationError` | `REDIS_URL` missing the password | Format is `redis://:PASSWORD@host:6379/0` — the `:` before password is required. |
| Tenant URL returns 404 on every API call | `X-Tenant-Domain` header not forwarded | Confirm the `proxy_set_header X-Tenant-Domain $host` line is in `quotpse.conf`. |
| WeasyPrint PDF export 500 | `cairo`/`pango` libs missing | `dnf install -y cairo pango` and restart the web service. |

---

## 12. Hardening checklist before go-live

- [ ] `DEBUG=false` confirmed in `/etc/quotpse/quotpse.env`
- [ ] A non-default `SECRET_KEY` (50+ random characters)
- [ ] Strong DB password, strong Redis password
- [ ] SSH key-only, `PermitRootLogin no`
- [ ] firewalld enabled, only 22/80/443 open
- [ ] TLS cert valid, auto-renewal timer enabled
- [ ] HSTS header confirmed in response
- [ ] nightly backup timer running + verified a restore in staging
- [ ] Sentry DSN set and receiving events
- [ ] Prometheus scraping `/metrics` successfully
- [ ] `/healthz` and `/readyz` both 200
- [ ] Test tenant created + able to log in + post a journal
- [ ] Runbook location documented: `docs/RUNBOOK.md`
- [ ] Incident on-call rota set
- [ ] DR drill scheduled within 90 days

---

## 13. Reference

- **Source:** <https://github.com/oosadiaye/Quot-PSA>
- **Operational runbook:** [`docs/RUNBOOK.md`](RUNBOOK.md) — 14 incident scenarios
- **DR drill:** [`docs/DR_DRILL.md`](DR_DRILL.md) — 9-step restore
- **Tenant onboarding:** [`docs/RUNBOOK_ONBOARD_TENANT.md`](RUNBOOK_ONBOARD_TENANT.md)
- **Performance audit:** [`docs/PERFORMANCE_AUDIT.md`](PERFORMANCE_AUDIT.md)
- **Load test:** [`tests/load/README.md`](../tests/load/README.md)
- **API reference (live):** `https://<your-host>/api/docs/`
