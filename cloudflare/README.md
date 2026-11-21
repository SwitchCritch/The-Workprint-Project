# The Workprint Project — Cloudflare migration (STAGING ONLY)

This directory is an **isolated, read-only Flask / Python Workers smoke test**.
It is **not** a functional replacement for the Railway website yet.
The production Flask application at the repository root is deliberately unchanged.

## Why the original Cloudflare deploy failed

Cloudflare ran `npx wrangler deploy` from the repository root. The root
contains a traditional Flask + Gunicorn app, not a Wrangler Worker entrypoint
or automatically detectable static site. This preview provides a Python
Workers entrypoint and a dedicated Wrangler configuration.

Official Cloudflare reference:
https://developers.cloudflare.com/workers/languages/python/packages/flask/

## Current files

- `src/worker.py`: Flask WSGI Worker serving a disabled/read-only preview
  plus `/health`. Other routes return 404; no members or downloads.
- `wrangler.jsonc`: preview-only Worker name, Python compatibility flag,
  and static assets. D1/R2 examples are commented out.
- `public/`: tiny migration-status page, not the existing website UI.
- `schema.sql`: **schema only** copied from `app.py` as a starting point.
  No real records are included.
- `tools/export_sqlite.py`: local tool for a PRIVATE SQLite SQL dump.
- `pyproject.toml`: Python Worker dependencies. The production root
  `requirements.txt` is not used to deploy this preview.

## Run and test (separate staging environment)

Prerequisites: Node.js, uv and a Cloudflare account.

1. Check out the branch `cloudflare-migration` and change into `cloudflare/`.
2. Run `uv run pywrangler dev`.
3. Open http://localhost:8787/ and http://localhost:8787/health.
4. Confirm unknown routes, member registration, downloads and admin are
   unavailable. The preview does not use a real database.
5. Only if the local smoke test passes, run
   `uv run pywrangler deploy` to create the separately named preview Worker.
   Do **not** bind or redirect `theworkprintproject.com` yet.

Use `cloudflare/` as the **project root** for this Worker, NOT the repository
root. If wiring a GitHub-connected Cloudflare build, select branch
`cloudflare-migration`, root directory `cloudflare`, and use a deployment
process that provides `uv` and runs `uv run pywrangler deploy` from there.
The earlier `npx wrangler deploy` command at `/` remains unsuitable.

Deployment has NOT been run or verified by this change; this only prepares
the files in GitHub.

## Preserving the existing archive

The production code uses a Railway volume:
- `/data/workprints.db` — movies, articles, contact messages, members,
  download requests and other site state.
- `/data/uploads/` — uploaded posters, covers, screenshots.

**Never commit either folder, an exported SQL file, admin passwords, member
details, or any environment variable secrets to GitHub.**

Before any real migration:
1. Keep Railway running. Make a verified, private backup of
   `/data/workprints.db` AND the entire `/data/uploads/` folder.
2. Confirm table row counts, record totals, sample images and hashes
   from the source backup. Back up again just before cutover.
3. On a trusted machine, optionally export from a backup with:
   `python cloudflare/tools/export_sqlite.py /secure/backup/workprints.db /secure/backup/cloudflare-export.sql`
   (command is relative to repository root).
   **That SQL contains personal information and password hashes.**
   It is NOT ready to import into D1 without review and adaptation.
4. Create separate Cloudflare D1 **preview** database and R2 **preview**
   bucket. Insert their binding identifiers in `wrangler.jsonc` once
   provisioned; never bind production resources to the preview by mistake.
5. Convert and validate SQLite schema + data for D1, preserving IDs and
   foreign keys. Restore images to R2 while retaining the stored filenames.
6. Port the Flask `db()` calls to D1 (asynchronous bindings), image
   upload/read/delete to R2, session/cookie secrets, and rate limiting.
   `app.py` currently calls `init_db()` at import time and assumes a
   writable local SQLite filesystem, so importing it directly in a Worker
   is unsafe and will not work.
7. Test all routes end-to-end: public catalog, search, news, admin CRUD,
   file uploads, contact forms, member registration/login/logout, limits,
   Pixeldrain redirects and atomic quota enforcement under concurrent
   requests, backup/restore and errors.
8. Do a final production backup and delta transfer with writes frozen.
   Cut DNS/custom domain over **only after** comparing content, protecting
   member data, verifying HTTPS, and confirming a rollback plan.
9. Keep the Railway instance and original backups until the new service
   has been checked in production.

### Critical transactional/security considerations

- D1 supports SQL but is **not a drop-in synchronous Python sqlite3 file**.
  Replacing the SQLite connection requires a separate persistence layer.
- The existing download quota uses `BEGIN IMMEDIATE` to prevent race
  conditions. Replacing it with independent D1 queries would create a
  concurrency vulnerability. Preserve atomic enforcement and test it.
- Password hashes must remain intact and usable; all member and admin
  flows need functional testing before enabling.
- Uploaded files are not durable on a Worker filesystem. Use R2/KV as
  appropriate, not `/data/uploads`.
- `SECRET_KEY`, `ADMIN_PASSWORD`/`ADMIN_PASSWORD_HASH` and other
  settings belong in Cloudflare Secrets, not source control.
- The schema includes sensitive tables. Don't use a real production
  SQL export as test data in a public preview.

## Rollback and deployment status

Nothing here modifies the live Railway app or the `main` branch.
No Cloudflare deployment, data export/import, domain update or
production cutover has been performed. Further development is required
before real migration.
