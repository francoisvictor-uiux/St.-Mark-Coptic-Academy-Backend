# Backend auto-deploy from GitHub (cPanel Git™ Version Control)

The GitHub repo `St.-Mark-Coptic-Academy-Backend` (`main`) is the source of truth.
This host has **no SSH/webhook**, so there is no instant push-to-live. Instead we use
cPanel **Git Version Control** (clones the repo without shell) + `.cpanel.yml`, in two
modes that are already wired in the repo:

- **One-click:** cPanel → Git Version Control → *Update from Remote* → *Deploy HEAD Commit*.
- **Near-automatic:** a cron job (`scripts/cpanel-deploy.sh`) pulls & deploys every ~5 min.

Both run the same steps: sync code into the live app root, `pip install`, `migrate`,
`collectstatic`, restart Passenger. App root: `/home/smca/api.smcacademy.org`.

> Prerequisite: cPanel must show **Git Version Control** (it's how the clone is created
> without SSH). If it's missing, ask the host to enable it — the cron mode needs the clone too.

---

## 1. Create the repository in cPanel (one time)

cPanel → **Git™ Version Control** → **Create**:
- **Clone a Repository:** toggle **ON**.
- **Clone URL:** `https://github.com/francoisvictor-uiux/St.-Mark-Coptic-Academy-Backend.git`
  (public repo — no credentials needed).
- **Repository Path:** `/home/smca/repositories/backend`  ← remember this; the cron uses it.
- **Repository Name:** `backend`.
- **Create.** cPanel clones `main`.

## 2. First deploy (one-click)

cPanel → Git Version Control → **Manage** (on the `backend` repo) → **Pull or Deploy** tab:
- **Update from Remote** (pulls latest `main`).
- **Deploy HEAD Commit** (runs `.cpanel.yml`).

Watch the deploy log, then verify:
`https://api.smcacademy.org/api/v1/health` → `{"status":"ok","database":"connected"}`

> The very first deploy is essentially a no-op for code (the server already runs this
> code) plus migrate/collectstatic/restart. Do it at a quiet time and confirm health.

## 3. Turn on the cron (near-automatic)

cPanel → **Cron Jobs** → Add New Cron Job:
- **Common Settings:** *Once Per Five Minutes* (`*/5 * * * *`).
- **Command:**
  ```
  /home/smca/repositories/backend/scripts/cpanel-deploy.sh >> /home/smca/deploy-backend.log 2>&1
  ```
  (match the path to your Repository Path from step 1).

The script exits instantly when `origin/main` hasn't moved, and only does the full
deploy when there are new commits. Check `/home/smca/deploy-backend.log` for history.

If the log shows `git: command not found`, prefix the cron command with the host's git
path, e.g. `PATH=/usr/local/cpanel/3rdparty/bin:$PATH` before the script.

---

## Day-to-day: how to ship a backend change

1. Edit code locally on `main`.
2. `git push origin main`.
3. Either wait ≤5 min for the cron, **or** click *Update from Remote* → *Deploy* for instant.

No more File Manager re-uploads. The deploy preserves server-only files that are not in
git: `.env`, `media/`, `staticfiles/`, `tmp/`, and the Passenger `.htaccess`.

## Safety notes

- Deploys run migrations against the **live** DB automatically. Review migrations before
  pushing. To pause automation, disable the cron job; the one-click button still works.
- The sync is an **overlay** (no `rsync --delete`) so it never removes uploads/secrets.
  A file deleted from the repo stays on the server until manually removed.
- If a deploy fails mid-way (e.g. a bad migration), the cron/`.cpanel.yml` stops before
  the restart; check the log, fix forward, and push again.
