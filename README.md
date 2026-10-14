# The Workprint Project

A dark, cinematic movie workprint catalogue website, built with Flask and SQLite.

## Features
- Public, searchable movie collection with poster cards, genre and year filters
- Individual workprint pages documenting versions and differences from the official cut
- Technical information: file size, format, resolution, audio, runtime and source
- Optional external download link for **material you have permission to distribute**
- Upload a poster and multiple screenshots
- Password-protected admin area to add, edit, unpublish and delete entries
- Responsive layout for mobile and desktop
- Persistent SQLite database + uploaded image files

## Run locally (Windows)
Install Python 3.11 or newer, then in a terminal in this folder:

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
$env:ADMIN_PASSWORD = "replace-with-a-long-unique-password"
$env:SECRET_KEY = "replace-with-a-long-random-secret"
python app.py
```
Open http://localhost:8080. Select **Admin**, log in, then **+ Add workprint**.

## Host on Railway
1. Unzip this project into a GitHub repository.
2. In Railway select **New Project → Deploy from GitHub repo** and choose the repo.
3. Under **Variables**, add:
   - `ADMIN_PASSWORD` — your private long, unique administrator password. Do not share it.
   - `SECRET_KEY` — a separate random string, ideally 64+ characters. Keep it stable across redeployments.
   - `DATA_DIR` — `/data`
4. Under the Railway service's **Volumes**, add a persistent volume mounted at **`/data`**. **Do this before adding entries**, or redeployment may wipe the SQLite database and uploaded images.
5. Deploy and use Railway's generated public domain in **Settings → Networking**.
6. Open `/login` to sign in and add your first entry.

Railway can change its interface; the exact menu labels may vary.

## Image uploads and download links
- Screenshots and posters are hosted on your site's volume.
- The site does **not** host or transfer film video files. An optional external HTTP/HTTPS link can be entered per film.
- Only include links to media you're authorised to share; an existing copy online doesn't establish redistribution rights.
- Forms are CSRF-protected and user-uploaded pictures are checked for file signature and extension.

## Data backups
Back up `/data/workprints.db` and `/data/uploads/` regularly from your hosting volume.

## Notes
- No sample copyrighted movies or movie files are included.
- This is a single-admin application, not a multi-user account system.
- The external download destination is controlled by you; always review it before publishing.
