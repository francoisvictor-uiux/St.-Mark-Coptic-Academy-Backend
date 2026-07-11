# Backend auto-deploy from GitHub (cPanel, no SSH)

The GitHub repo `St.-Mark-Coptic-Academy-Backend` (`main`) is the source of truth.
This host has **no SSH/webhook and no working server shell**, so there is no instant
push-to-live. A **cron job** gives near-automatic deploys (live within ~5 min of a push).

> **What actually works here:** cPanel's built-in one-click *Deploy HEAD Commit* does
> **NOT** run on this account — it needs a server shell (disabled), so it queues but never
> executes and leaves an empty deploy log. The **cron job below is the real mechanism.**
> cPanel **Git Version Control** is only used once, to place the clone on the server; after
> that you can even remove it from the Git UI — the deploy works off the on-disk folder.

The cron runs `scripts/cpanel-deploy.sh`, which pulls `main` and (only when there are new
commits) syncs code into the live app root, `pip install`s, `migrate`s, `collectstatic`s,
and restarts Passenger. App root: `/home/smca/api.smcacademy.org`.

---

## 1. Put a clone on the server (one time)

cPanel → **Git™ Version Control** → **Create** → *Clone a Repository*:
- **Clone URL:** `https://github.com/francoisvictor-uiux/St.-Mark-Coptic-Academy-Backend.git`
  (public repo — no credentials needed).
- Let cPanel choose the path. It derives it from the repo name:
  **`/home/smca/repositories/St.-Mark-Coptic-Academy-Backend`** ← this exact path is what the cron uses.
- **Create.** cPanel clones `main` (folder includes `.git`, so the cron can pull).

You do **not** need to touch *Update from Remote* / *Deploy HEAD Commit* — the cron pulls itself.

## 2. Add the cron job (this is the deploy engine)

cPanel → **Cron Jobs** → Add New Cron Job:
- **Common Settings:** *Once Per Five Minutes* (`*/5 * * * *`).
- **Command** (exact — note the real repo path and the `/bin/bash` prefix):
  ```
  /bin/bash /home/smca/repositories/St.-Mark-Coptic-Academy-Backend/scripts/cpanel-deploy.sh >> /home/smca/deploy-backend.log 2>&1
  ```

The script exits instantly when `origin/main` hasn't moved, and does the full deploy only
when there are new commits. History/log: **`/home/smca/deploy-backend.log`**.

## 3. Verify

After a deploy, `/home/smca/deploy-backend.log` shows `deploying <old> -> <new>` … `deploy
complete`, and `https://api.smcacademy.org/api/v1/health` → `{"status":"ok","database":"connected"}`.

---

## Day-to-day: how to ship a backend change

1. Edit code locally on `main`.
2. `git push origin main`.
3. Wait ≤5 min — the cron pulls & deploys automatically. No cPanel, no File Manager.

The deploy preserves server-only files that are not in git: `.env`, `media/`,
`staticfiles/`, `tmp/`, and the Passenger `.htaccess`.

## Safety notes

- Deploys run migrations against the **live** DB automatically. Review migrations before
  pushing. To pause automation, disable the cron job in cPanel → Cron Jobs.
- The sync is an **overlay** (no `rsync --delete`) so it never removes uploads/secrets.
  A file deleted from the repo stays on the server until manually removed.
- If a deploy fails mid-way (e.g. a bad migration), the script stops before the restart;
  check `deploy-backend.log`, fix forward, and push again.
- The clone folder must keep its `.git` and an `origin` remote pointing at the GitHub repo
  (a fresh cPanel clone has both). If it's ever lost, re-clone via Git Version Control.
