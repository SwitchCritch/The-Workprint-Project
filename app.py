import os
import re
import sqlite3
import secrets
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse, urlsplit
from xml.etree import ElementTree as ET
from flask import Flask, Response, abort, flash, redirect, render_template, request, send_from_directory, session, url_for
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
DEFAULT_DAILY_LIMIT = max(1, min(50, int(os.getenv('DAILY_DOWNLOAD_LIMIT', '3'))))
LONDON_TZ = ZoneInfo('Europe/London')
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
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL COLLATE NOCASE UNIQUE,
            email TEXT NOT NULL COLLATE NOCASE UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            suspended INTEGER NOT NULL DEFAULT 0,
            daily_limit INTEGER,
            last_login_at TEXT
        );
        CREATE TABLE IF NOT EXISTS download_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
            movie_id INTEGER REFERENCES movies(id) ON DELETE SET NULL,
            movie_title TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            uk_date TEXT NOT NULL,
            provider TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_member_request_date ON download_requests(member_id,uk_date);
        CREATE INDEX IF NOT EXISTS idx_request_history ON download_requests(requested_at);
        CREATE TABLE IF NOT EXISTS auth_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            attempted_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_auth_attempts_ip ON auth_attempts(ip, attempted_at);
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


def current_member():
    member_id = session.get('member_id')
    if not isinstance(member_id, int):
        return None
    with db() as con:
        member = con.execute('SELECT * FROM members WHERE id=?', (member_id,)).fetchone()
    return member if member and not member['suspended'] else None


def member_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_member():
            flash('Please sign in to access downloads.', 'error')
            return redirect(url_for('member_login', next=(url_for('detail', mid=kwargs['mid']) if request.endpoint == 'member_download' and 'mid' in kwargs else request.path)))
        return fn(*args, **kwargs)
    return wrapper


def uk_today():
    return datetime.now(LONDON_TZ).date().isoformat()


def remaining_downloads(member):
    if not member:
        return None
    with db() as con:
        count = con.execute('SELECT COUNT(*) FROM download_requests WHERE member_id=? AND uk_date=?',
                            (member['id'], uk_today())).fetchone()[0]
    limit = member['daily_limit'] if member['daily_limit'] is not None else DEFAULT_DAILY_LIMIT
    return max(0, limit - count)


def safe_next(target, fallback='home'):
    # Only allow internal relative paths; prevent open redirects.
    target = (target or '').strip()
    parts = urlsplit(target)
    if target.startswith('/') and not target.startswith('//') and not parts.netloc and not parts.scheme and '\\' not in target:
        return target
    return url_for(fallback)


def auth_rate_limited():
    now = datetime.now(timezone.utc)
    ip = request.remote_addr or 'unknown'
    with db() as con:
        con.execute('DELETE FROM auth_attempts WHERE attempted_at<?', ((now-timedelta(days=2)).isoformat(),))
        count = con.execute('SELECT COUNT(*) FROM auth_attempts WHERE ip=? AND attempted_at>?',
                            (ip, (now-timedelta(minutes=30)).isoformat())).fetchone()[0]
        if count >= 12:
            return True
        con.execute('INSERT INTO auth_attempts (ip, attempted_at) VALUES (?,?)', (ip, now.isoformat()))
    return False


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
    return {'is_admin': admin_ok(), 'member': current_member(), 'csrf_token': csrf(), 'donation_url': DONATION_URL, 'categories_nav': CATEGORIES}


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


# Public, dynamically maintained search-engine sitemap. No unpublished content is listed.
# SITE_URL may be overridden in Railway if the canonical domain changes.
SITE_URL = os.getenv('SITE_URL', 'https://theworkprintproject.com').rstrip('/')
if not SITE_URL.startswith('https://'):
    SITE_URL = 'https://theworkprintproject.com'


@app.get('/sitemap.xml')
def sitemap():
    namespace = 'http://www.sitemaps.org/schemas/sitemap/0.9'
    ET.register_namespace('', namespace)
    root = ET.Element(f'{{{namespace}}}urlset')

    def include(path, modified=None):
        item = ET.SubElement(root, f'{{{namespace}}}url')
        ET.SubElement(item, f'{{{namespace}}}loc').text = SITE_URL + path
        if modified:
            # Existing app writes timestamps as ISO strings; sitemap uses YYYY-MM-DD.
            date = str(modified)[:10]
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
                ET.SubElement(item, f'{{{namespace}}}lastmod').text = date

    include(url_for('home'))
    include(url_for('browse'))
    include(url_for('category_index'))
    include(url_for('contact'))
    include(url_for('donate'))
    for category in CATEGORIES:
        from urllib.parse import urlencode
        include(url_for('browse') + '?' + urlencode({'category': category}))
    with db() as con:
        movies = con.execute('SELECT id, updated_at FROM movies WHERE published=1 ORDER BY id').fetchall()
        articles = con.execute('SELECT id, updated_at FROM articles WHERE published=1 ORDER BY id').fetchall()
    for movie in movies:
        include(url_for('detail', mid=movie['id']), movie['updated_at'])
    for article in articles:
        include(url_for('article_detail', aid=article['id']), article['updated_at'])
    xml = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    return Response(xml, mimetype='application/xml', headers={'Cache-Control': 'public, max-age=900'})


