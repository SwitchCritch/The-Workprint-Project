# THE WORKPRINT PROJECT — Modern Database Dashboard

A functional Flask + SQLite film archive redesigned to match the **Modern Database Dashboard** reference selected on 30 October 2026.

## What is in this GitHub ZIP?

- `app.py` — Flask backend, database, admin login and persistent file uploads
- `templates/base.html` — centred transparent Workprint Project logo on a plain dark header and working navigation
- `templates/home.html` — statistics, film filters, dashboard sidebars, real latest additions and search
- `templates/detail.html` — movie metadata, artwork, screenshots, comparisons, external download links
- `templates/form.html` — add/edit films and screenshots; preserve existing metadata fields
- `templates/login.html` — password-protected admin sign-in
- `static/style.css` — responsive dark blue/cyan dashboard styling
- `static/workprint-logo.png` — your original transparent projector logo, used in the header at every screen size
- `static/favicon.svg`, `Procfile`, `railway.json`, `requirements.txt`, `.gitignore`

The dashboard contains real, working links and controls — not a screenshot used as an unclickable webpage. The old photographic video-store header has been removed entirely; only your transparent logo appears above the navigation. Movie posters, upload counts and information are drawn from your own data, **not fabricated sample records**.

## Categories

**Workprint, CAM, 35mm, Screener, VHS, Betamax and Laserdisc**.

**Alternate Version has been removed** from the add/edit form, category bar and filtering. To preserve older entries without keeping a removed category, the app migrates records previously marked `Alternate Version` to `Workprint` on first startup. Review and recategorise any such films using Edit. This changes only their category; titles, notes, posters, screenshots and download URLs remain intact.

## Install / update on GitHub and Railway

1. **Back up** your Railway database and uploaded images (`/data/workprints.db` and `/data/uploads/`) before updating.
2. Extract this ZIP; upload its *contents* into the **root** of your existing GitHub repo. Replace prior `app.py`, `templates`, and `static` files. Older unused header assets can be removed from the repository.
3. Keep the **same attached Railway volume** and mount it at `/data` (do not remove/recreate the old volume).
4. Check Railway service variables: `DATA_DIR=/data`, `ADMIN_PASSWORD=<your password>` or `ADMIN_PASSWORD_HASH=<your hash>`, and a persistent long `SECRET_KEY`.
5. Commit; Railway redeploys the service. Do not upload any database or film files into GitHub.

The app uses `/data` automatically if that directory is present, but **you still must attach a Railway persistent volume and set `DATA_DIR=/data`**. Updates to GitHub should not be allowed to replace your saved content. If a database was previously stored only on an ephemeral filesystem, this update cannot magically recover lost files.

## How archive features work

- The top cards show **published film count, number of occupied categories, screenshot count and number of newly added films in the current year**. They are not hardcoded mockup numbers.
- Latest additions and Recent Uploads use the existing movies and poster images in the database.
- Search and format tabs use server-side query filtering. Random entry selects a real published film.
- Add/edit forms preserve details on differences from the official release, notes, file format, size, resolution, runtime and source information.
- Pixeldrain supports individual public `https://pixeldrain.com/u/FILE_ID` links; on each film page, the direct download button uses the Pixeldrain file API `?download` endpoint. Limits and availability are managed by Pixeldrain. Only link to files you have the right to distribute.
- Existing admin login, upload validation, screenshot management, editing and deleting remain in place.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate       # On Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
export ADMIN_PASSWORD='replace-this-with-your-own-password'
export SECRET_KEY='replace-this-with-a-long-random-key'
python app.py
```

Then open `http://127.0.0.1:8080/`. The local instance uses `./data` if `DATA_DIR` isn't specified.

## Testing note

The package's Python was syntax checked, all Jinja templates were compiled, and desktop/mobile visual layouts were rendered in a headless browser using illustrative data. The QA poster artwork was **not** packaged as a real film collection. This environment did not have a usable Flask installation for a complete local backend integration test or a live Railway deployment.

## Logo-only header update (30 October 2026)

The illustrated VHS shelves, posters and neon signage in the previous header have been removed. The header now displays only `static/workprint-logo.png`, centred on a plain dark background above the navigation. The former `static/dashboard-hero.webp` is intentionally omitted. All database, forms, Pixeldrain and Railway volume code is unchanged.


## Film page layout and formatted comparisons (30 October 2026)

- Film detail pages and add/edit forms are now centred with responsive maximum widths. The poster sits next to the title and technical details on desktop, and stacks neatly on mobile.
- The **Differences from the official release** field is a WYSIWYG editor with bold, italic, underline, headings, bullet and numbered lists, links, and clear formatting. Click Edit entry on any film to use it. The field updates on Save.
- Rich text is sanitised with `bleach` on save and on display. HTML scripts, styles and unsafe link protocols are stripped. Existing plain-text comparison notes continue to display as paragraphs and remain editable.
- An additive database migration introduces `differences_is_html`, defaulting to 0. Existing film records, screenshots and Pixeldrain links remain untouched.
- The new `static/rich-editor.js` is local and needs no external editor CDN; the browser requires JavaScript to interact with the formatting buttons.
- **Keep your existing Railway volume mounted at `/data` and `DATA_DIR=/data`, and back up the volume before deploying.**
