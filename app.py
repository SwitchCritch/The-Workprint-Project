import os
import re
import sqlite3
import secrets
from datetime import datetime, timezone, timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse
from flask import Flask, abort, flash, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from markupsafe import Markup, escape
import bleach

BASE = Path(__file__).resolve().parent
# Prefer the mounted Railway volume automatically; DATA_DIR=/data remains recommended.
DATA = Path(os.getenv('DATA_DIR', '/data' if Path('/data').is_dir() else str(BASE / 'data')))
UPLOADS = DATA / 'uploads'
DATA.mkdir(parents=True, exist_ok=True)
UPLOADS.mkdir(parents=True, exist_ok=True)
DB = DATA / 'workprints.db'
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '')
ADMIN_PASSWORD_HASH = os.getenv('ADMIN_PASSWORD_HASH', '')
DONATION_URL = os.getenv('DONATION_URL','').strip()
if DONATION_URL and (urlparse(DONATION_URL).scheme != 'https' or not urlparse(DONATION_URL).hostname):
    DONATION_URL = ''
ALLOWED_EXT = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
CATEGORIES = ('Workprint', 'CAM', '35mm', 'Screener', 'VHS', 'Betamax', 'Laserdisc')
RICH_TAGS = {'p', 'br', 'div', 'strong', 'b', 'em', 'i', 'u', 'h2', 'h3', 'ul', 'ol', 'li', 'blockquote', 'a'}
RICH_ATTRIBUTES = {'a': ['href', 'title']}



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
            title TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'Workprint', release_year INTEGER, workprint_date TEXT,
            genre TEXT, director TEXT, runtime TEXT, official_runtime TEXT,
            synopsis TEXT, differences TEXT, differences_is_html INTEGER NOT NULL DEFAULT 0, notes TEXT, source_details TEXT,
            file_size TEXT, file_format TEXT, video_resolution TEXT,
            audio_details TEXT, download_url TEXT, pixeldrain_url TEXT, poster TEXT,
            published INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, excerpt TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '',
            cover TEXT, status TEXT NOT NULL DEFAULT 'published',
            published INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS contact_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, email TEXT NOT NULL, subject TEXT NOT NULL,
            message TEXT NOT NULL, created_at TEXT NOT NULL, read INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS contact_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ip TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS screenshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
            filename TEXT NOT NULL, caption TEXT NOT NULL DEFAULT ''
        );
        ''')
        columns = {row['name'] for row in con.execute('PRAGMA table_info(movies)')}
        if 'pixeldrain_url' not in columns:
            con.execute('ALTER TABLE movies ADD COLUMN pixeldrain_url TEXT')
        if 'category' not in columns:
            con.execute("ALTER TABLE movies ADD COLUMN category TEXT NOT NULL DEFAULT 'Workprint'")
        if 'differences_is_html' not in columns:
            con.execute('ALTER TABLE movies ADD COLUMN differences_is_html INTEGER NOT NULL DEFAULT 0')
        # Preserve all movie records while removing the retired category from the site.
        # Existing "Alternate Version" entries become Workprints, and remain editable.
        con.execute("UPDATE movies SET category='Workprint' WHERE category='Alternate Version'")


init_db()


def clean_rich_html(value):
    """Sanitise author-entered markup, leaving only basic document formatting."""
    return bleach.clean(value or '', tags=RICH_TAGS, attributes=RICH_ATTRIBUTES,
                        protocols={'https', 'http', 'mailto'}, strip=True)


@app.template_filter('rich_differences')
def rich_differences(value, is_html=0):
    if not value:
        return Markup('')
    if is_html:
        return Markup(clean_rich_html(value))
    # Preserve old plain-text descriptions exactly; do not interpret them as HTML.
    paragraphs = value.replace('\r\n', '\n').replace('\r', '\n').split('\n\n')
    return Markup(''.join('<p>' + '<br>'.join(str(escape(part)) for part in para.split('\n')) + '</p>' for para in paragraphs))


@app.template_filter('pixeldrain_direct')
def pixeldrain_direct(link):
    if not link:
        return ''
    p = urlparse(link)
    segments = p.path.strip('/').split('/')
    if p.hostname not in ('pixeldrain.com', 'www.pixeldrain.com') or len(segments) != 2 or segments[0] != 'u' or not re.fullmatch(r'[A-Za-z0-9_-]{4,100}', segments[1]):
        return ''
    return f'https://pixeldrain.com/api/file/{segments[1]}?download'


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
    return {'is_admin': admin_ok(), 'csrf_token': csrf(), 'donation_url': DONATION_URL, 'categories_nav': CATEGORIES}


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
    with db() as con:
        condition = '' if admin_ok() else 'WHERE published=1'
        articles = con.execute(f'SELECT * FROM articles {condition} ORDER BY created_at DESC, id DESC').fetchall()
        recent = con.execute('SELECT * FROM movies WHERE published=1 ORDER BY created_at DESC, id DESC LIMIT 6').fetchall()
    return render_template('home.html', articles=articles, recent=recent)


SORT_ORDERS = {
    'newest': 'created_at DESC, id DESC',
    'oldest': 'created_at ASC, id ASC',
    'az': 'title COLLATE NOCASE ASC, id DESC',
    'za': 'title COLLATE NOCASE DESC, id DESC',
    'year_new': 'release_year IS NULL, release_year DESC, title COLLATE NOCASE ASC',
    'year_old': 'release_year IS NULL, release_year ASC, title COLLATE NOCASE ASC',
    'updated': 'updated_at DESC, id DESC',
}


@app.get('/browse')
def browse():
    q = request.args.get('q', '').strip()[:120]
    genre = request.args.get('genre', '').strip()[:90]
    category = request.args.get('category', '').strip()
    year = request.args.get('year', '').strip()
    order = request.args.get('order', 'newest')
    if order not in SORT_ORDERS:
        order = 'newest'
    sql = 'SELECT * FROM movies WHERE 1=1'
    vals = []
    if not admin_ok():
        sql += ' AND published=1'
    if q:
        sql += ' AND (title LIKE ? OR synopsis LIKE ? OR differences LIKE ?)'
        vals += [f'%{q}%'] * 3
    if category in CATEGORIES:
        sql += ' AND category=?'
        vals.append(category)
    if genre:
        sql += ' AND genre=?'
        vals.append(genre)
    if year.isdigit():
        sql += ' AND release_year=?'
        vals.append(int(year))
    sql += ' ORDER BY ' + SORT_ORDERS[order]
    with db() as con:
        movies = con.execute(sql, vals).fetchall()
        genres = [r[0] for r in con.execute("SELECT DISTINCT genre FROM movies WHERE genre IS NOT NULL AND genre != '' ORDER BY genre").fetchall()]
    return render_template('browse.html', movies=movies, genres=genres, categories=CATEGORIES,
                           q=q, genre=genre, category=category, year=year, order=order)


@app.get('/categories')
def category_index():
    with db() as con:
        counts = {r['category']:r['total'] for r in con.execute('SELECT category, COUNT(*) AS total FROM movies WHERE published=1 GROUP BY category')}
    return render_template('categories.html', categories=CATEGORIES, counts=counts)


@app.get('/news/<int:aid>')
def article_detail(aid):
    with db() as con:
        article=con.execute('SELECT * FROM articles WHERE id=?',(aid,)).fetchone()
    if not article or (not article['published'] and not admin_ok()):
        abort(404)
    return render_template('article.html', article=article)


@app.route('/admin/news/new', methods=['GET','POST'])
@protected
def article_add():
    return article_form(None)


@app.route('/admin/news/<int:aid>/edit', methods=['GET','POST'])
@protected
def article_edit(aid):
    with db() as con:
        article=con.execute('SELECT * FROM articles WHERE id=?',(aid,)).fetchone()
    if not article:
        abort(404)
    return article_form(article)


def article_form(article):
    if request.method == 'POST':
        validate_csrf()
        try:
            title=request.form.get('title','').strip()[:200]
            excerpt=request.form.get('excerpt','').strip()[:500]
            body=request.form.get('body','').strip()
            status=request.form.get('status','published')
            if not title:
                raise ValueError('Please enter an article title.')
            if status not in ('published','coming_soon'):
                raise ValueError('Invalid article type.')
            if len(body)>150000:
                raise ValueError('Article is too long.')
            body=clean_rich_html(body)
            published=int(request.form.get('published')=='on')
            cover=image_save(request.files.get('cover'))
            now=datetime.now(timezone.utc).isoformat()
            with db() as con:
                if article:
                    if cover:
                        con.execute('UPDATE articles SET title=?,excerpt=?,body=?,status=?,published=?,cover=?,updated_at=? WHERE id=?',
                            (title,excerpt,body,status,published,cover,now,article['id']))
                    else:
                        con.execute('UPDATE articles SET title=?,excerpt=?,body=?,status=?,published=?,updated_at=? WHERE id=?',
                            (title,excerpt,body,status,published,now,article['id']))
                    aid=article['id']
                else:
                    aid=con.execute('INSERT INTO articles (title,excerpt,body,status,published,cover,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                         (title,excerpt,body,status,published,cover,now,now)).lastrowid
            flash('Article saved successfully.','success')
            return redirect(url_for('article_detail',aid=aid))
        except ValueError as exc:
            flash(str(exc),'error')
    return render_template('article_form.html',article=article)


@app.post('/admin/news/<int:aid>/delete')
@protected
def article_delete(aid):
    validate_csrf()
    with db() as con:
        con.execute('DELETE FROM articles WHERE id=?',(aid,))
    flash('Article deleted.','success')
    return redirect(url_for('home'))


@app.route('/contact', methods=['GET','POST'])
def contact():
    if request.method == 'POST':
        validate_csrf()
        # Honeypot and server-side rate limiting; no third-party email service required.
        if request.form.get('website','').strip():
            flash('Your message was received.','success')
            return redirect(url_for('contact'))
        name=request.form.get('name','').strip()[:120]
        email=request.form.get('email','').strip()[:254]
        subject=request.form.get('subject','General enquiry').strip()[:140]
        message=request.form.get('message','').strip()[:5000]
        if not name or not message or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
            flash('Please enter your name, a valid email, and a message.','error')
        else:
            now=datetime.now(timezone.utc)
            ip=request.remote_addr or 'unknown'
            with db() as con:
                recent=con.execute('SELECT COUNT(*) FROM contact_attempts WHERE ip=? AND created_at>?',
                    (ip,(now-timedelta(hours=1)).isoformat())).fetchone()[0]
                if recent>=5:
                    flash('Too many messages. Please try again later.','error')
                    return render_template('contact.html')
                con.execute('INSERT INTO contact_attempts (ip,created_at) VALUES (?,?)',(ip,now.isoformat()))
                con.execute('INSERT INTO contact_messages (name,email,subject,message,created_at) VALUES (?,?,?,?,?)',
                    (name,email,subject,message,now.isoformat()))
                con.execute('DELETE FROM contact_attempts WHERE created_at<?',((now-timedelta(days=2)).isoformat(),))
            flash('Message sent. Thank you for contacting us!','success')
            return redirect(url_for('contact'))
    return render_template('contact.html')


@app.get('/admin/messages')
@protected
def inbox():
    with db() as con:
        messages=con.execute('SELECT * FROM contact_messages ORDER BY created_at DESC,id DESC').fetchall()
    return render_template('inbox.html',messages=messages)


@app.post('/admin/messages/<int:mid>/read')
@protected
def inbox_read(mid):
    validate_csrf()
    with db() as con:
        con.execute('UPDATE contact_messages SET read=1 WHERE id=?',(mid,))
    return redirect(url_for('inbox'))


@app.post('/admin/messages/<int:mid>/delete')
@protected
def inbox_delete(mid):
    validate_csrf()
    with db() as con:
        con.execute('DELETE FROM contact_messages WHERE id=?',(mid,))
    return redirect(url_for('inbox'))


@app.get('/donate')
def donate():
    if DONATION_URL:
        return redirect(DONATION_URL)
    return render_template('donate.html')


@app.template_filter('numberfmt')
def numberfmt(value):
    return f'{int(value):,}'


@app.get('/random')
def random_movie():
    with db() as con:
        entry = con.execute('SELECT id FROM movies WHERE published=1 ORDER BY RANDOM() LIMIT 1').fetchone()
    if not entry:
        return redirect(url_for('browse'))
    return redirect(url_for('detail', mid=entry['id']))


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


FIELDS = ['title', 'category', 'release_year', 'workprint_date', 'genre', 'director', 'runtime', 'official_runtime',
          'synopsis', 'differences', 'notes', 'source_details', 'file_size', 'file_format',
          'video_resolution', 'audio_details', 'download_url', 'pixeldrain_url']


def get_fields():
    data = {name: request.form.get(name, '').strip() for name in FIELDS}
    if not data['title']:
        raise ValueError('Movie title is required.')
    if len(data['differences']) > 75000:
        raise ValueError('Differences text is too long (maximum 75,000 characters).')
    data['differences'] = clean_rich_html(data['differences'])
    data['differences_is_html'] = 1
    if data['category'] not in CATEGORIES:
        raise ValueError('Choose a valid movie category.')
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
    pixeldrain = data['pixeldrain_url']
    if pixeldrain:
        p = urlparse(pixeldrain)
        if p.scheme != 'https' or p.hostname not in ('pixeldrain.com', 'www.pixeldrain.com') or p.username or p.password or p.port not in (None, 443):
            raise ValueError('Enter a valid HTTPS Pixeldrain file link (pixeldrain.com/u/FILE_ID).')
        segments = p.path.strip('/').split('/')
        if not (len(segments) == 2 and segments[0] == 'u' and re.fullmatch(r'[A-Za-z0-9_-]{4,100}', segments[1])) and not (len(segments) == 3 and segments[:2] == ['api', 'file'] and re.fullmatch(r'[A-Za-z0-9_-]{4,100}', segments[2])):
            raise ValueError('Use a Pixeldrain individual file link (pixeldrain.com/u/FILE_ID), not a list or directory.')
        file_id = segments[-1]
        data['pixeldrain_url'] = f'https://pixeldrain.com/u/{file_id}'
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
            flash('Movie added!', 'success')
            return redirect(url_for('detail', mid=mid))
        except ValueError as e:
            flash(str(e), 'error')
    return render_template('form.html', movie=None, pics=[], heading='Add a movie', categories=CATEGORIES)


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
            flash('Movie updated.', 'success')
            return redirect(url_for('detail', mid=mid))
        except ValueError as e:
            flash(str(e), 'error')
    with db() as con:
        pics = con.execute('SELECT * FROM screenshots WHERE movie_id=? ORDER BY id', (mid,)).fetchall()
    return render_template('form.html', movie=movie, pics=pics, heading='Edit movie', categories=CATEGORIES)


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
    flash('Movie deleted.', 'success')
    return redirect(url_for('browse'))


@app.get('/uploads/<path:name>')
def uploads(name):
    return send_from_directory(UPLOADS, name, max_age=86400)


if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG') == '1', port=int(os.getenv('PORT', '8080')))