@app.get('/robots.txt')
def robots_txt():
    text = ('User-agent: *\n'
            'Disallow: /admin/\n'
            'Disallow: /login\n'
            'Disallow: /logout\n'
            f'Sitemap: {SITE_URL}/sitemap.xml\n')
    return Response(text, mimetype='text/plain')


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
    member = current_member()
    return render_template('detail.html', movie=movie, pics=pics, remaining=remaining_downloads(member))


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


@app.route('/members/register', methods=['GET', 'POST'])
def member_register():
    if current_member():
        return redirect(url_for('member_account'))
    if request.method == 'POST':
        validate_csrf()
        if auth_rate_limited():
            flash('Too many sign-in attempts from this connection. Please try again later.', 'error')
        elif request.form.get('website', '').strip():
            flash('Unable to create this account.', 'error')
        else:
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            confirm = request.form.get('confirm', '')
            if not re.fullmatch(r'[A-Za-z0-9_.-]{3,32}', username):
                flash('Username must be 3–32 characters (letters, numbers, underscore, dash or dot).', 'error')
            elif len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                flash('Enter a valid email address.', 'error')
            elif len(password) < 12 or len(password) > 256:
                flash('Please use a password of at least 12 characters.', 'error')
            elif password != confirm:
                flash('Passwords do not match.', 'error')
            else:
                try:
                    with db() as con:
                        cur = con.execute('INSERT INTO members (username,email,password_hash,created_at) VALUES (?,?,?,?)',
                                          (username,email,generate_password_hash(password),datetime.now(timezone.utc).isoformat()))
                    session.clear()
                    session['member_id'] = cur.lastrowid
                    session['csrf'] = secrets.token_urlsafe(32)
                    flash('Welcome! Your member account is ready.', 'success')
                    return redirect(url_for('member_account'))
                except sqlite3.IntegrityError:
                    flash('This username or email is already in use.', 'error')
    return render_template('member_register.html')


@app.route('/members/login', methods=['GET', 'POST'])
def member_login():
    if current_member():
        return redirect(url_for('member_account'))
    if request.method == 'POST':
        validate_csrf()
        if auth_rate_limited():
            flash('Too many sign-in attempts. Please try again later.', 'error')
        else:
            login_id = request.form.get('login', '').strip()[:254]
            password = request.form.get('password', '')
            with db() as con:
                member = con.execute('SELECT * FROM members WHERE username=? OR email=?', (login_id,login_id)).fetchone()
            if member and not member['suspended'] and check_password_hash(member['password_hash'], password):
                session.clear()
                session['member_id'] = member['id']
                session['csrf'] = secrets.token_urlsafe(32)
                with db() as con:
                    con.execute('UPDATE members SET last_login_at=? WHERE id=?', (datetime.now(timezone.utc).isoformat(),member['id']))
                return redirect(safe_next(request.form.get('next'), 'member_account'))
            flash('Incorrect credentials or account unavailable.', 'error')
    return render_template('member_login.html', next_url=safe_next(request.args.get('next'), 'member_account'))


@app.post('/members/logout')
def member_logout():
    validate_csrf()
    session.clear()
    return redirect(url_for('home'))


@app.get('/members/account')
@member_required
def member_account():
    member = current_member()
    with db() as con:
        history = con.execute('SELECT * FROM download_requests WHERE member_id=? ORDER BY requested_at DESC,id DESC LIMIT 150',
                              (member['id'],)).fetchall()
        today = con.execute('SELECT COUNT(*) FROM download_requests WHERE member_id=? AND uk_date=?', (member['id'],uk_today())).fetchone()[0]
    limit = member['daily_limit'] if member['daily_limit'] is not None else DEFAULT_DAILY_LIMIT
    return render_template('member_account.html', history=history, today=today, limit=limit)


