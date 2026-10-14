import os
import re
import sqlite3
import secrets
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse
from flask import Flask, abort, flash, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE = Path(__file__).resolve().parent
DATA = Path(os.getenv('DATA_DIR', str(BASE / 'data')))
UPLOADS = DATA / 'uploads'
DATA.mkdir(parents=True, exist_ok=True)
UPLOADS.mkdir(parents=True, exist_ok=True)
DB = DATA / 'workprints.db'
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '')
ADMIN_PASSWORD_HASH = os.getenv('ADMIN_PASSWORD_HASH', '')
ALLOWED_EXT = {'jpg', 'jpeg', 'png', 'webp', 'gif'}


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    return con


def init_db():
    with db() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, release_year INTEGER, workprint_date TEXT,
            genre TEXT, director TEXT, runtime TEXT, official_runtime TEXT,
            synopsis TEXT, differences TEXT, notes TEXT, source_details TEXT,
            file_size TEXT, file_format TEXT, video_resolution TEXT,
            audio_details TEXT, download_url TEXT, poster TEXT,
            published INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS screenshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
            filename TEXT NOT NULL, caption TEXT NOT NULL DEFAULT ''
        );
        ''')


init_db()


def admin_ok():
    return session.get('admin') is True


def protected(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not admin_ok():
            return redirect(url_for('login', next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def csrf():
    if not session.get('csrf'):
        session['csrf'] = secrets.token_urlsafe(32)
    return session['csrf']


@app.context_processor
def common():
    return {'is_admin': admin_ok(), 'csrf_token': csrf()}


def validate_csrf():
    if not secrets.compare_digest(request.form.get('csrf_token', ''), csrf()):
        abort(400, 'Invalid form token')


def image_save(file):
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXT:
        raise ValueError('Images must be JPG, PNG, WEBP or GIF.')
    header = file.stream.read(16)
    file.stream.seek(0)
    is_valid = ((ext in ('jpg', 'jpeg') and header.startswith(b'\xff\xd8\xff')) or
                (ext == 'png' and header.startswith(b'\x89PNG\r\n\x1a\n')) or
                (ext == 'webp' and header[0:4] == b'RIFF' and header[8:12] == b'WEBP') or
                (ext == 'gif' and header.startswith((b'GIF87a', b'GIF89a'))))
    if not is_valid:
        raise ValueError('The file does not appear to be a valid image.')
    filename = f'{secrets.token_hex(16)}.{ext}'
    file.save(UPLOADS / filename)
    return filename


def fetch_movie(mid, include_unpublished=False):
    with db() as con:
        movie = con.execute('SELECT * FROM movies WHERE id=?', (mid,)).fetchone()
    if not movie or (not movie['published'] and not include_unpublished):
        abort(404)
    return movie


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/')
def home():
    q = request.args.get('q', '').strip()
    genre = request.args.get('genre', '').strip()
    year = request.args.get('year', '').strip()
    sql = 'SELECT * FROM movies WHERE 1=1'
    vals = []
    if not admin_ok():
        sql += ' AND published=1'
    if q:
        sql += ' AND (title LIKE ? OR synopsis LIKE ? OR differences LIKE ?)'
        vals += [f'%{q}%'] * 3
    if genre:
        sql += ' AND genre=?'
        vals.append(genre)
    if year.isdigit():
        sql += ' AND release_year=?'
        vals.append(int(year))
    sql += ' ORDER BY created_at DESC, id DESC'
    with db() as con:
        movies = con.execute(sql, vals).fetchall()
        genres = [x[0] for x in con.execute("SELECT DISTINCT genre FROM movies WHERE genre != '' AND genre IS NOT NULL ORDER BY genre").fetchall()]
        count = con.execute('SELECT COUNT(*) FROM movies WHERE published=1').fetchone()[0]
        screenshots = con.execute('SELECT COUNT(*) FROM screenshots').fetchone()[0]
    return render_template('home.html', movies=movies, q=q, genre=genre, year=year, genres=genres, count=count, screenshots=screenshots)


@app.get('/workprint/<int:mid>')
def detail(mid):
    movie = fetch_movie(mid, admin_ok())
    with db() as con:
        pics = con.execute('SELECT * FROM screenshots WHERE movie_id=? ORDER BY id', (mid,)).fetchall()
    return render_template('detail.html', movie=movie, pics=pics)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        validate_csrf()
        candidate = request.form.get('password', '')
        valid = (check_password_hash(ADMIN_PASSWORD_HASH, candidate) if ADMIN_PASSWORD_HASH else bool(ADMIN_PASSWORD) and secrets.compare_digest(candidate, ADMIN_PASSWORD))
        if valid:
            session.clear()
            session['admin'] = True
            session['csrf'] = secrets.token_urlsafe(32)
            return redirect(url_for('home'))
        flash('Incorrect admin password.', 'error')
    return render_template('login.html', configured=bool(ADMIN_PASSWORD or ADMIN_PASSWORD_HASH))


@app.post('/logout')
@protected
def logout():
    validate_csrf()
    session.clear()
    return redirect(url_for('home'))


FIELDS = ['title', 'release_year', 'workprint_date', 'genre', 'director', 'runtime', 'official_runtime',
          'synopsis', 'differences', 'notes', 'source_details', 'file_size', 'file_format',
          'video_resolution', 'audio_details', 'download_url']


def get_fields():
    data = {name: request.form.get(name, '').strip() for name in FIELDS}
    if not data['title']:
        raise ValueError('Movie title is required.')
    if data['release_year']:
        if not re.fullmatch(r'\d{4}', data['release_year']):
            raise ValueError('Release year must be four digits.')
        data['release_year'] = int(data['release_year'])
    else:
        data['release_year'] = None
    link = data['download_url']
    if link:
        p = urlparse(link)
        if p.scheme not in ('http', 'https') or not p.netloc or p.username or p.password:
            raise ValueError('Download link must be a valid HTTP(S) URL.')
    data['published'] = int(request.form.get('published') == 'on')
    return data


@app.route('/admin/new', methods=['GET', 'POST'])
@protected
def add():
    if request.method == 'POST':
        validate_csrf()
        try:
            data = get_fields()
            poster = image_save(request.files.get('poster'))
            now = datetime.now(timezone.utc).isoformat()
            cols = list(data) + ['poster', 'created_at', 'updated_at']
            values = list(data.values()) + [poster, now, now]
            with db() as con:
                cur = con.execute(f"INSERT INTO movies ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", values)
                mid = cur.lastrowid
                for file in request.files.getlist('screenshots')[:20]:
                    pic = image_save(file)
                    if pic:
                        con.execute('INSERT INTO screenshots (movie_id, filename) VALUES (?,?)', (mid, pic))
            flash('Workprint added!', 'success')
            return redirect(url_for('detail', mid=mid))
        except ValueError as e:
            flash(str(e), 'error')
    return render_template('form.html', movie=None, pics=[], heading='Add a workprint')


@app.route('/admin/edit/<int:mid>', methods=['GET', 'POST'])
@protected
def edit(mid):
    movie = fetch_movie(mid, True)
    if request.method == 'POST':
        validate_csrf()
        try:
            data = get_fields()
            poster = image_save(request.files.get('poster'))
            sets = [f'{name}=?' for name in data]
            values = list(data.values())
            if poster:
                sets.append('poster=?')
                values.append(poster)
            sets.append('updated_at=?')
            values.append(datetime.now(timezone.utc).isoformat())
            values.append(mid)
            with db() as con:
                con.execute(f"UPDATE movies SET {','.join(sets)} WHERE id=?", values)
                for file in request.files.getlist('screenshots')[:20]:
                    pic = image_save(file)
                    if pic:
                        con.execute('INSERT INTO screenshots (movie_id, filename) VALUES (?,?)', (mid, pic))
            flash('Workprint updated.', 'success')
            return redirect(url_for('detail', mid=mid))
        except ValueError as e:
            flash(str(e), 'error')
    with db() as con:
        pics = con.execute('SELECT * FROM screenshots WHERE movie_id=? ORDER BY id', (mid,)).fetchall()
    return render_template('form.html', movie=movie, pics=pics, heading='Edit workprint')


@app.post('/admin/screenshot/<int:pic_id>/delete')
@protected
def delete_screenshot(pic_id):
    validate_csrf()
    with db() as con:
        pic = con.execute('SELECT * FROM screenshots WHERE id=?', (pic_id,)).fetchone()
        if not pic:
            abort(404)
        con.execute('DELETE FROM screenshots WHERE id=?', (pic_id,))
    (UPLOADS / pic['filename']).unlink(missing_ok=True)
    flash('Screenshot deleted.', 'success')
    return redirect(url_for('edit', mid=pic['movie_id']))


@app.post('/admin/delete/<int:mid>')
@protected
def delete(mid):
    validate_csrf()
    movie = fetch_movie(mid, True)
    with db() as con:
        filenames = [p[0] for p in con.execute('SELECT filename FROM screenshots WHERE movie_id=?', (mid,)).fetchall()]
        con.execute('DELETE FROM movies WHERE id=?', (mid,))
    for filename in filenames + ([movie['poster']] if movie['poster'] else []):
        (UPLOADS / filename).unlink(missing_ok=True)
    flash('Workprint deleted.', 'success')
    return redirect(url_for('home'))


@app.get('/uploads/<path:name>')
def uploads(name):
    return send_from_directory(UPLOADS, name, max_age=86400)


if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG') == '1', port=int(os.getenv('PORT', '8080')))
