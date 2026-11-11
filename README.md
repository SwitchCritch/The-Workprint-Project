# THE WORKPRINT PROJECT — Modern Database Dashboard

A Flask + SQLite film archive with a news-first homepage, searchable sortable library, format categories, contact inbox and optional donations.

## What is in this GitHub ZIP?

- `app.py` — Flask backend, database, admin login and persistent file uploads
- `templates/base.html` — centred transparent Workprint Project logo on a plain dark header and working navigation
- `templates/home.html` — latest articles, coming-soon news and recent film additions
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

- The old homepage statistics cards have been removed. The homepage now showcases admin-published news stories.
- Latest additions and Recent Uploads use the existing movies and poster images in the database.
- Browse, order and format filters use server-side SQL querying. Random entry selects a real published film.
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

## Newsroom, browse, categories, donation, and contact update (5 November 2026)

The former four-number statistics panel has been removed. The homepage `/` is now a news feed. Admins can write rich-text news articles with cover pictures, choose **News** or **Coming Soon**, save drafts, edit and delete at `/admin/news/new` and the article edit screen. News and visitor messages are saved in the same persistent SQLite database under `/data`, with additive tables only; existing films, uploads, screenshots, and Pixeldrain links are retained.

**Browse** is now `/browse` and offers search, category and genre filters, movie-year filter and order controls (newest/oldest, A–Z/Z–A, movie year newest/oldest, last updated). The **Categories** page is `/categories`, with clickable format cards for Workprint, CAM, 35mm, Screener, VHS, Betamax, and Laserdisc. Each category links to a prefiltered browse page.

**Contact Us** is `/contact`. Messages save to the private admin inbox at `/admin/messages` rather than being emailed. The contact form validates required fields, uses a CSRF token, a hidden spam field and a per-IP limit. Admins can reply through their own mail software via the sender's email link and mark messages read/delete messages. **Configure backups** for the inbox because it lives in the existing SQLite database.

**Donation** goes to `/donate`. To enable donations, create a hosted payment/donation page with a provider of your choice and set the Railway service variable `DONATION_URL` to its full `https://` URL. If not configured, the site shows a friendly “not set up” page. No card data or payments are processed by this site.

**Upgrade**: Back up your mounted `/data` folder, extract the ZIP, replace GitHub repository files and redeploy without changing or deleting the existing Railway volume. Maintain `DATA_DIR=/data`, `ADMIN_PASSWORD` or `ADMIN_PASSWORD_HASH`, and `SECRET_KEY`. Do not put your private database, API keys or passwords into GitHub.


## Google Search Console / Sitemap

The sitemap is generated dynamically at **https://theworkprintproject.com/sitemap.xml**. It includes public pages, published film entries, published news articles, and category searches; unpublished drafts are excluded. The site also provides **/robots.txt**. You do not need to upload a static sitemap manually.

If you change domain, set `SITE_URL=https://your-new-domain.com` in Railway (HTTPS, no trailing slash).

To submit it, redeploy your GitHub files, open the sitemap URL in a browser, then in Google Search Console → Sitemaps enter `sitemap.xml` and select Submit. Search engines can take time to index pages.

**Note:** This update does not alter the database schema or delete saved films, screenshots, articles, or messages. Keep your existing Railway volume and `DATA_DIR=/data`.

## Member accounts & download request limits (new)

The public film library remains browsable. Visitors must **register / sign in** to request an external download link. `Members Login`, `Sign Up` and `My Account` appear in the navigation. The admin-only `MEMBERS` navigation item opens **Admin → Members** to search users, see the request log, suspend/reactivate accounts and override individual quotas.

### Railway settings

- Keep the **existing persistent volume mounted at `/data`** and `DATA_DIR=/data`. All movie records, screenshots, news, members and request logs share the same `workprints.db` file. **Back up your live `/data/workprints.db` and `/data/uploads` before deploying**. The upgrade creates two new tables and indexes without dropping existing content.
- Set a **strong, permanent `SECRET_KEY`** and keep your existing `ADMIN_PASSWORD` or `ADMIN_PASSWORD_HASH`.
- Optional: `DAILY_DOWNLOAD_LIMIT=3` (integer 1–50). The default is three download-link requests per account per calendar day in the `Europe/London` time zone. Changing this setting requires a redeploy; individual limits are editable in Admin → Members.
- You **must have working HTTPS with a valid certificate before accepting registrations**. Fix Chrome's **Not secure** warning before making the site public.

### Download link behaviour and limits

- A signed-in member clicks **REQUEST DOWNLOAD** on a published film. A CSRF-protected POST transaction checks the account's suspended status and its remaining daily quota, records the film title and timestamp, and redirects to the configured Pixeldrain URL (or fallback external link).
- Admin sees **download requests**, not proof of completed file transfers. If a user clicks again, it counts again. Records are stored in the persistent SQLite database and are not wiped at midnight; only the quota counter starts afresh on the next UK calendar day.
- The new site no longer renders direct Pixeldrain links to anonymous users. **It cannot revoke or block reuse of a Pixeldrain URL once someone obtains it**, nor can it control downloads outside the site. For strict file-level limits, you would need a private storage service with expiring signed links and server-side file delivery.
- Registration uses hashed passwords and simple IP-based sign-in throttling. **Email verification, automatic password reset email, CAPTCHA, and email notifications are not yet included**, since they need an email/CAPTCHA service and suitable configuration. Users can contact you to request account help. Consider adding these before broad public promotion.
- This website handles member data (email addresses and download request history). Publish an appropriate privacy notice and provide a way to request data access/deletion before public sign-ups; collect only data you need.
- Only share downloadable content you are authorised to distribute.


## New: YouTube embeds inside news articles

In Admin → News → Add/Edit, click the desired location in **Article content** and use **▶ Insert YouTube Video**. Paste a standard YouTube watch, share, Shorts, Live, or embed URL. The editor inserts a movable video placeholder at that point in the article; you may type above/below it, or click the placeholder to replace/remove it. Save the article and a responsive privacy-enhanced YouTube iframe will play **in that position** on the public article page. YouTube may display ads or block embeds for videos whose owners disallow embedding. No new database columns or environment variables are needed.

For safety, raw custom iframe HTML is not accepted. Only valid 11-character YouTube video IDs produce an iframe. The public embed loads content from youtube-nocookie.com. The article editor preserves existing article HTML.
