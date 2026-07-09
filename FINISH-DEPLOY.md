# Finish the deploy — final steps

## Done ✅ (verified on the server)
- Host Python ceiling is **3.11.15**; project downgraded Django 6.0 → **5.2 LTS**.
- cPanel Python app created (root `api.smcacademy.org`, Python 3.11.15, startup
  `passenger_wsgi.py`, entry `application`, env `DJANGO_ENV=prod`).
- Verified code uploaded/extracted to `/home/smca/api.smcacademy.org`.
- **Dependencies installed** and confirmed: `manage.py check` → *0 issues*.
- PostgreSQL **database `smca_stmark` created**.
- `.env` uploaded to the app root with placeholders for the 3 secrets.

## What only YOU can do (I don't handle passwords)

### A. Create the PostgreSQL user + grant it the database
cPanel → **PostgreSQL Databases**:
1. Under **PostgreSQL Users → Add New User**: username `stmark_app` (becomes
   `smca_stmark_app`). Password — use this generated one (or your own):
   `R2K6r3nv8O0VEMrQiqOG9xQ95tfI`
2. Under **Add User To Database**: add `smca_stmark_app` to `smca_stmark`, then on the
   privileges screen check **ALL PRIVILEGES**.

### B. Fill the 3 secrets in `.env`
File Manager → `/home/smca/api.smcacademy.org` → select `.env` → **Edit**. Replace:
- `__PASTE_SECRET_KEY_HERE__` →
  `fXn!zaR-EfUz9jNNVN@8^C&#x$Qw1LwLQM-OR%jcWwg-7kpW-F(Kdu$3!O6=(4vC`
- `__PASTE_DB_PASSWORD_HERE__` → the DB password from step A
  (`R2K6r3nv8O0VEMrQiqOG9xQ95tfI` if you used the generated one)
- `__PASTE_MAILBOX_PASSWORD_HERE__` → the mailbox password for `info@smcacademy.org`
Save.

**After A + B, tell me — I'll run the migrations, collect static, and verify.**

## What I'll run once A + B are done (Setup Python App → Execute python script)
- `manage.py migrate`
- `manage.py collectstatic --noinput`

### C. Create the admin user (your password)
Setup Python App → add temp env vars, then run the script:
- `DJANGO_SUPERUSER_EMAIL` = your email
- `DJANGO_SUPERUSER_USERNAME` = your email (this project logs in by email)
- `DJANGO_SUPERUSER_PASSWORD` = a strong password *(you set this)*
- run `manage.py createsuperuser --noinput`
- then delete `DJANGO_SUPERUSER_PASSWORD` from the env vars.

### D. Restart + verify (I can do this)
Setup Python App → **Restart**, then:
- `https://api.smcacademy.org/api/v1/health` → `{"status":"ok","database":"connected"}`
- `https://api.smcacademy.org/api/v1/docs`
- Admin: `https://api.smcacademy.org/smca-control-9f3b/`

## Cleanup (optional)
Delete `backend.zip`, `deploy_backend.zip`, `db.sqlite3` from the app root.
