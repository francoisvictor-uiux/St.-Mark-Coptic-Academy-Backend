# Deploying the backend to cPanel (api.smcacademy.org)

cPanel runs Python apps under **Passenger**. You point it at the app folder and a
startup file (`passenger_wsgi.py`), it builds a virtualenv, you `pip install`, run
migrations, collect static, and restart. There is no `runserver` in production.

App root on the server: `/home/smca/api.smcacademy.org`

---

## 0. Pre-flight (verify once)

1. **Python version** — This host tops out at **Python 3.11.15**, so the project
   runs **Django 5.2 LTS** (security-supported to April 2028; requires Python
   3.10+). Select **3.11.15** in Setup Python App. (Django 6.0 would need 3.12+,
   which this host does not offer.)
2. **PostgreSQL** — In cPanel **Databases → PostgreSQL Databases**, confirm the
   `stmark` database and `stmark_app` user exist and the user is added to the DB
   with all privileges. (Your `.env` already points at it.) If your host has no
   PostgreSQL, tell me — we switch `DATABASE_URL` to MySQL or SQLite instead.
3. **SSL** — The subdomain `api.smcacademy.org` must have a valid SSL cert
   (cPanel → SSL/TLS Status → run AutoSSL). Prod forces HTTPS redirects.

## 1. Upload the code

You've already uploaded and extracted `backend.zip` into the app root. Make sure
these new files are present there (re-upload if you extracted before this change):
`passenger_wsgi.py`, updated `requirements.txt`, `config/settings/base.py`,
`config/settings/prod.py`.

Delete `backend.zip` and `db.sqlite3` from the server after extraction — prod uses
PostgreSQL, and a stray SQLite file is just confusion.

## 2. Create the production .env on the server

Copy `.env.prod.example` to `.env` in the app root and fill in the real values
(secret key, DB password, mailbox password). Use cPanel File Manager → Edit.
Critical: `DJANGO_ALLOWED_HOSTS=api.smcacademy.org` and the correct `DATABASE_URL`.

## 3. Setup Python App (cPanel UI)

cPanel → **Setup Python App → Create Application**:

- **Python version:** 3.11.15 (see pre-flight)
- **Application root:** `api.smcacademy.org`
- **Application URL:** `api.smcacademy.org` (leave the path blank)
- **Application startup file:** `passenger_wsgi.py`
- **Application Entry point:** `application`

Click **Create**. cPanel builds a virtualenv and shows the command to enter it,
e.g. `source /home/smca/virtualenv/api.smcacademy.org/3.11/bin/activate`.

## 4. Install dependencies + initialize

Open cPanel → **Terminal** (or the SSH), then run — activate the venv first using
the exact command cPanel showed you in step 3:

```bash
source /home/smca/virtualenv/api.smcacademy.org/3.11/bin/activate
cd /home/smca/api.smcacademy.org

pip install --upgrade pip
pip install -r requirements.txt

# Sanity check: prod settings load and DB connects
DJANGO_ENV=prod python manage.py check --deploy

DJANGO_ENV=prod python manage.py migrate
DJANGO_ENV=prod python manage.py collectstatic --noinput
DJANGO_ENV=prod python manage.py createsuperuser
```

If your host's Terminal is disabled, use the **"Run Pip Install"** button in Setup
Python App for requirements, and the **"Execute python script"** field for
`manage.py migrate` / `collectstatic` (set `DJANGO_ENV=prod` in the app's
Environment variables section first — see step 5).

## 5. Environment variable in the Python App UI (belt & suspenders)

In Setup Python App, under **Environment variables**, add:
`DJANGO_ENV = prod`. (Passenger also sets this via `passenger_wsgi.py`, but the UI
value makes the `manage.py` buttons use prod too.)

## 6. Restart & verify

Click **Restart** in Setup Python App, then:

- Health check: `https://api.smcacademy.org/api/v1/health` → `{"status":"ok","database":"connected"}`
- API docs: `https://api.smcacademy.org/api/v1/docs`
- Admin: `https://api.smcacademy.org/<DJANGO_ADMIN_PATH>` (the value from `.env`)

## 7. Media files

User uploads live in `/home/smca/api.smcacademy.org/media/` and are served
directly by LiteSpeed because the app root is the subdomain's document root
(request `/media/x.jpg` → physical file → served without hitting Passenger).
Confirm an uploaded image URL loads. If it 404s on your host, tell me and I'll add
an explicit media route.

---

## Redeploying after code changes

```bash
source /home/smca/virtualenv/api.smcacademy.org/3.11/bin/activate
cd /home/smca/api.smcacademy.org
pip install -r requirements.txt          # only if requirements changed
DJANGO_ENV=prod python manage.py migrate
DJANGO_ENV=prod python manage.py collectstatic --noinput
# then click Restart in Setup Python App (or: touch tmp/restart.txt)
```

## Common failures

- **400 Bad Request** → `DJANGO_ALLOWED_HOSTS` doesn't include `api.smcacademy.org`.
- **500 on every page, "DJANGO_SECRET_KEY must be set"** → `.env` missing/secret is the dev key.
- **Infinite HTTPS redirect** → SSL not active on the subdomain (run AutoSSL).
- **CSS-less admin / broken Swagger** → `collectstatic` didn't run, or WhiteNoise not installed.
- **DB connection refused** → PostgreSQL not created, or `DATABASE_URL` host/port/password wrong.
- **App won't boot, ImportError** → wrong Python selected (need 3.11.15), or `pip install -r requirements.txt` not run in the venv.