@app.post('/workprint/<int:mid>/download')
@member_required
def member_download(mid):
    validate_csrf()
    movie = fetch_movie(mid, False)
    direct = pixeldrain_direct(movie['pixeldrain_url']) if movie['pixeldrain_url'] else ''
    external = movie['download_url'] or ''
    if direct:
        link, provider = direct, 'Pixeldrain'
    elif external:
        parsed = urlparse(external)
        if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
            abort(400)
        link, provider = external, 'External'
    else:
        abort(404)
    member = current_member()
    if not member:
        return redirect(url_for('member_login',next=request.path))
    uk_date = uk_today()
    limit = member['daily_limit'] if member['daily_limit'] is not None else DEFAULT_DAILY_LIMIT
    con = db()
    try:
        # BEGIN IMMEDIATE serializes concurrent requests, preventing quota bypasses.
        con.execute('BEGIN IMMEDIATE')
        fresh = con.execute('SELECT suspended,daily_limit FROM members WHERE id=?',(member['id'],)).fetchone()
        if not fresh or fresh['suspended']:
            con.rollback()
            abort(403)
        limit = fresh['daily_limit'] if fresh['daily_limit'] is not None else DEFAULT_DAILY_LIMIT
        count = con.execute('SELECT COUNT(*) FROM download_requests WHERE member_id=? AND uk_date=?',
                            (member['id'],uk_date)).fetchone()[0]
        if count >= limit:
            con.rollback()
            flash('You have used all your download requests for today. Your allowance resets at midnight UK time.', 'error')
            return redirect(url_for('detail',mid=mid))
        con.execute('INSERT INTO download_requests (member_id,movie_id,movie_title,requested_at,uk_date,provider) VALUES (?,?,?,?,?,?)',
                    (member['id'],mid,movie['title'],datetime.now(timezone.utc).isoformat(),uk_date,provider))
        con.commit()
    finally:
        con.close()
    # Redirect to a third-party URL; this records link requests, not actual download completions.
    response = redirect(link, code=303)
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/admin/members')
@protected
def admin_members():
    q=request.args.get('q','').strip()[:120]
    with db() as con:
        if q:
            members=con.execute("""SELECT m.*, (SELECT COUNT(*) FROM download_requests r WHERE r.member_id=m.id AND r.uk_date=?) AS today_count,
                (SELECT COUNT(*) FROM download_requests r WHERE r.member_id=m.id) AS total_count
                FROM members m WHERE m.username LIKE ? OR m.email LIKE ? ORDER BY m.created_at DESC""",
                (uk_today(),f'%{q}%',f'%{q}%')).fetchall()
        else:
            members=con.execute("""SELECT m.*, (SELECT COUNT(*) FROM download_requests r WHERE r.member_id=m.id AND r.uk_date=?) AS today_count,
                (SELECT COUNT(*) FROM download_requests r WHERE r.member_id=m.id) AS total_count
                FROM members m ORDER BY m.created_at DESC""",(uk_today(),)).fetchall()
        count=con.execute('SELECT COUNT(*) FROM members').fetchone()[0]
        today_count=con.execute('SELECT COUNT(*) FROM download_requests WHERE uk_date=?',(uk_today(),)).fetchone()[0]
        recent=con.execute("""SELECT d.*,m.username FROM download_requests d JOIN members m ON m.id=d.member_id
                              ORDER BY d.requested_at DESC,d.id DESC LIMIT 50""").fetchall()
    return render_template('admin_members.html',members=members,q=q,total_members=count,today_count=today_count,recent=recent,default_limit=DEFAULT_DAILY_LIMIT)


@app.get('/admin/members/<int:member_id>')
@protected
def admin_member_detail(member_id):
    with db() as con:
        member=con.execute('SELECT * FROM members WHERE id=?',(member_id,)).fetchone()
        history=con.execute('SELECT * FROM download_requests WHERE member_id=? ORDER BY requested_at DESC,id DESC LIMIT 500',(member_id,)).fetchall()
        count=con.execute('SELECT COUNT(*) FROM download_requests WHERE member_id=? AND uk_date=?',(member_id,uk_today())).fetchone()[0]
    if not member:
        abort(404)
    return render_template('admin_member_detail.html',member_record=member,history=history,today_count=count,default_limit=DEFAULT_DAILY_LIMIT)


@app.post('/admin/members/<int:member_id>/settings')
@protected
def admin_member_settings(member_id):
    validate_csrf()
    operation=request.form.get('operation')
    with db() as con:
        member=con.execute('SELECT id FROM members WHERE id=?',(member_id,)).fetchone()
        if not member: abort(404)
        if operation == 'suspend':
            con.execute('UPDATE members SET suspended=1 WHERE id=?',(member_id,))
            flash('Member suspended.', 'success')
        elif operation == 'reactivate':
            con.execute('UPDATE members SET suspended=0 WHERE id=?',(member_id,))
            flash('Member reactivated.', 'success')
        elif operation == 'limit':
            value=request.form.get('daily_limit','').strip()
            if value == 'default':
                con.execute('UPDATE members SET daily_limit=NULL WHERE id=?',(member_id,))
            elif value.isdigit() and 1<=int(value)<=50:
                con.execute('UPDATE members SET daily_limit=? WHERE id=?',(int(value),member_id))
            else:
                abort(400,'Invalid limit')
            flash('Daily limit updated.', 'success')
        else:
            abort(400)
    return redirect(url_for('admin_member_detail',member_id=member_id))


@app.get('/uploads/<path:name>')
def uploads(name):
    return send_from_directory(UPLOADS, name, max_age=86400)


if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG') == '1', port=int(os.getenv('PORT', '8080')))
