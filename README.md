# The Workprint Project — Classic Retro VHS (mockup match)

This is a functional Flask/SQLite website rebuild based on the **first Classic Retro VHS screenshot** you supplied. The hero uses a bundled cropped image from that screenshot to preserve the exact video-store shelves, projector logo, wall posters and neon sign. The navigation bar, eight category tabs, movie poster links, search filters, detail pages and admin forms are functioning HTML—not part of a static website screenshot.

## How the first screenshot translates into the real site

- **Header**: uses the genuine selected artwork. It also includes the large centred blue/orange projector logo as shown. The design-label caption appearing at the upper left is part of your original concept screenshot, not a separate website heading.
- **Navigation**: working links right below the header image.
- **Categories**: All, Workprint, Alternate Version, CAM, 35mm, Screener, VHS, Betamax, Laserdisc; each is clickable.
- **Latest additions**: automatically displays YOUR saved films and poster uploads from the existing database. The mockup's five movie posters are not inserted as fictional archive records. The preview image supplied separately shows five reference cards to demonstrate the layout.
- **Mobile**: uses your original transparent logo over a darkened store scene to stay legible.

## Upload files to GitHub

1. Extract this ZIP.
2. Upload the project contents (`app.py`, `Procfile`, `railway.json`, `requirements.txt`, `static/`, `templates/`) to the **root** of your existing GitHub repository, replacing the matching old files.
3. Commit and let Railway deploy.
4. Do **not** upload film files or SQLite databases as part of website source updates.
5. Your own uploaded posters automatically appear on their movie cards when the Railway volume is attached.

## Persist the movie collection on Railway

- Keep the same persistent **Railway volume mounted at `/data`**.
- Keep **`DATA_DIR=/data`**, `ADMIN_PASSWORD`, and a stable `SECRET_KEY` in Railway variables.
- `workprints.db` and `uploads/` both live under `/data`. Do not overwrite or detach the existing volume.
- Back up `/data/workprints.db` and `/data/uploads` regularly.
- If the films previously disappeared after redeployments, verify that the existing volume is still attached to the deployed service. Code updates cannot restore data already erased from ephemeral disk.

## Features

Existing SQLite movie records and migrations are preserved. Admin can add/edit/delete films, upload posters and screenshots, enter synopsis, differences, notes, file size/format/resolution/source and Pixeldrain single-file links. Film pages provide an external download link for material you are authorised to share. The website itself does not store video files.

## Local test

```bash
pip install -r requirements.txt
export ADMIN_PASSWORD='choose-a-unique-password'
export SECRET_KEY='choose-a-long-random-secret'
python app.py
```

Then open http://127.0.0.1:8080 . To test the layout without adding real movie records, see `preview-layout.png`, which is a *visual preview*, not the live catalogue.
