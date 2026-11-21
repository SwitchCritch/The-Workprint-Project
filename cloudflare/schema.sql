-- Schema copied from app.py init_db() on main, 21 Nov 2026.
-- No production data or credentials are included.
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
