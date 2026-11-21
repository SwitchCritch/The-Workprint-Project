"""Read-only deployment smoke-test; NOT the production Workprint Project app.

This intentionally does not import ../app.py. That app opens a local SQLite
database and a writable filesystem at import time, neither of which is a
durable Cloudflare Workers storage solution.
"""
from flask import Flask, Response, request
from pyodide.ffi import run_sync
from workers import wsgi

app = Flask(__name__)


@app.get("/health")
def health():
    return {"status": "ok", "mode": "migration-preview", "writes_enabled": False}


@app.get("/health/storage")
def storage_health():
    # Read-only smoke test: no member data, object keys or exception details
    # are returned. No writes, migrations or public bucket access are needed.
    checks = {"database": "unavailable", "image_storage": "unavailable"}
    env = request.environ["workers.env"]
    try:
        result = run_sync(env.DB.prepare("SELECT 1 AS ok").first("ok"))
        if result == 1:
            checks["database"] = "connected"
    except Exception:
        pass
    try:
        # A missing object is expected and is still a successful R2 request.
        run_sync(env.UPLOADS.head("__workprint_preview_healthcheck__"))
        checks["image_storage"] = "connected"
    except Exception:
        pass
    healthy = all(value == "connected" for value in checks.values())
    return {"status": "ok" if healthy else "connection_check_failed",
            **checks, "writes_enabled": False}, 200 if healthy else 503


@app.route("/", defaults={"path": ""}, methods=["GET", "HEAD"])
@app.route("/<path:path>", methods=["GET", "HEAD"])
def static_preview(path):
    # The preview root now opens the migrated news page. Keep existing
    # static asset paths available while rejecting unknown paths.
    if path in ("", "index.html"):
        return redirect(url_for("home"), code=302)
    if path not in ("style.css", "workprint-logo.png", "favicon.svg"):
        return {"error": "The full archive is not yet migrated."}, 404
    assets = request.environ["workers.env"].ASSETS
    asset_response = run_sync(assets.fetch(f"https://assets.local/{'' if path == 'index.html' else path}"))
    body = run_sync(asset_response.bytes())
    return Response(body, status=asset_response.status, headers=asset_response.headers)



# Read-only public catalogue staging. Original templates and CSS adapted
# from main; do not import the production SQLite backend or expose secrets.
from flask import abort, render_template
from jinja2 import DictLoader
from markupsafe import Markup, escape
from html.parser import HTMLParser
import re

app.jinja_loader = DictLoader({"base.html":"<!doctype html>\n<html lang=\"en\"><head>\n<meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n<meta name=\"theme-color\" content=\"#060c1b\">\n<meta name=\"description\" content=\"The Workprint Project — a curated database of workprints, screeners and rare film formats.\">\n<title>{% block title %}The Workprint Project{% endblock %}</title>\n<link rel=\"icon\" href=\"{{url_for('static_preview',path='favicon.svg')}}\" type=\"image/svg+xml\">\n<link rel=\"stylesheet\" href=\"{{url_for('catalogue_css')}}\">\n{% if seo_canonical %}<meta name=\"robots\" content=\"index,follow\"><link rel=\"canonical\" href=\"{{seo_canonical}}\">{% else %}<meta name=\"robots\" content=\"noindex,nofollow\">{% endif %}</head>\n<body class=\"dashboard {% if request.endpoint == 'home' %}home-page{% else %}inner-page{% endif %}\">\n<header class=\"site-header\" id=\"top\">\n<div class=\"hero-art\"><a class=\"header-logo-link\" href=\"{{url_for('home')}}\" aria-label=\"The Workprint Project home\"><img class=\"header-logo\" src=\"{{url_for('static_preview',path='workprint-logo.png')}}\" alt=\"The Workprint Project\" onerror=\"this.style.display='none';this.nextElementSibling.style.display='inline'\"><span style=\"display:none;font-size:clamp(1.3rem,4vw,2.7rem);font-weight:800;letter-spacing:.06em;color:#eaf4ff\">THE WORKPRINT PROJECT</span></a></div>\n<nav class=\"site-nav shell\" aria-label=\"Primary navigation\">\n<a class=\"{% if request.endpoint == 'home' %}active{% endif %}\" href=\"{{url_for('home')}}\"><span class=\"nav-icon\">⌂</span> NEWS</a>\n<a class=\"{% if request.endpoint == 'browse' %}active{% endif %}\" href=\"{{url_for('browse')}}\"><span class=\"nav-icon\">▦</span> BROWSE</a>\n<a class=\"{% if request.endpoint == 'category_index' %}active{% endif %}\" href=\"{{url_for('category_index')}}\"><span class=\"nav-icon\">▱</span> CATEGORIES</a>\n\n<form class=\"nav-search\" action=\"{{url_for('browse')}}\" method=\"get\"><label class=\"sr-only\" for=\"nav-query\">Search films</label><input id=\"nav-query\" name=\"q\" type=\"search\" placeholder=\"Search films...\" value=\"{{request.args.get('q','')}}\"><button>SEARCH</button></form>\n<a class=\"nav-login\" href=\"{{url_for('preview_contact')}}\">CONTACT</a><a class=\"nav-login\" href=\"{{url_for('preview_donate')}}\">DONATE</a><a class=\"nav-login\" href=\"{{url_for('preview_member_account')}}\">MEMBERS</a><a class=\"nav-login\" href=\"{{url_for('preview_admin_dashboard')}}\">ADMIN</a>\n</nav>\n</header>\n<main><div style=\"padding:12px;text-align:center;background:#16304a;color:white\">{% if request.host.lower().split(':')[0] == 'theworkprintproject.com' %}The archive has moved to new hosting. The catalogue and member accounts are available. File downloads remain unavailable.{% else %}CLOUDFLARE STAGING · Preview of the archive. Downloads remain disabled.{% endif %}</div>{% if not schema_ready %}<div style=\"padding:12px;text-align:center\">The original archive data has not been imported yet.</div>{% endif %}\n{% with messages=get_flashed_messages(with_categories=true) %}{% if messages %}<div class=\"shell flashes\">{% for kind,msg in messages %}<div class=\"flash {{kind}}\">{{msg}}</div>{% endfor %}</div>{% endif %}{% endwith %}\n{% block body %}{% endblock %}\n</main>\n<footer class=\"site-footer\"><div class=\"shell footer-inner\"><span>© THE WORKPRINT PROJECT</span><span>THE ALTERNATIVE CINEMA ARCHIVE · ONLY SHARE MATERIAL YOU ARE AUTHORISED TO DISTRIBUTE</span><a href=\"#top\">BACK TO TOP ↑</a></div></footer>\n</body></html>\n","home.html":"{% extends 'base.html' %}{% block title %}Latest News — The Workprint Project{% endblock %}{% block body %}\n<div class=\"shell news-hub\">\n<div class=\"page-intro\"><div><span class=\"eyebrow\">THE WORKPRINT PROJECT / NEWSROOM</span><h1>NEWS &amp; UPDATES</h1><p>New additions, upcoming releases and updates from the archive.</p></div>{% if is_admin %}<a class=\"button primary\" href=\"{{url_for('article_add')}}\">+ WRITE ARTICLE</a>{% endif %}</div>\n{% if articles %}<section class=\"news-layout\"><div class=\"news-stack\">{% for a in articles %}<article class=\"news-card {% if loop.first %}lead-news{% endif %}\"><a href=\"{{url_for('article_detail',aid=a.id)}}\" class=\"news-art\">{% if a.cover %}<img src=\"{{url_for('uploads',name=a.cover)}}\" alt=\"\">{% else %}<div class=\"news-art-placeholder\">▣ <span>THE WORKPRINT PROJECT</span></div>{% endif %}</a><div class=\"news-copy\"><div class=\"article-meta\"><span class=\"news-tag {% if a.status=='coming_soon' %}upcoming{% endif %}\">{{'COMING SOON' if a.status=='coming_soon' else 'ARCHIVE NEWS'}}</span><time>{{a.created_at[:10]}}</time>{% if not a.published %}<span class=\"news-tag upcoming\">DRAFT</span>{% endif %}</div><h2><a href=\"{{url_for('article_detail',aid=a.id)}}\">{{a.title}}</a></h2><p>{{a.excerpt or (a.body|striptags|truncate(200))}}</p><a href=\"{{url_for('article_detail',aid=a.id)}}\" class=\"read-more\">READ ARTICLE →</a></div></article>{% endfor %}</div><aside class=\"news-sidebar\"><div class=\"side-panel\"><h2>THE ARCHIVE</h2><p>Explore rare prints, early cuts and unique versions of cinema history.</p><a class=\"button primary full\" href=\"{{url_for('browse')}}\">BROWSE ALL FILMS →</a></div><div class=\"side-panel\"><h2>EXPLORE BY FORMAT</h2><div class=\"news-format-links\">{% for cat in categories_nav %}<a href=\"{{url_for('browse',category=cat)}}\">{{cat}} <span>→</span></a>{% endfor %}</div></div></aside></section>\n{% else %}<section class=\"empty-news\"><span class=\"empty-news-icon\">▣</span><h2>NEWSROOM OPENING SOON</h2><p>News about new films, rare discoveries and upcoming additions will appear here.</p>{% if is_admin %}<a class=\"button primary\" href=\"{{url_for('article_add')}}\">PUBLISH YOUR FIRST ARTICLE</a>{% endif %}</section>{% endif %}\n{% if recent %}<section class=\"recent-films\"><div class=\"section-heading\"><h2>RECENT FILMS</h2><a href=\"{{url_for('browse')}}\">VIEW COLLECTION →</a></div><div class=\"recent-news-grid\">{% for m in recent %}<a class=\"recent-news-card\" href=\"{{url_for('detail',mid=m.id)}}\">{% if m.poster %}<img src=\"{{url_for('uploads',name=m.poster)}}\" alt=\"\">{% else %}<div class=\"mini-placeholder\">▣</div>{% endif %}<strong>{{m.title}}</strong><span>{{m.category}}</span></a>{% endfor %}</div></section>{% endif %}\n</div>{% endblock %}\n","browse.html":"{% extends 'base.html' %}{% block title %}Browse the Archive — The Workprint Project{% endblock %}{% block body %}\n<div class=\"shell archive-browse\"><div class=\"page-intro\"><div><span class=\"eyebrow\">DISCOVER THE COLLECTION</span><h1>BROWSE THE ARCHIVE</h1><p>Explore the complete film library, search, filter and choose how it is ordered.</p></div>{% if is_admin %}<a class=\"button primary\" href=\"{{url_for('add')}}\">+ ADD FILM</a>{% endif %}</div>\n<form class=\"browse-controls\" method=\"get\" action=\"{{url_for('browse')}}\"><div class=\"browse-search\"><label for=\"browse-query\">SEARCH FILMS</label><input id=\"browse-query\" name=\"q\" value=\"{{q}}\" type=\"search\" placeholder=\"Title or description\"></div><div><label for=\"cat\">CATEGORY</label><select id=\"cat\" name=\"category\"><option value=\"\">All formats</option>{% for c in categories %}<option value=\"{{c}}\" {% if category==c %}selected{% endif %}>{{c}}</option>{% endfor %}</select></div><div><label for=\"genre\">GENRE</label><select id=\"genre\" name=\"genre\"><option value=\"\">All genres</option>{% for g in genres %}<option value=\"{{g}}\" {% if genre==g %}selected{% endif %}>{{g}}</option>{% endfor %}</select></div><div><label for=\"year\">MOVIE YEAR</label><input id=\"year\" type=\"number\" name=\"year\" min=\"1880\" max=\"2200\" placeholder=\"Any year\" value=\"{{year}}\"></div><div><label for=\"order\">ORDER BY</label><select id=\"order\" name=\"order\"><option value=\"newest\" {% if order=='newest' %}selected{% endif %}>Date added: newest first</option><option value=\"oldest\" {% if order=='oldest' %}selected{% endif %}>Date added: oldest first</option><option value=\"az\" {% if order=='az' %}selected{% endif %}>Alphabetically: A–Z</option><option value=\"za\" {% if order=='za' %}selected{% endif %}>Alphabetically: Z–A</option><option value=\"year_new\" {% if order=='year_new' %}selected{% endif %}>Movie year: newest first</option><option value=\"year_old\" {% if order=='year_old' %}selected{% endif %}>Movie year: oldest first</option><option value=\"updated\" {% if order=='updated' %}selected{% endif %}>Recently updated</option></select></div><button class=\"button primary\">APPLY FILTERS</button><a class=\"button\" href=\"{{url_for('browse')}}\">RESET</a></form>\n<div class=\"browse-subhead\"><strong>{{movies|length}} FILMS</strong><a href=\"{{url_for('category_index')}}\">EXPLORE CATEGORIES →</a></div>\n{% if movies %}<div class=\"movie-grid\">{% for m in movies %}<a class=\"movie-card\" href=\"{{url_for('detail',mid=m.id)}}\"><div class=\"poster-wrap\">{% if m.poster %}<img loading=\"lazy\" src=\"{{url_for('uploads',name=m.poster)}}\" alt=\"Poster for {{m.title}}\">{% else %}<div class=\"poster-placeholder\"><span>◉</span><strong>{{m.title}}</strong></div>{% endif %}<span class=\"movie-type type-{{m.category|lower|replace(' ','-')}}\">{{m.category|upper}}</span></div><div class=\"movie-info\"><h3>{{m.title}}</h3><span class=\"movie-year\">{{m.release_year or 'Year unknown'}}</span>{% if m.synopsis %}<p>{{m.synopsis|truncate(95,True)}}</p>{% endif %}<div class=\"card-meta\"><span>{{m.file_format or m.category}}</span>{% if not m.published %}<span>DRAFT</span>{% endif %}</div></div></a>{% endfor %}</div>{% else %}<div class=\"empty\"><h2>NO FILMS FOUND</h2><p>Try a different search or category.</p></div>{% endif %}</div>{% endblock %}\n","categories.html":"{% extends 'base.html' %}{% block title %}Categories — The Workprint Project{% endblock %}{% block body %}\n<div class=\"shell format-page\"><div class=\"page-intro\"><div><span class=\"eyebrow\">FILM FORMATS / CATEGORIES</span><h1>EXPLORE BY FORMAT</h1><p>Choose a format to see only films in that collection.</p></div></div>\n{% set icons={'Workprint':'🎞','CAM':'📹','35mm':'🎥','Screener':'📺','VHS':'📼','Betamax':'▣','Laserdisc':'💿'} %}\n<div class=\"format-card-grid\">{% for c in categories %}<a class=\"format-card\" href=\"{{url_for('browse',category=c)}}\"><div class=\"format-icon\" aria-hidden=\"true\">{{icons[c]}}</div><div><h2>{{c}}</h2><p>{{counts.get(c,0)}} {{'film' if counts.get(c,0)==1 else 'films'}}</p></div><span class=\"format-arrow\">↗</span></a>{% endfor %}</div>\n</div>{% endblock %}\n","detail.html":"{% extends 'base.html' %}{% block title %}{{movie.title}} | The Workprint Project{% endblock %}{% block body %}\n<div class=\"container detail\"><a class=\"back\" href=\"{{url_for('home')}}\">← BACK TO COLLECTION</a><div class=\"detail-top\"><div class=\"detail-poster\">{% if movie.poster %}<img src=\"{{url_for('uploads',name=movie.poster)}}\" alt=\"Poster for {{movie.title}}\">{% else %}<div class=\"poster-placeholder\">◈<br>WORKPRINT ARCHIVE</div>{% endif %}</div><div><div class=\"eyebrow\">FILM ARCHIVE / {{movie.category|upper}} {% if not movie.published %}· UNPUBLISHED{% endif %}</div><h1>{{movie.title}}</h1><div class=\"tags\"><span>{{movie.category}}</span>{% if movie.release_year %}<span>{{movie.release_year}}</span>{% endif %}{% if movie.genre %}<span>{{movie.genre}}</span>{% endif %}{% if movie.workprint_date %}<span>Edition: {{movie.workprint_date}}</span>{% endif %}</div><p class=\"intro\">{{movie.synopsis or 'No synopsis has been added yet.'}}</p><div class=\"meta-grid\">{% for label,val in [('DIRECTOR',movie.director),('EDITION RUNTIME',movie.runtime),('OFFICIAL RUNTIME',movie.official_runtime),('FILE SIZE',movie.file_size),('FILE FORMAT',movie.file_format),('RESOLUTION',movie.video_resolution),('AUDIO',movie.audio_details),('SOURCE',movie.source_details)] %}{% if val %}<div><span>{{label}}</span><strong>{{val}}</strong></div>{% endif %}{% endfor %}</div>{% if is_admin %}<div class=\"admin-actions\"><a class=\"button\" href=\"{{url_for('edit',mid=movie.id)}}\">Edit entry</a><form method=\"post\" action=\"{{url_for('delete',mid=movie.id)}}\" onsubmit=\"return confirm('Permanently delete this entry?')\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><button class=\"button danger\">Delete entry</button></form></div>{% endif %}</div></div>\n{% if external_available %}<div class=\"detail-section\"><div class=\"eyebrow\">AUTHORISED DISTRIBUTION</div><h2>Download</h2><p>Hosted externally on Pixeldrain. Each accepted link request uses one daily allowance. Pixeldrain has its own download rules.</p>{% if external_token %}<form method=\"post\" action=\"{{url_for('approved_external_request',mid=movie.id)}}\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{external_token}}\"><button class=\"button primary\" type=\"submit\">REQUEST DOWNLOAD</button></form>{% else %}<a class=\"button primary\" href=\"{{url_for('preview_member_login')}}\">SIGN IN TO REQUEST DOWNLOAD</a>{% endif %}</div>{% endif %}<div class=\"detail-section\"><div class=\"eyebrow\">THE DIFFERENCES</div><h2>What changed in this version?</h2><div class=\"prose formatted-differences\">{% if movie.differences %}{{movie.differences|rich_differences(movie.differences_is_html)}}{% else %}<p>Differences from the official release have not been documented yet.</p>{% endif %}</div></div>\n{% if pics %}<div class=\"detail-section\"><div class=\"eyebrow\">VISUAL REFERENCE</div><h2>Edition screenshots <span class=\"count\">{{pics|length}}</span></h2><div class=\"gallery\">{% for pic in pics %}<a href=\"{{url_for('uploads',name=pic.filename)}}\" target=\"_blank\" rel=\"noopener\"><img loading=\"lazy\" src=\"{{url_for('uploads',name=pic.filename)}}\" alt=\"Edition screenshot {{loop.index}}\"><span>{{pic.caption or ('SCREENSHOT %02d'|format(loop.index))}} ↗</span></a>{% endfor %}</div></div>{% endif %}\n{% if movie.notes %}<div class=\"detail-section\"><div class=\"eyebrow\">ARCHIVIST NOTES</div><h2>Additional notes</h2><div class=\"prose\">{{movie.notes}}</div></div>{% endif %}</div>\n{% endblock %}\n","article.html":"{% extends 'base.html' %}{% block title %}{{article.title}} — News{% endblock %}{% block body %}<div class=\"shell article-page\">{% if private_preview %}<p class=\"flash\" style=\"padding:14px;border:1px solid #294977\">PRIVATE ADMIN PREVIEW · Saved article only · <a href=\"{{url_for('preview_news_edit',aid=article.id)}}\">BACK TO EDITOR</a></p>{% else %}<a class=\"back-link\" href=\"{{url_for('home')}}\">← BACK TO NEWS</a>{% endif %}<div class=\"article-meta\"><span class=\"news-tag {% if article.status=='coming_soon' %}upcoming{% endif %}\">{{'COMING SOON' if article.status=='coming_soon' else 'ARCHIVE NEWS'}}</span><time>{{article.created_at[:10]}}</time>{% if not article.published %}<span class=\"news-tag upcoming\">DRAFT</span>{% endif %}</div><h1>{{article.title}}</h1>{% if article.excerpt %}<p class=\"article-standfirst\">{{article.excerpt}}</p>{% endif %}{% if article.cover %}<img class=\"article-cover\" src=\"{{url_for('preview_news_cover_view',aid=article.id) if private_preview else url_for('uploads',name=article.cover)}}\" alt=\"\">{% endif %}<div class=\"article-content\">{{article.body|rich_differences(1)}}</div>{% if is_admin %}<div class=\"admin-actions\"><a class=\"button\" href=\"{{url_for('article_edit',aid=article.id)}}\">EDIT ARTICLE</a><form method=\"post\" action=\"{{url_for('article_delete',aid=article.id)}}\" onsubmit=\"return confirm('Delete this news article?')\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><button type=\"submit\" class=\"button danger\">DELETE</button></form></div>{% endif %}</div>{% endblock %}\n","preview_admin_login.html":"{% extends 'base.html' %}{% block title %}Admin sign-in — The Workprint Project{% endblock %}{% block body %}<div class=\"shell member-panel\"><div class=\"member-box\"><h1>ADMIN LOGIN</h1><p>Cloudflare preview — authorised administrators only.</p>{% if error %}<p class=\"flash error\" role=\"alert\">{{error}}</p>{% endif %}{% if configured %}<form class=\"member-form\" method=\"post\" action=\"{{url_for('preview_admin_login')}}\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><label for=\"password\">Admin password</label><input id=\"password\" name=\"password\" type=\"password\" autocomplete=\"current-password\" required maxlength=\"512\"><button class=\"button primary full\" type=\"submit\">SIGN IN</button></form>{% else %}<p>Admin sign-in is unavailable. Check the Worker secrets and database configuration.</p>{% endif %}</div></div>{% endblock %}","preview_admin_dashboard.html":"{% extends 'base.html' %}{% block title %}Admin dashboard — The Workprint Project{% endblock %}{% block body %}<div class=\"shell member-panel\"><div class=\"page-intro\"><div><span class=\"eyebrow\">CLOUDFLARE / ADMINISTRATION</span><h1>ADMIN DASHBOARD</h1><p>Signed in successfully. Film metadata management is now available for testing.</p></div><form method=\"post\" action=\"{{url_for('preview_admin_logout')}}\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><button class=\"button\">SIGN OUT</button></form></div><div class=\"member-card-row\">{% for label,count in counts %}<div class=\"member-card\"><span>{{label}}</span><strong>{{count}}</strong></div>{% endfor %}</div><p>Manage film metadata and publication status. Drafts are private. Poster and screenshot uploads are now available for testing. Member management is available for testing; member sign-in and registration are available for testing after the private helper upgrade.</p><a class=\"button primary\" href=\"{{url_for('preview_film_manager')}}\">MANAGE FILMS</a> <a class=\"button\" href=\"{{url_for('preview_film_new')}}\">+ ADD DRAFT FILM</a> <a class=\"button primary\" href=\"{{url_for('preview_news_manager')}}\">MANAGE NEWS</a> <a class=\"button primary\" href=\"{{url_for('preview_member_manager')}}\">MANAGE MEMBERS</a> <a class=\"button primary\" href=\"{{url_for('approved_downloads_admin')}}\">MANAGE DOWNLOADS</a> <a class=\"button primary\" href=\"{{url_for('preview_inbox')}}\">MESSAGES</a> <a class=\"button\" href=\"{{url_for('preview_member_check')}}\">PASSWORD COMPATIBILITY TEST</a> <a class=\"button\" href=\"{{url_for('browse')}}\">VIEW CATALOGUE</a> <a class=\"button\" href=\"{{url_for('preview_member_account')}}\">TEST MEMBER ALLOWANCE</a></div>{% endblock %}","preview_film_manager.html":"{% extends 'base.html' %}{% block title %}Manage films — The Workprint Project{% endblock %}{% block body %}<div class=\"shell member-panel\"><div class=\"page-intro\"><div><span class=\"eyebrow\">CLOUDFLARE / ADMINISTRATION</span><h1>MANAGE FILMS</h1><p>Add films, edit metadata and manage publication status. Unpublish a film before deleting it; records with request history are protected.</p></div><a class=\"button primary\" href=\"{{url_for('preview_film_new')}}\">+ ADD DRAFT FILM</a></div><p><a class=\"button\" href=\"{{url_for('preview_admin_dashboard')}}\">BACK TO ADMIN</a></p>{% if request.args.get('deleted')=='1' %}<p class=\"flash success\" role=\"status\">Draft deleted successfully.</p>{% endif %}<div class=\"member-table-wrap\"><table class=\"member-table\"><thead><tr><th>Title</th><th>Category</th><th>Year</th><th>Status</th><th>Action</th></tr></thead><tbody>{% for m in films %}<tr><td>{{m.title}}</td><td>{{m.category}}</td><td>{{m.release_year or '—'}}</td><td>{{'Published' if m.published else 'Draft'}}</td><td><a href=\"{{url_for('preview_film_edit',mid=m.id)}}\">Edit</a> · <a href=\"{{url_for('preview_film_images',mid=m.id)}}\">Images</a>{% if m.published %} · <a href=\"{{url_for('detail',mid=m.id)}}\">View</a>{% endif %}</td></tr>{% endfor %}</tbody></table></div></div>{% endblock %}","preview_film_form.html":"{% extends 'base.html' %}{% block title %}Draft film — The Workprint Project{% endblock %}{% block body %}<div class=\"shell member-panel\"><div class=\"member-box\" style=\"width:min(100%,900px)\"><h1>{{'EDIT FILM' if movie.id else 'ADD DRAFT FILM'}}</h1><p>{% if movie.id %}Status: <strong>{{'Published' if movie.published else 'Private draft'}}</strong>. Edits change the Cloudflare copy only; existing images and links are retained.{% else %}New films are saved as private drafts. They can be published after saving.{% endif %}</p>{% if saved %}<p role=\"status\">Film saved successfully.</p>{% endif %}{% if error %}<p class=\"flash error\" role=\"alert\">{{error}}</p>{% endif %}<form class=\"member-form\" method=\"post\" action=\"{{url_for('preview_film_edit',mid=movie.id) if movie.id else url_for('preview_film_new')}}\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><input type=\"hidden\" name=\"updated_at\" value=\"{{movie.updated_at or ''}}\"><label for=\"title\">Film title</label><input id=\"title\" name=\"title\" value=\"{{movie.title or ''}}\" maxlength=\"200\" required><label for=\"category\">Category</label><select id=\"category\" name=\"category\" required>{% for category in categories_nav %}<option value=\"{{category}}\" {% if movie.category==category %}selected{% endif %}>{{category}}</option>{% endfor %}</select><label for=\"release_year\">Release year</label><input id=\"release_year\" name=\"release_year\" type=\"number\" min=\"1880\" max=\"2200\" value=\"{{movie.release_year or ''}}\">{% for name,label,limit,multiline in fields %}<label for=\"{{name}}\">{{label}}</label>{% if multiline %}<textarea id=\"{{name}}\" name=\"{{name}}\" maxlength=\"{{[limit,(movie[name] or '')|length]|max}}\" rows=\"5\" style=\"width:100%;background:#08162f;color:#fff;border:1px solid #2d4c75;padding:13px;border-radius:6px\">{{movie[name] or ''}}</textarea>{% if name=='differences' %}<input type=\"hidden\" id=\"differences_visual\" name=\"differences_visual\" value=\"0\">{% with editor_value=movie.differences,editor_html=movie.differences_is_html %}{% include 'rich_editor.html' %}{% endwith %}{% with editor_field='differences' %}{% include 'rich_editor_script.html' %}{% endwith %}{% endif %}{% else %}<input id=\"{{name}}\" name=\"{{name}}\" maxlength=\"{{limit}}\" value=\"{{movie[name] or ''}}\">{% endif %}{% endfor %}<button class=\"button primary full\" type=\"submit\">{{'SAVE CHANGES' if movie.id else 'SAVE PRIVATE DRAFT'}}</button><a class=\"button full\" href=\"{{url_for('preview_film_manager')}}\">BACK TO FILMS</a></form>{% if movie.id %}<hr style=\"margin:32px 0\"><h2>POSTERS &amp; SCREENSHOTS</h2><p>Save metadata changes before opening the image manager.</p><a class=\"button primary\" href=\"{{url_for('preview_film_images',mid=movie.id)}}\">MANAGE IMAGES</a><hr style=\"margin:32px 0\"><h2>AUTHORISED EXTERNAL DOWNLOAD</h2><p>Set up a separate, rights-cleared Pixeldrain file. Imported archive links stay disabled.</p><a class=\"button\" href=\"{{url_for('approved_external_settings',mid=movie.id)}}\">MANAGE PIXELDRAIN LINK</a><hr style=\"margin:32px 0\"><h2>PUBLICATION STATUS</h2><p>Changing the status does not delete records, images or history. Save any metadata changes above first.</p><form class=\"member-form\" method=\"post\" action=\"{{url_for('preview_film_visibility',mid=movie.id)}}\" onsubmit=\"return confirm('Change publication status of this film?')\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><input type=\"hidden\" name=\"updated_at\" value=\"{{movie.updated_at}}\"><input type=\"hidden\" name=\"published\" value=\"{{0 if movie.published else 1}}\"><button class=\"button\" type=\"submit\">{{'UNPUBLISH FILM (KEEP DRAFT)' if movie.published else 'PUBLISH FILM'}}</button></form>{% if not movie.published %}<hr style=\"margin:32px 0\"><h2>DELETE DRAFT</h2><p>Permanently remove this private film record from Cloudflare. Its image files are retained in private storage.</p><a class=\"button danger\" href=\"{{url_for('preview_delete_draft',kind='film',rid=movie.id)}}\">DELETE DRAFT FILM</a>{% endif %}{% endif %}</div></div>{% endblock %}","preview_film_images.html":"{% extends 'base.html' %}{% block title %}Film images — The Workprint Project{% endblock %}{% block body %}<div class=\"shell member-panel\"><div class=\"page-intro\"><div><span class=\"eyebrow\">CLOUDFLARE / ADMINISTRATION</span><h1>MANAGE IMAGES</h1><p>{{movie.title}} · {{'Published' if movie.published else 'Private draft'}}</p></div><a class=\"button\" href=\"{{url_for('preview_film_edit',mid=movie.id)}}\">BACK TO FILM</a></div>{% if saved %}<p class=\"flash success\" role=\"status\">Image saved successfully.</p>{% endif %}{% if error %}<p class=\"flash error\" role=\"alert\">{{error}}</p>{% endif %}<p>Choose one JPG, PNG, WebP or GIF at a time, up to 5 MiB. Only administrators can upload. Existing image files are not deleted when a poster is replaced.</p><section class=\"two-col\" style=\"display:flex;gap:24px;flex-wrap:wrap\"><div class=\"member-box\" style=\"flex:1;min-width:260px\"><h2>POSTER</h2>{% if movie.poster %}<img style=\"max-width:220px;max-height:330px;object-fit:contain\" src=\"{{url_for('preview_admin_image',mid=movie.id,name=movie.poster)}}\" alt=\"Current poster\">{% else %}<p>No poster yet.</p>{% endif %}<form class=\"member-form\" method=\"post\" enctype=\"multipart/form-data\" action=\"{{url_for('preview_film_images',mid=movie.id)}}\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><input type=\"hidden\" name=\"updated_at\" value=\"{{movie.updated_at}}\"><input type=\"hidden\" name=\"kind\" value=\"poster\"><label for=\"poster\">Select poster</label><input id=\"poster\" name=\"image\" type=\"file\" accept=\"image/png,image/jpeg,image/webp,image/gif\" required><button type=\"submit\" class=\"button primary\">UPLOAD POSTER</button></form></div><div class=\"member-box\" style=\"flex:1;min-width:260px\"><h2>ADD SCREENSHOT</h2><form class=\"member-form\" method=\"post\" enctype=\"multipart/form-data\" action=\"{{url_for('preview_film_images',mid=movie.id)}}\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><input type=\"hidden\" name=\"kind\" value=\"screenshot\"><label for=\"screenshot\">Choose screenshot</label><input id=\"screenshot\" name=\"image\" type=\"file\" accept=\"image/png,image/jpeg,image/webp,image/gif\" required><label for=\"caption\">Caption (optional)</label><input id=\"caption\" name=\"caption\" maxlength=\"200\"><button type=\"submit\" class=\"button primary\">UPLOAD SCREENSHOT</button></form></div></section><h2>EXISTING SCREENSHOTS ({{pics|length}})</h2><div class=\"gallery\">{% for pic in pics %}<a href=\"{{url_for('preview_admin_image',mid=movie.id,name=pic.filename)}}\"><img loading=\"lazy\" src=\"{{url_for('preview_admin_image',mid=movie.id,name=pic.filename)}}\" alt=\"{{pic.caption or 'Screenshot'}}\"><span>{{pic.caption or 'Screenshot'}}</span></a>{% else %}<p>No screenshots yet.</p>{% endfor %}</div></div>{% endblock %}","preview_news_manager.html":"{% extends 'base.html' %}{% block title %}Manage news — The Workprint Project{% endblock %}{% block body %}<div class=\"shell member-panel\"><div class=\"page-intro\"><div><span class=\"eyebrow\">CLOUDFLARE / ADMINISTRATION</span><h1>MANAGE NEWS</h1><p>Manage articles and private drafts. Unpublish an article before deleting it.</p></div><a class=\"button primary\" href=\"{{url_for('preview_news_new')}}\">+ WRITE ARTICLE</a></div><p><a class=\"button\" href=\"{{url_for('preview_admin_dashboard')}}\">BACK TO ADMIN</a></p>{% if request.args.get('deleted')=='1' %}<p class=\"flash success\" role=\"status\">Draft deleted successfully.</p>{% endif %}<div class=\"member-table-wrap\"><table class=\"member-table\"><thead><tr><th>Title</th><th>Date</th><th>Status</th><th>Action</th></tr></thead><tbody>{% for a in articles %}<tr><td>{{a.title}}</td><td>{{a.created_at[:10]}}</td><td>{{'Published' if a.published else 'Draft'}}</td><td><a href=\"{{url_for('preview_news_edit',aid=a.id)}}\">Edit</a> · <a href=\"{{url_for('preview_news_view',aid=a.id)}}\">Preview</a>{% if a.published %} · <a href=\"{{url_for('article_detail',aid=a.id)}}\">View</a>{% endif %}</td></tr>{% endfor %}</tbody></table></div></div>{% endblock %}","preview_news_form.html":"{% extends 'base.html' %}{% block title %}News editor — The Workprint Project{% endblock %}{% block body %}<div class=\"shell member-panel\"><div class=\"member-box\" style=\"width:min(100%,1000px)\"><h1>{{'EDIT ARTICLE' if article.id else 'WRITE ARTICLE'}}</h1><p>{{'Published' if article.published else 'Private draft'}} · changes affect the Cloudflare copy only.</p>{% if saved %}<p class=\"flash success\" role=\"status\">Article saved successfully.</p>{% endif %}{% if error %}<p class=\"flash error\" role=\"alert\">{{error}}</p>{% endif %}<form class=\"member-form\" method=\"post\" action=\"{{url_for('preview_news_edit',aid=article.id) if article.id else url_for('preview_news_new')}}\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><input type=\"hidden\" name=\"updated_at\" value=\"{{article.updated_at or ''}}\"><label for=\"title\">Article title</label><input id=\"title\" name=\"title\" required maxlength=\"200\" value=\"{{article.title}}\"><label for=\"excerpt\">Short summary</label><textarea id=\"excerpt\" name=\"excerpt\" rows=\"3\" maxlength=\"500\">{{article.excerpt or ''}}</textarea><label for=\"status\">Article type</label><select id=\"status\" name=\"status\"><option value=\"published\" {% if article.status=='published' %}selected{% endif %}>Archive news</option><option value=\"coming_soon\" {% if article.status=='coming_soon' %}selected{% endif %}>Coming soon</option></select><label for=\"body\">Article body</label><textarea id=\"body\" name=\"body\" rows=\"16\" maxlength=\"150000\" style=\"width:100%;background:#08162f;color:#fff;border:1px solid #2d4c75;padding:13px\">{{article.body or ''}}</textarea>{% with editor_value=article.body,editor_html=1 %}{% include 'rich_editor.html' %}{% endwith %}{% with editor_field='body' %}{% include 'rich_editor_script.html' %}{% endwith %}<label for=\"video\">Append a YouTube video (optional, video ID only)</label><input id=\"video\" name=\"video\" maxlength=\"11\" placeholder=\"11-character YouTube video ID\"><label><input style=\"width:auto\" type=\"checkbox\" name=\"published\" value=\"1\" {% if article.published %}checked{% endif %}> Publish this article</label><button type=\"submit\" class=\"button primary\">{{'SAVE ARTICLE' if article.id else 'CREATE ARTICLE'}}</button></form>{% if article.id %}<p><a class=\"button\" href=\"{{url_for('preview_news_view',aid=article.id)}}\">PREVIEW SAVED ARTICLE</a></p><small>Save your changes first. This preview is private, including unpublished articles.</small><hr style=\"margin:26px 0\"><h2>COVER IMAGE</h2>{% if article.cover %}<img src=\"{{url_for('preview_news_cover_view',aid=article.id)}}\" alt=\"Current cover\" style=\"max-width:100%;max-height:300px\">{% endif %}<form method=\"post\" class=\"member-form\" enctype=\"multipart/form-data\" action=\"{{url_for('preview_news_cover',aid=article.id)}}\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><input type=\"hidden\" name=\"updated_at\" value=\"{{article.updated_at}}\"><label for=\"cover\">Upload cover (max 5 MiB)</label><input id=\"cover\" type=\"file\" name=\"image\" accept=\"image/png,image/jpeg,image/webp,image/gif\" required><button type=\"submit\" class=\"button primary\">UPLOAD COVER</button></form>{% endif %}{% if article.id and not article.published %}<hr style=\"margin:32px 0\"><h2>DELETE DRAFT</h2><p>Permanently remove this private article from Cloudflare. Its cover file is retained in private storage.</p><a class=\"button danger\" href=\"{{url_for('preview_delete_draft',kind='article',rid=article.id)}}\">DELETE DRAFT ARTICLE</a>{% endif %}<p><a class=\"button\" href=\"{{url_for('preview_news_manager')}}\">BACK TO NEWS</a></p></div></div>{% endblock %}","preview_member_manager.html":"{% extends 'base.html' %}{% block title %}Manage members — The Workprint Project{% endblock %}{% block body %}<div class=\"shell member-panel\"><div class=\"page-intro\"><div><span class=\"eyebrow\">CLOUDFLARE / ADMINISTRATION</span><h1>MANAGE MEMBERS</h1><p>Existing accounts and history from the imported database. Member sign-in and registration are in testing.</p></div><a class=\"button\" href=\"{{url_for('preview_admin_dashboard')}}\">BACK TO ADMIN</a></div><form method=\"get\" class=\"member-search\"><input name=\"q\" maxlength=\"120\" value=\"{{q}}\" placeholder=\"Search username or email\"><button class=\"button\">SEARCH</button></form><div class=\"member-table-wrap\"><table class=\"member-table\"><thead><tr><th>Username</th><th>Email</th><th>Joined</th><th>Status</th><th>Daily allowance</th><th>Link requests</th><th>Action</th></tr></thead><tbody>{% for m in members %}<tr><td>{{m.username}}</td><td>{{m.email}}</td><td>{{m.created_at[:10]}}</td><td>{{'Suspended' if m.suspended else 'Active'}}</td><td>{{m.daily_limit if m.daily_limit is not none else 'Default (3)'}}</td><td>{{m.total}}</td><td><a href=\"{{url_for('preview_member_detail',mid=m.id)}}\">Manage</a></td></tr>{% endfor %}</tbody></table></div></div>{% endblock %}","preview_member_detail.html":"{% extends 'base.html' %}{% block title %}Member settings — The Workprint Project{% endblock %}{% block body %}<div class=\"shell member-panel\"><div class=\"page-intro\"><div><span class=\"eyebrow\">CLOUDFLARE / ADMINISTRATION</span><h1>{{record.username}}</h1><p>{{record.email}} · {{'Suspended' if record.suspended else 'Active'}}</p></div><a class=\"button\" href=\"{{url_for('preview_member_manager')}}\">BACK TO MEMBERS</a></div>{% if saved %}<p class=\"flash success\">Member settings saved.</p>{% endif %}<div class=\"member-box\"><h2>ACCOUNT SETTINGS</h2><p>Changes apply to the Cloudflare copy only. No passwords are displayed or reset.</p><form class=\"member-form\" method=\"post\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><input type=\"hidden\" name=\"expected_suspended\" value=\"{{record.suspended}}\"><input type=\"hidden\" name=\"expected_limit\" value=\"{{record.daily_limit if record.daily_limit is not none else 'default'}}\"><label for=\"suspended\">Account status</label><select id=\"suspended\" name=\"suspended\"><option value=\"0\" {% if not record.suspended %}selected{% endif %}>Active</option><option value=\"1\" {% if record.suspended %}selected{% endif %}>Suspended</option></select><label for=\"limit\">Daily request allowance</label><input id=\"limit\" name=\"limit\" maxlength=\"7\" required value=\"{{record.daily_limit if record.daily_limit is not none else 'default'}}\"><small>Enter default (3) or a number from 1 to 50. Limits are enforced in the simulated request test; live downloads remain disabled.</small><button class=\"button primary\">SAVE SETTINGS</button></form></div><h2>DOWNLOAD REQUEST HISTORY</h2><div class=\"member-table-wrap\"><table class=\"member-table\"><thead><tr><th>Film</th><th>Requested</th><th>Provider</th></tr></thead><tbody>{% for h in history %}<tr><td>{{h.movie_title}}</td><td>{{h.requested_at}}</td><td>{{h.provider}}</td></tr>{% else %}<tr><td colspan=\"3\">No requests recorded.</td></tr>{% endfor %}</tbody></table></div></div>{% endblock %}","preview_member_check.html":"{% extends 'base.html' %}{% block title %}Password compatibility — The Workprint Project{% endblock %}{% block body %}<div class=\"shell member-panel\"><div class=\"member-box\"><h1>PASSWORD COMPATIBILITY</h1><p>Tests use a fixed dummy password, never real member credentials.</p>{% if result %}<p class=\"flash {{'success' if result=='passed' else 'error'}}\">Legacy scrypt verification: {{result}}</p>{% endif %}<p>Imported password hash formats:</p><ul>{% for item in formats %}<li>{{item.method}}: {{item.total}} accounts</li>{% endfor %}</ul><form class=\"member-form\" method=\"post\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><button class=\"button primary\" type=\"submit\">RUN COMPATIBILITY TEST</button></form><p><a class=\"button\" href=\"{{url_for('preview_admin_dashboard')}}\">BACK TO ADMIN</a></p></div></div>{% endblock %}","preview_member_auth.html":"{% extends 'base.html' %}{% block title %}Member {{'registration' if register else 'login'}} — The Workprint Project{% endblock %}{% block body %}<div class=\"shell member-panel\"><div class=\"member-box\"><h1>{{'CREATE ACCOUNT' if register else 'MEMBER LOGIN'}}</h1><p>Free membership · Cloudflare staging test, not the live archive. Downloads are disabled.</p>{% if error %}<p class=\"flash error\" role=\"alert\">{{error}}</p>{% endif %}<form class=\"member-form\" method=\"post\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\">{% if register %}<label for=\"username\">Username</label><input id=\"username\" name=\"username\" autocomplete=\"username\" minlength=\"3\" maxlength=\"32\" required><label for=\"email\">Email</label><input id=\"email\" type=\"email\" name=\"email\" autocomplete=\"email\" maxlength=\"254\" required><small>Use your own email address. This preview does not verify email ownership yet.</small><div class=\"trap\" aria-hidden=\"true\"><input name=\"website\" tabindex=\"-1\" autocomplete=\"off\"></div>{% else %}<label for=\"login\">Username or email</label><input id=\"login\" name=\"login\" autocomplete=\"username\" maxlength=\"254\" required>{% endif %}<label for=\"password\">Password</label><input id=\"password\" name=\"password\" type=\"password\" maxlength=\"256\" autocomplete=\"{{'new-password' if register else 'current-password'}}\" required>{% if register %}<label for=\"confirm\">Confirm password</label><input id=\"confirm\" name=\"confirm\" type=\"password\" autocomplete=\"new-password\" maxlength=\"256\" required><small>At least 12 characters.</small>{% endif %}<button class=\"button primary full\">{{'REGISTER' if register else 'SIGN IN'}}</button></form><p>{% if register %}Already registered? <a href=\"{{url_for('preview_member_login')}}\">Sign in</a>{% else %}New member? <a href=\"{{url_for('preview_member_register')}}\">Create a free account</a>{% endif %}</p></div></div>{% endblock %}","preview_member_account.html":"{% extends 'base.html' %}{% block title %}My account — The Workprint Project{% endblock %}{% block body %}<div class=\"shell member-panel\"><div class=\"page-intro\"><div><span class=\"eyebrow\">MEMBERS / ACCOUNT</span><h1>MY ACCOUNT</h1><p>Welcome, {{record.username}}. Your membership is free.</p></div><form method=\"post\" action=\"{{url_for('preview_member_logout')}}\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><button class=\"button\">SIGN OUT</button></form></div><div class=\"member-card-row\"><div class=\"member-card\"><span>DAILY ALLOWANCE</span><strong>{{limit}}</strong><small>{{used}} used today · {{remaining}} remaining. Resets at midnight UK time. Film downloads remain unavailable. Original project documentation is available below.</small></div><div class=\"member-card\"><span>LINK REQUESTS RECORDED</span><strong>{{total}}</strong></div></div><div class=\"member-box\" style=\"margin:24px 0;max-width:100%\"><h2>AVAILABLE DOWNLOADS</h2><p>Original and authorised project documents. Each accepted file request uses one daily allowance.</p>{% if guide_limited %}<p class=\"flash error\" role=\"alert\">Daily allowance reached. No file was delivered or request recorded.</p>{% endif %}<h3>WORKPRINT PROJECT — ARCHIVE GUIDE</h3><p>Original text guide to documenting alternative film editions. TXT · No film footage or third-party file links.</p><form method=\"post\" action=\"{{url_for('member_original_guide')}}\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{guide_token}}\"><button type=\"submit\" class=\"button primary\" {% if not remaining %}disabled{% endif %}>DOWNLOAD GUIDE (.TXT)</button></form><p class=\"tiny\">Refresh your account after downloading to see the updated allowance and history.</p></div>{% if approved_files %}<div class=\"member-box\" style=\"margin:24px 0;max-width:100%\"><h2>AUTHORISED DOCUMENTS</h2>{% for file in approved_files %}<div style=\"margin:20px 0\"><h3>{{file.title}}</h3><p>{{file.filename}} · {{file.size}} bytes</p><form method=\"post\" action=\"{{url_for('approved_download',fid=file.id)}}\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{approved_token}}\"><button type=\"submit\" class=\"button primary\" {% if not remaining %}disabled{% endif %}>DOWNLOAD FILE</button></form></div>{% endfor %}</div>{% endif %}{% if quota_test_token %}<div class=\"member-box\" style=\"margin:24px 0;max-width:100%\"><h2>DOWNLOAD ALLOWANCE TEST</h2><p>Administrator-only staging test. Use your test member account. Requests exercise the real quota and history tables but do not deliver a film or reveal a download link.</p>{% if test_result=='accepted' %}<p class=\"flash success\" role=\"status\">Test request accepted and recorded.</p>{% elif test_result=='limit' %}<p class=\"flash error\" role=\"status\">Daily allowance reached. No request recorded.</p>{% elif test_result=='cleared' %}<p class=\"flash success\" role=\"status\">Your migration test requests have been cleared.</p>{% endif %}<form method=\"post\" class=\"member-form\" action=\"{{url_for('preview_quota_test')}}\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{quota_test_token}}\"><button class=\"button primary\" type=\"submit\" name=\"action\" value=\"request\">SIMULATE DOWNLOAD REQUEST</button><button class=\"button\" type=\"submit\" name=\"action\" value=\"clear\">CLEAR TEST REQUESTS</button></form></div>{% endif %}<h2>YOUR REQUEST HISTORY</h2><div class=\"member-table-wrap\"><table class=\"member-table\"><thead><tr><th>Film</th><th>Date</th><th>Provider</th></tr></thead><tbody>{% for h in history %}<tr><td>{{h.movie_title}}</td><td>{{h.requested_at}}</td><td>{{h.provider}}</td></tr>{% else %}<tr><td colspan=\"3\">No requests recorded.</td></tr>{% endfor %}</tbody></table></div><p><a class=\"button primary\" href=\"{{url_for('browse')}}\">VIEW CATALOGUE</a></p></div>{% endblock %}","preview_contact.html":"{% extends 'base.html' %}{% block title %}Contact — The Workprint Project{% endblock %}{% block body %}<div class=\"shell member-panel\"><div class=\"member-box\" style=\"width:min(100%,850px)\"><h1>CONTACT US</h1><p>Questions, archive information, corrections or rights enquiries? Send us a message. This is the Cloudflare staging copy.</p>{% if sent %}<p class=\"flash success\" role=\"status\">Message received. Thank you for contacting us!</p>{% endif %}{% if error %}<p class=\"flash error\" role=\"alert\">{{error}}</p>{% endif %}<form class=\"member-form\" method=\"post\" action=\"{{url_for('preview_contact')}}\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><div style=\"position:absolute;left:-10000px;width:1px;height:1px;overflow:hidden\" aria-hidden=\"true\"><label>Leave blank<input name=\"website\" tabindex=\"-1\" autocomplete=\"off\"></label></div><label for=\"name\">Your name</label><input id=\"name\" name=\"name\" maxlength=\"120\" autocomplete=\"name\" required value=\"{{values.name}}\"><label for=\"email\">Email address</label><input id=\"email\" name=\"email\" type=\"email\" maxlength=\"254\" autocomplete=\"email\" required value=\"{{values.email}}\"><label for=\"subject\">Subject</label><input id=\"subject\" name=\"subject\" maxlength=\"140\" required value=\"{{values.subject}}\"><label for=\"message\">Message</label><textarea id=\"message\" name=\"message\" maxlength=\"5000\" rows=\"8\" required style=\"width:100%;padding:14px;background:#08162f;color:white;border:1px solid #2d4c75;border-radius:6px\">{{values.message}}</textarea><small>Your message and contact details are stored in the private administrator inbox for responding to your enquiry.</small><button class=\"button primary\" type=\"submit\">SEND MESSAGE</button></form></div></div>{% endblock %}","preview_donate.html":"{% extends 'base.html' %}{% block title %}Support the archive — The Workprint Project{% endblock %}{% block body %}<div class=\"shell member-panel\"><div class=\"member-box\" style=\"width:min(100%,850px)\"><h1>SUPPORT THE PROJECT</h1><p>Voluntary donations help with the costs of maintaining the website, storage and documenting film history. Membership is free, and donations do not purchase films or access to copyrighted material.</p>{% if donation_url %}<p><a class=\"button primary\" href=\"{{donation_url}}\" rel=\"noopener noreferrer\">SUPPORT US ON KO-FI</a></p><small>Payments are handled externally by Ko-fi.</small>{% else %}<p>Our donation link is not configured on this preview yet.</p>{% endif %}<p><a href=\"{{url_for('home')}}\">BACK TO NEWS</a></p></div></div>{% endblock %}","preview_inbox.html":"{% extends 'base.html' %}{% block title %}Admin inbox — The Workprint Project{% endblock %}{% block body %}<div class=\"shell member-panel\"><div class=\"page-intro\"><div><span class=\"eyebrow\">CLOUDFLARE / ADMINISTRATION</span><h1>MESSAGES</h1><p>Private contact inbox · {{unread}} unread messages.</p></div><a class=\"button\" href=\"{{url_for('preview_admin_dashboard')}}\">BACK TO ADMIN</a></div>{% if saved %}<p class=\"flash success\">Message marked as read.</p>{% endif %}{% for m in messages %}<article class=\"member-box\" style=\"width:100%;max-width:none;margin:20px 0\"><p class=\"tiny\">{{m.created_at}} · {{'Read' if m.read else 'Unread'}}</p><h2>{{m.subject}}</h2><p>{{m.name}} · {{m.email}}</p><p style=\"white-space:pre-wrap;overflow-wrap:anywhere\">{{m.message}}</p>{% if not m.read %}<form method=\"post\" action=\"{{url_for('preview_inbox_read',mid=m.id)}}\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><button class=\"button\" type=\"submit\">MARK AS READ</button></form>{% endif %}</article>{% else %}<p>No messages received.</p>{% endfor %}{% if has_more %}<p><a class=\"button\" href=\"{{url_for('preview_inbox',before=messages[-1].id)}}\">OLDER MESSAGES</a></p>{% endif %}</div>{% endblock %}","rich_editor.html":"<div data-rich-editor style=\"margin:10px 0 18px\"><div data-toolbar hidden style=\"display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px\">{% for cmd,label in [('bold','Bold'),('italic','Italic'),('underline','Underline'),('heading','Heading'),('paragraph','Paragraph'),('insertUnorderedList','Bullets'),('insertOrderedList','Numbered list'),('createLink','Link'),('unlink','Remove link'),('undo','Undo'),('redo','Redo'),('video','YouTube')] %}<button class=\"button\" type=\"button\" data-command=\"{{cmd}}\" style=\"padding:8px 12px\">{{label}}</button>{% endfor %}</div><div data-editable hidden contenteditable=\"true\" role=\"textbox\" aria-label=\"Formatted content\" aria-multiline=\"true\" style=\"min-height:260px;padding:16px;background:#08162f;color:white;border:1px solid #2d4c75;border-radius:6px;overflow-wrap:anywhere;white-space:pre-wrap\">{{editor_value|editor_safe_html(editor_html)}}</div><small data-editor-note hidden>Use the toolbar or paste plain text. Place your cursor where a YouTube video should appear. Save the form to keep changes.</small></div>","rich_editor_script.html":"<script>\n(function(){\n  const root=document.querySelector('[data-rich-editor]'), field=document.getElementById('{{editor_field}}');\n  if(!root||!field) return;\n  const box=root.querySelector('[data-editable]'), bar=root.querySelector('[data-toolbar]');\n  const hidden=document.getElementById('differences_visual');\n  let dirty=false;\n  const sync=()=>{dirty=true;field.value=box.innerHTML;if(hidden)hidden.value='1';};\n  box.hidden=false;bar.hidden=false;root.querySelector('[data-editor-note]').hidden=false;\n  field.hidden=true;field.style.display='none';\n  box.addEventListener('input',sync);\n  box.addEventListener('paste',e=>{e.preventDefault();document.execCommand('insertText',false,e.clipboardData.getData('text/plain'));sync();});\n  box.addEventListener('drop',e=>e.preventDefault());\n  box.addEventListener('click',e=>{if(e.target.closest('a'))e.preventDefault();});\n  bar.addEventListener('mousedown',e=>{if(e.target.closest('button'))e.preventDefault();});\n  function focusSelection(){\n    const selection=window.getSelection();\n    if(!selection||!selection.rangeCount||!box.contains(selection.anchorNode)||!box.contains(selection.focusNode)){\n      box.focus();const r=document.createRange();r.selectNodeContents(box);r.collapse(false);\n      if(selection){selection.removeAllRanges();selection.addRange(r);}\n    }else box.focus();\n  }\n  function videoId(input){\n    if(/^[A-Za-z0-9_-]{11}$/.test(input))return input;\n    try{\n      const u=new URL(input);\n      if(!['https:','http:'].includes(u.protocol))return '';\n      let id='';\n      if(u.hostname==='youtu.be')id=u.pathname.split('/')[1];\n      else if(['youtube.com','www.youtube.com','m.youtube.com'].includes(u.hostname)){\n        id=u.searchParams.get('v')||(/^\\/(shorts|embed|live)\\//.test(u.pathname)?u.pathname.split('/')[2]:'');\n      }\n      return /^[A-Za-z0-9_-]{11}$/.test(id||'')?id:'';\n    }catch{return '';}\n  }\n  bar.addEventListener('click',e=>{\n    const button=e.target.closest('[data-command]');if(!button)return;\n    const cmd=button.dataset.command;\n    focusSelection();\n    try { document.execCommand('styleWithCSS',false,false); } catch (_) {}\n    if(cmd==='video'){\n      const input=prompt('Paste a YouTube video URL or its 11-character ID');\n      if(input===null)return;\n      const id=videoId(input.trim());\n      if(!id){alert('Please enter a valid YouTube video URL or ID.');return;}\n      focusSelection();\n      document.execCommand('insertHTML',false,'<p><span class=\"youtube-embed\" data-youtube-id=\"'+id+'\">[YouTube video: '+id+']</span></p><p><br></p>');\n    }else if(cmd==='createLink'){\n      const input=prompt('Enter an HTTPS or HTTP link');\n      if(!input)return;\n      try{const url=new URL(input);if(!['https:','http:'].includes(url.protocol))throw Error();focusSelection();document.execCommand('createLink',false,url.href);}catch{alert('Enter a valid web address.');return;}\n    }else if(cmd==='heading'||cmd==='paragraph'){\n      document.execCommand('formatBlock',false,cmd==='heading'?'h2':'p');\n    }else document.execCommand(cmd,false,null);\n    sync();\n  });\n  field.form.addEventListener('submit',()=>{if(dirty)sync();});\n})();\n</script>","preview_delete_draft.html":"{% extends 'base.html' %}{% block title %}Delete draft — The Workprint Project{% endblock %}{% block body %}<div class=\"shell member-panel\"><div class=\"member-box\" style=\"width:min(100%,800px)\"><h1>DELETE DRAFT {{kind|upper}}</h1><p>You are about to permanently delete <strong>{{record.title}}</strong> (record #{{record.id}}) from the Cloudflare database. This does not change Railway or delete files from R2.</p>{% if kind=='film' %}<p>Screenshot database references will be deleted with this draft. Films with download request history cannot be deleted here.</p>{% endif %}{% if error %}<p class=\"flash error\" role=\"alert\">{{error}}</p>{% endif %}<form class=\"member-form\" method=\"post\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><input type=\"hidden\" name=\"updated_at\" value=\"{{record.updated_at}}\"><label for=\"confirm\">Type DELETE to confirm</label><input id=\"confirm\" name=\"confirm\" required maxlength=\"6\" autocomplete=\"off\"><button type=\"submit\" class=\"button danger\">PERMANENTLY DELETE DRAFT</button><a class=\"button\" href=\"{{url_for('preview_film_edit',mid=record.id) if kind=='film' else url_for('preview_news_edit',aid=record.id)}}\">CANCEL</a></form></div></div>{% endblock %}","approved_downloads_admin.html":"{% extends 'base.html' %}{% block title %}Manage downloads — The Workprint Project{% endblock %}{% block body %}<div class=\"shell member-panel\"><div class=\"page-intro\"><div><span class=\"eyebrow\">CLOUDFLARE / ADMINISTRATION</span><h1>MANAGE DOWNLOADS</h1><p>Upload original or authorised documents to private storage. New files start disabled. Existing movie links are not imported or enabled.</p></div><a class=\"button\" href=\"{{url_for('preview_admin_dashboard')}}\">BACK TO ADMIN</a></div>{% if saved %}<p class=\"flash success\" role=\"status\">Download record saved.</p>{% endif %}{% if error %}<p class=\"flash error\" role=\"alert\">{{error}}</p>{% endif %}<div class=\"member-box\" style=\"width:min(100%,900px)\"><h2>ADD DOCUMENT</h2><form class=\"member-form\" method=\"post\" enctype=\"multipart/form-data\" action=\"{{url_for('approved_downloads_upload')}}\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><label for=\"title\">Display title</label><input id=\"title\" name=\"title\" maxlength=\"150\" required><label for=\"file\">Document (TXT or PDF, up to 5 MiB)</label><input id=\"file\" name=\"file\" type=\"file\" accept=\".txt,.pdf\" required><label for=\"basis\">Distribution permission</label><select id=\"basis\" name=\"basis\" required><option value=\"\">Choose permission basis</option><option value=\"original\">Original material I own and may distribute</option><option value=\"licensed\">Permission or licence from rights holder</option><option value=\"public-domain\">Public domain in intended distribution territories</option></select><label for=\"evidence\">Private permission record</label><textarea id=\"evidence\" name=\"evidence\" maxlength=\"2000\" rows=\"5\" required placeholder=\"Record authorship, licence terms or public-domain research. Do not include passwords or access tokens.\"></textarea><label><input type=\"checkbox\" name=\"confirm_rights\" value=\"1\" required style=\"width:auto\"> I have verified permission to distribute this specific file to members.</label><button class=\"button primary\" type=\"submit\">SAVE DISABLED DOWNLOAD</button></form></div><h2>DOCUMENTS</h2><div class=\"member-table-wrap\"><table class=\"member-table\"><thead><tr><th>Title / file</th><th>Permission record (private)</th><th>Status</th><th>Action</th></tr></thead><tbody>{% for file in files %}<tr><td>{{file.title}}<br>{{file.filename}} · {{file.size}} bytes</td><td>{{file.basis}}<br><span style=\"white-space:pre-wrap;overflow-wrap:anywhere\">{{file.evidence}}</span></td><td>{{'Enabled' if file.enabled else 'Disabled'}}</td><td><form method=\"post\" action=\"{{url_for('approved_downloads_toggle',fid=file.id)}}\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><input type=\"hidden\" name=\"expected\" value=\"{{file.enabled}}\">{% if not file.enabled %}<label><input type=\"checkbox\" required name=\"confirm_rights\" value=\"1\" style=\"width:auto\"> Permission still valid</label>{% endif %}<button class=\"button\" type=\"submit\">{{'Disable' if file.enabled else 'Enable'}}</button></form></td></tr>{% else %}<tr><td colspan=\"4\">No documents added.</td></tr>{% endfor %}</tbody></table></div></div>{% endblock %}","approved_external_settings.html":"{% extends 'base.html' %}{% block title %}Authorised external file — The Workprint Project{% endblock %}{% block body %}<div class=\"shell member-panel\"><div class=\"member-box\" style=\"width:min(100%,900px)\"><h1>PIXELDRAIN DOWNLOAD</h1><p>{{movie.title}} · {{'Published catalogue entry' if movie.published else 'Private draft'}}</p><p>Only add a file for which you hold distribution rights. This is a new permission record, not the imported archive link. Linking is not proof of permission.</p>{% if saved %}<p class=\"flash success\" role=\"status\">Permission record saved. Review the availability below.</p>{% endif %}{% if error %}<p class=\"flash error\" role=\"alert\">{{error}}</p>{% endif %}<form method=\"post\" class=\"member-form\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><input type=\"hidden\" name=\"revision\" value=\"{{record.revision or ''}}\"><input type=\"hidden\" name=\"action\" value=\"save\"><label for=\"link\">Pixeldrain file page URL</label><input id=\"link\" name=\"link\" type=\"url\" maxlength=\"150\" placeholder=\"https://pixeldrain.com/u/FILE_ID\" value=\"{{record.link or ''}}\" required><label for=\"basis\">Distribution permission</label><select id=\"basis\" name=\"basis\" required><option value=\"\">Select</option>{% for k,v in [('original','Original material I own and may distribute'),('licensed','Permission or licence from the rights holder'),('public-domain','Public domain in intended distribution territories')] %}<option value=\"{{k}}\" {% if record.basis==k %}selected{% endif %}>{{v}}</option>{% endfor %}</select><label for=\"evidence\">Private evidence of distribution rights</label><textarea id=\"evidence\" name=\"evidence\" maxlength=\"2000\" rows=\"6\" required placeholder=\"Identify rights holder, the specific edition/file, permission terms or public domain research. No credentials.\">{{record.evidence or ''}}</textarea><label><input type=\"checkbox\" name=\"confirm\" value=\"1\" required style=\"width:auto\"> I have verified the rights to distribute this specific file, including its edition and soundtrack where applicable.</label><button class=\"button primary\" type=\"submit\">SAVE AS DISABLED</button></form>{% if record.revision %}<hr><h2>AVAILABILITY: {{'ENABLED' if record.enabled else 'DISABLED'}}</h2><form method=\"post\" class=\"member-form\"><input type=\"hidden\" name=\"csrf_token\" value=\"{{csrf_token}}\"><input type=\"hidden\" name=\"revision\" value=\"{{record.revision}}\"><input type=\"hidden\" name=\"action\" value=\"{{'disable' if record.enabled else 'enable'}}\">{% if not record.enabled %}<label><input type=\"checkbox\" name=\"confirm\" value=\"1\" required style=\"width:auto\"> The permission is valid and covers distribution to these members.</label>{% endif %}<button class=\"button\" type=\"submit\">{{'DISABLE DOWNLOAD' if record.enabled else 'ENABLE DOWNLOAD'}}</button></form><p>Only published catalogue entries can deliver a link. Disabling prevents future requests here but cannot revoke a link already shared externally.</p>{% endif %}<p><a class=\"button\" href=\"{{url_for('preview_film_edit',mid=movie.id)}}\">BACK TO FILM</a></p></div></div>{% endblock %}"})
CATALOGUE_CSS = "@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;500;600;700;800;900&family=Inter:wght@400;500;600;700;800&display=swap');\n:root{--bg:#050b17;--panel:#081427;--panel2:#0b1930;--line:#203654;--text:#edf4ff;--muted:#8299b6;--blue:#27baff;--glow:#047fff;--orange:#ff9c42}\n*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:25px}body{margin:0;background:radial-gradient(ellipse at 45% -5%,#0b2450 0,#060d1c 40%,#030917 86%);color:var(--text);font:13px/1.55 Inter,Arial,sans-serif}a{color:inherit;text-decoration:none}button,input,textarea,select{font:inherit}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}.shell{max-width:1700px;width:calc(100% - 64px);margin:auto}.site-header{position:relative;background:#050a16}.hero-art{height:clamp(290px,25vw,405px);background:#050a16;border-bottom:1px solid #16365c;display:flex;align-items:center;justify-content:center;padding:10px 20px}.header-logo-link{display:flex;align-items:center;justify-content:center;width:min(710px,90%);height:100%}.header-logo{display:block;max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain;filter:drop-shadow(0 0 14px #1177ff35)}.site-nav{height:62px;display:flex;align-items:stretch;gap:0;padding:0 10px;background:linear-gradient(180deg,#0c1b32,#071325);border:1px solid #23507c;border-radius:8px;box-shadow:0 4px 20px #0009;position:relative;z-index:3;margin-top:0}.site-nav>a,.nav-button{display:flex;align-items:center;justify-content:center;gap:11px;border:0;border-bottom:3px solid transparent;background:transparent;color:#d9e6f5;font:800 17px 'Barlow Condensed','Arial Narrow',Arial,sans-serif,sans-serif;letter-spacing:.2px;min-width:120px;padding:12px 19px;white-space:nowrap;cursor:pointer}.site-nav>a:hover,.site-nav>a.active{border-bottom-color:#ff683b;background:linear-gradient(#24233333,#1e171755);color:#ffbd6b;text-shadow:0 0 11px #f65c2b77}.nav-icon{font:700 23px Arial;color:inherit}.nav-search{margin:auto 0 auto auto;display:flex;height:40px;width:min(400px,30%);background:#0d203c;border:1px solid #1c3b60;border-radius:8px;overflow:hidden;align-items:center}.nav-search>span{padding-left:14px;color:var(--blue);font-size:26px}.nav-search input{flex:1;min-width:50px;width:100%;border:0;background:none;color:white;font:12px Inter;padding:10px;outline:none}.nav-search button{height:100%;border:0;border-left:1px solid #1a5683;background:#1171bd;color:#dff6ff;font:800 13px 'Barlow Condensed','Arial Narrow',Arial,sans-serif,sans-serif;padding:0 18px;cursor:pointer}.site-nav .nav-login{color:#27baff;min-width:95px}.nav-logout{display:contents}.nav-button{font-size:14px;min-width:85px}.site-nav .nav-login:hover,.nav-button:hover{color:white}\n.dashboard-content{padding-top:17px;padding-bottom:90px}.stat-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px}.stat-card{min-height:92px;border:1px solid #183d68;background:linear-gradient(120deg,#0b1c3b,#0b132c);border-radius:9px;display:flex;align-items:center;gap:24px;padding:17px 22px;box-shadow:inset 0 0 35px #0064ff0d}.stat-icon{font:700 43px Arial;line-height:1;color:#2f8dff;text-shadow:0 0 13px #1d7eff88}.stat-card>div{min-width:0;display:flex;flex-direction:column}.stat-card strong{font:800 32px/1 'Barlow Condensed','Arial Narrow',Arial,sans-serif;letter-spacing:.6px;color:#32c5ff}.stat-card span:not(.stat-icon){font:700 14px/1.4 'Barlow Condensed','Arial Narrow',Arial,sans-serif;letter-spacing:.5px}.stat-card small{font-size:11px;color:#88a1c5}.stat-green{border-color:#14564d;background:linear-gradient(120deg,#061f30,#071726)}.stat-green .stat-icon,.stat-green strong{color:#39e0ac}.stat-purple{border-color:#3b245b;background:linear-gradient(120deg,#211332,#0d1529)}.stat-purple .stat-icon,.stat-purple strong{color:#d27cff}.stat-red{border-color:#572741;background:linear-gradient(120deg,#231327,#100f22)}.stat-red .stat-icon,.stat-red strong{color:#ff5c78}\n.format-toolbar{display:flex;align-items:center;gap:28px;margin-top:14px;margin-bottom:13px;padding:12px 18px;min-height:67px;border:1px solid #19436e;background:linear-gradient(95deg,#071e39,#09172b);border-radius:7px}.format-info{min-width:270px;display:flex;align-items:center;gap:15px}.toolbar-symbol{font-size:26px;color:var(--blue)}.format-info strong{font:800 17px 'Barlow Condensed','Arial Narrow',Arial,sans-serif;color:#25d4ff;letter-spacing:.6px}.format-info small{display:block;color:#718fb4;font-size:11px}.format-buttons{display:flex;flex:1;align-items:center;gap:8px;flex-wrap:wrap}.format-button{font:700 12px 'Barlow Condensed','Arial Narrow',Arial,sans-serif;border:1px solid #2b4564;border-radius:7px;min-height:39px;min-width:76px;padding:10px 13px;text-align:center;background:#081427;color:#f0f5ff;box-shadow:0 2px 7px #0006}.format-button:hover,.format-button.selected{border-color:#27baff;box-shadow:inset 0 0 16px #107aff30,0 0 6px #178eff46;color:#eafaff}.format-button.selected{background:#123768}\n.dashboard-grid{display:grid;grid-template-columns:270px minmax(0,1fr) 270px;gap:18px;align-items:start}.dashboard-left,.dashboard-right{min-width:0}.side-panel{background:linear-gradient(145deg,#09172b,#061022);border:1px solid #19375d;border-radius:8px;margin-bottom:12px;overflow:hidden}.side-panel h2{font:800 18px 'Barlow Condensed','Arial Narrow',Arial,sans-serif;letter-spacing:.55px;color:#30d4ff;margin:0;padding:11px 15px 8px;border-bottom:1px solid #183254}.side-panel h2 span{color:#259fff;margin-right:7px;font-size:22px}.side-links a{padding:7px 16px;display:flex;align-items:center;gap:9px;color:#c0d5ed;font-size:12px;border-bottom:1px solid #132940}.side-links a:last-child{border:0}.side-links a:hover{background:#142a45;color:white}.side-links a span{width:19px;color:#bed2f7;font-size:17px}.side-links a b{margin-left:auto;font-size:18px;color:#90add4}.archive-stats{padding:8px 13px 13px}.archive-stats>div{display:flex;justify-content:space-between;gap:8px;padding:4px 0;color:#90a6c1;border-bottom:1px solid #142741;font-size:11px}.archive-stats strong{color:#dce7f5;font-variant-numeric:tabular-nums;font-size:12px}\n.section-heading{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:5px 0 12px}.section-heading>div{position:relative;padding-left:40px}.section-icon{position:absolute;left:0;top:-7px;font-size:30px;color:#ffab54;text-shadow:0 0 12px #ff562799}.section-heading h1{font:800 25px/1.06 'Barlow Condensed','Arial Narrow',Arial,sans-serif;letter-spacing:.8px;margin:0}.section-heading p{font-size:12px;color:#7291b7;margin:3px 0 0}.section-heading>a{font:800 13px 'Barlow Condensed','Arial Narrow',Arial,sans-serif;color:#85cfff;padding:10px 12px;border-radius:7px;background:#102039;border:1px solid #223957;white-space:nowrap}.section-heading>a:hover{color:white;border-color:#26baff}.movie-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:13px}.movie-card{min-width:0;border:1px solid #244468;border-radius:7px;overflow:hidden;background:linear-gradient(#0a182d,#061121);transition:transform .2s,border-color .2s,box-shadow .2s}.movie-card:hover{transform:translateY(-4px);border-color:#2fbcff;box-shadow:0 5px 22px #056abe44}.poster-wrap{position:relative;aspect-ratio:170/215;overflow:hidden;background:radial-gradient(#112f59,#050e1e);border-bottom:1px solid #183659}.poster-wrap img{width:100%;height:100%;object-fit:cover;display:block}.poster-wrap:after{content:'';pointer-events:none;position:absolute;inset:0;box-shadow:inset 0 0 12px #07132877}.poster-placeholder{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:13px;gap:12px;background:radial-gradient(#16406e,#071126)}.poster-placeholder>span{color:#00a9ff;font-size:40px}.poster-placeholder small{font:600 9px 'Barlow Condensed','Arial Narrow',Arial,sans-serif;letter-spacing:1px;color:#6b9ed2}.poster-placeholder strong{font:800 clamp(15px,1.6vw,23px)/1.1 'Barlow Condensed','Arial Narrow',Arial,sans-serif;text-transform:uppercase;overflow-wrap:anywhere}.movie-type{position:absolute;left:7px;top:7px;font:800 11px 'Barlow Condensed','Arial Narrow',Arial,sans-serif;letter-spacing:.3px;color:#041329;background:#44b5ff;border-radius:5px;padding:3px 9px;max-width:calc(100% - 14px);white-space:normal;z-index:1}.type-cam{background:#ffb751}.type-vhs{background:#ce72ff}.type-35mm{background:#48dfb5}.type-screener{background:#ec6f92}.type-betamax{background:#a7aaff}.type-laserdisc{background:#ffbe54}.movie-info{padding:9px 10px 11px}.movie-info h3{font:800 15px/1.12 'Barlow Condensed','Arial Narrow',Arial,sans-serif;letter-spacing:.2px;margin:0 0 3px;min-height:17px;overflow-wrap:anywhere}.movie-year{color:#8aaed1;font-size:11px}.movie-info p{font-size:10px;line-height:1.5;color:#94a9c3;margin:5px 0 8px;min-height:45px}.card-meta{border-top:1px solid #182d46;padding-top:5px;display:flex;flex-wrap:wrap;justify-content:space-between;font:700 10px 'Barlow Condensed','Arial Narrow',Arial,sans-serif;color:#9fc7e8}.draft-label{color:#ffbc67}.empty{border:1px dashed #28517d;border-radius:8px;padding:38px;text-align:center;color:#acc8e9;background:#0a1730}.empty strong{font:800 24px 'Barlow Condensed','Arial Narrow',Arial,sans-serif}.search-section{margin-top:22px;border:1px solid #183859;border-radius:7px;background:#081629;padding:18px}.search-section h2{font:800 22px 'Barlow Condensed','Arial Narrow',Arial,sans-serif;color:#40d6ff;margin:0 0 11px}.filters{display:grid;grid-template-columns:2fr 1fr 1fr 95px auto;gap:8px}\n.uploads-panel{min-height:230px}.recent-item{display:flex;align-items:center;gap:10px;padding:8px 10px;border-top:1px solid #172c49}.recent-item:hover{background:#112842}.recent-thumb{width:53px;height:64px;flex:0 0 53px;border-radius:5px;border:1px solid #2d4f76;background:#0c1e37;overflow:hidden;display:flex;justify-content:center;align-items:center}.recent-thumb img{display:block;width:100%;height:100%;object-fit:cover}.recent-thumb>span{color:#409fff;font-size:25px}.recent-copy{flex:1;min-width:0;display:flex;flex-direction:column;align-items:start;gap:2px}.recent-copy strong{font:800 14px/1.15 'Barlow Condensed','Arial Narrow',Arial,sans-serif;white-space:normal}.mini-tag{border:1px solid #3972a1;border-radius:5px;padding:0px 5px;background:#102a49;color:#78bcff;font:700 11px 'Barlow Condensed','Arial Narrow',Arial,sans-serif}.recent-copy small{font-size:10px;color:#90a7c4}.recent-chevron{font-size:20px;color:#adc9e8}.empty-recent{padding:15px;color:#97aac2;font-size:12px}.mini-info{border:1px solid #223a57;background:#08182b;padding:12px;border-radius:7px;display:flex;flex-direction:column}.mini-info span{color:#65ceff;font:700 13px 'Barlow Condensed','Arial Narrow',Arial,sans-serif}.mini-info strong{color:#38ddab;font:800 20px 'Barlow Condensed','Arial Narrow',Arial,sans-serif}.mini-info small{color:#92a6bd;font-size:10px}\ninput,select,textarea{width:100%;padding:11px 13px;border:1px solid #274b72;border-radius:6px;background:#0c1a31;color:#edf5ff;outline:none}input:focus,select:focus,textarea:focus{border-color:#4bc9ff;box-shadow:0 0 0 2px #2093eb33}textarea{resize:vertical;min-height:100px}label{display:block;margin:15px 0 7px;font-size:12px;font-weight:700;color:#c3d7eb}.button{display:inline-flex;align-items:center;justify-content:center;padding:11px 18px;background:#162744;border:1px solid #30587d;border-radius:6px;color:#e9f5ff;font:800 13px 'Barlow Condensed','Arial Narrow',Arial,sans-serif;cursor:pointer;white-space:nowrap}.button.primary{background:#0686e5;border-color:#28aafe;color:white}.button:hover{filter:brightness(1.18)}.danger{background:#401529;border-color:#b54c76}.flashes{padding-top:18px}.flash{padding:12px 18px;border:1px solid #248368;background:#103e39;border-radius:5px}.flash.error{background:#43142d;border-color:#b84b76}.site-footer{border-top:1px solid #203a59;background:#040a15}.footer-inner{display:flex;justify-content:space-between;align-items:center;gap:25px;padding:22px 0;color:#719abb;font:600 11px 'Barlow Condensed','Arial Narrow',Arial,sans-serif;letter-spacing:.6px}.footer-inner>a{color:#2fc1ff}\n/* Existing movie detail, Pixeldrain and protected admin pages */\n.detail,.edit-wrap{padding-top:36px;padding-bottom:85px}.back,.eyebrow{font:700 13px 'Barlow Condensed','Arial Narrow',Arial,sans-serif;color:#45ccff;letter-spacing:.7px}.eyebrow{margin-top:16px}.detail-top{display:grid;grid-template-columns:minmax(180px,285px) 1fr;gap:38px;margin-top:20px}.detail-poster{aspect-ratio:2/3;border:1px solid #1e5486;background:#0b1b34;overflow:hidden}.detail-poster img{height:100%;width:100%;object-fit:cover}.detail h1,.edit-wrap h1,.panel h1{font:900 clamp(36px,5.5vw,75px)/1 'Barlow Condensed','Arial Narrow',Arial,sans-serif;margin:12px 0 22px;text-transform:uppercase}.tags{display:flex;flex-wrap:wrap;gap:7px}.tags span{padding:5px 11px;border:1px solid #315675;border-radius:4px;font:700 12px 'Barlow Condensed','Arial Narrow',Arial,sans-serif;color:#8bcdf5}.intro{color:#becde1;line-height:1.8;font-size:15px;max-width:860px}.meta-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:25px 0;padding:20px 0;border-top:1px solid #203854;border-bottom:1px solid #203854}.meta-grid>div{display:flex;flex-direction:column;gap:3px;border-left:2px solid #1f99ed;padding-left:10px}.meta-grid span{color:#58c8f6;font:800 11px 'Barlow Condensed','Arial Narrow',Arial,sans-serif}.meta-grid strong{font-size:12px}.download{margin:10px 6px 4px 0}.tiny,.muted,.hint{color:#92a8c2;font-size:12px}.admin-actions{display:flex;gap:9px;margin-top:18px}.detail-section{margin-top:36px;padding-top:24px;border-top:1px solid #254461}.detail-section h2{font:800 29px 'Barlow Condensed','Arial Narrow',Arial,sans-serif;margin:6px 0 16px}.prose{white-space:pre-line;max-width:900px;color:#b8cae0;font-size:14px;line-height:1.85}.gallery{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.gallery a{background:#0c1b30;border:1px solid #2b4a6a}.gallery img{display:block;aspect-ratio:16/9;width:100%;object-fit:contain}.gallery span{display:block;padding:7px;color:#87cfff;font-size:11px}.login-wrap{min-height:60vh;display:flex;align-items:center;justify-content:center;padding:35px}.panel{width:min(460px,100%);padding:35px;background:#0b1930;border:1px solid #234772;border-radius:7px}.panel p{color:var(--muted)}.full,.save{width:100%;margin-top:15px}.edit-wrap{max-width:1100px}.edit-form{margin-top:24px}.form-section{padding:26px 30px;margin-bottom:16px;border:1px solid #24486b;border-radius:8px;background:#0b192d}.form-section h2{font:800 27px 'Barlow Condensed','Arial Narrow',Arial,sans-serif;color:#4fd0ff;margin:0 0 14px;text-transform:uppercase}.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:19px}.span2{grid-column:span 2}.check{display:flex;align-items:center;gap:10px}.check input{width:auto}.preview-poster{max-width:150px;display:block;margin:12px 0}.existing-pics{display:flex;flex-wrap:wrap;gap:14px}.existing-pics>div{width:148px}.existing-pics img{display:block;width:100%;aspect-ratio:16/9;object-fit:cover}.existing-pics button{width:100%}.empty .button{margin-top:10px}\n@media(max-width:1400px){.site-nav>a{min-width:auto;padding:12px 14px}.dashboard-grid{grid-template-columns:210px minmax(0,1fr) 220px}.stat-card{gap:12px;padding:15px}.stat-card strong{font-size:27px}.format-info{min-width:210px}.movie-grid{gap:9px}.movie-info h3{font-size:13px}.movie-info p{font-size:9px}}\n@media(max-width:1160px){.shell{width:calc(100% - 38px)}.dashboard-grid{grid-template-columns:195px minmax(0,1fr)}.dashboard-right{grid-column:1/-1}.uploads-panel{min-height:0}.uploads-panel .recent-item{display:inline-flex;width:calc(25% - 3px);vertical-align:top;border-top:1px solid #173554}.nav-search{width:min(290px,26%)}.stat-card small{font-size:10px}.format-toolbar{align-items:flex-start}.format-info{min-width:185px}.movie-grid{grid-template-columns:repeat(4,minmax(0,1fr))}}\n@media(max-width:800px){.hero-art{height:260px;padding:14px 14px}.header-logo-link{width:min(480px,100%)}.site-nav{width:100%;border-radius:0;height:auto;min-height:54px;flex-wrap:wrap;justify-content:center}.site-nav>a,.nav-button{min-width:auto;font-size:15px;padding:10px}.nav-search{order:3;width:100%;max-width:none;margin:3px 6px 9px}.stat-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.format-toolbar{flex-direction:column;gap:12px}.format-buttons{gap:7px}.dashboard-grid{grid-template-columns:1fr}.dashboard-left{display:grid;grid-template-columns:1fr 1fr;gap:12px}.dashboard-right{grid-column:auto}.uploads-panel .recent-item{display:inline-flex;width:calc(50% - 3px)}.movie-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.movie-info h3{font-size:16px}.movie-info p{font-size:11px}.detail-top{grid-template-columns:200px 1fr;gap:22px}.filters{grid-template-columns:repeat(2,minmax(0,1fr))}.filters .button{grid-column:1/-1}}\n@media(max-width:530px){.shell{width:calc(100% - 22px)}.hero-art{height:205px;padding:12px 8px}.header-logo-link{width:100%}.site-nav{gap:0}.site-nav>a,.nav-button{font-size:14px;padding:8px 8px;flex:1 1 29%}.nav-icon{font-size:16px}.stat-grid{gap:9px}.stat-card{padding:11px 10px;min-height:84px}.stat-icon{font-size:28px}.stat-card strong{font-size:23px}.stat-card span:not(.stat-icon){font-size:11px}.stat-card small{font-size:9px}.format-toolbar{padding:10px}.format-button{flex:1 1 auto;min-width:0}.dashboard-left{grid-template-columns:1fr}.movie-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.movie-info h3{font-size:15px}.uploads-panel .recent-item{width:100%}.detail-top{grid-template-columns:1fr}.detail-poster{max-width:260px}.meta-grid{grid-template-columns:1fr 1fr}.gallery{grid-template-columns:repeat(2,1fr)}.form-grid{grid-template-columns:1fr}.span2{grid-column:auto}.form-section{padding:18px}.footer-inner{flex-direction:column;gap:9px;text-align:center}.section-heading h1{font-size:21px}.section-heading>div{padding-left:34px}.filters{grid-template-columns:1fr}.filters .button{grid-column:auto}}\n@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}\n\n\n/* Center film detail and admin pages (dashboard uses .shell elsewhere) */\n.container.detail {width:min(1220px, calc(100% - 48px));max-width:1220px;margin-inline:auto;padding-left:0;padding-right:0;}\n.container.edit-wrap {width:min(1100px, calc(100% - 48px));max-width:1100px;margin-inline:auto;padding-left:0;padding-right:0;}\n.detail .detail-top {max-width:1180px;margin-left:auto;margin-right:auto;grid-template-columns:minmax(230px,300px) minmax(0,1fr);gap:clamp(24px,4vw,56px);align-items:start;}\n.detail .detail-section {max-width:1180px;margin-left:auto;margin-right:auto;}\n.detail .detail-poster {width:100%;}\n.detail .detail-section .prose {max-width:100%;}\n.detail .detail-top > div {min-width:0;}\n.detail .intro {white-space:pre-line;}\n/* Rich text in film descriptions */\n.formatted-differences {white-space:normal;overflow-wrap:anywhere;line-height:1.85;}\n.formatted-differences p {margin:0 0 1.05em;}\n.formatted-differences h2,.formatted-differences h3 {color:#eaf7ff;font-family:'Barlow Condensed',Arial,sans-serif;margin:1.15em 0 .35em;line-height:1.15;}\n.formatted-differences h2{font-size:27px}.formatted-differences h3{font-size:22px}\n.formatted-differences strong,.formatted-differences b {font-weight:800;color:#f4faff;}\n.formatted-differences a{color:#57cdff;text-decoration:underline;overflow-wrap:anywhere;}\n.formatted-differences ul,.formatted-differences ol {margin:0 0 1.1em;padding-left:1.75em;}\n.formatted-differences li {margin:.3em 0;}\n.formatted-differences blockquote {margin:1.1em 0;padding:7px 18px;border-left:3px solid #32baff;background:#0b1f37;}\n/* Admin rich text editor */\n.rich-editor {border:1px solid #275078;border-radius:9px;background:#0b1930;overflow:hidden;box-shadow:0 5px 18px #0002;}\n.rich-editor:focus-within{border-color:#4bc9ff;box-shadow:0 0 0 2px #2093eb33;}\n.rich-toolbar{display:flex;flex-wrap:wrap;gap:5px;align-items:center;padding:10px;background:#10223c;border-bottom:1px solid #2a5078;}\n.rich-toolbar button{border:1px solid #355678;color:#e4f3ff;background:#132b47;padding:7px 10px;border-radius:5px;min-height:34px;min-width:34px;cursor:pointer;font:700 12px Inter,Arial,sans-serif;}\n.rich-toolbar button:hover,.rich-toolbar button:focus-visible{border-color:#57cfff;background:#193d61;outline:none;}\n.rich-toolbar button:active{background:#205b85;}\n.toolbar-divider{height:23px;width:1px;background:#365575;margin:0 4px;}\n.rich-edit-area{padding:18px 20px;min-height:250px;max-height:600px;overflow:auto;background:#08172b;color:#edf5ff;font:14px/1.75 Inter,Arial,sans-serif;outline:none;overflow-wrap:anywhere;}\n.rich-edit-area:empty:before{content:attr(data-placeholder);color:#7f9abb;pointer-events:none;}\n.rich-edit-area p{margin:0 0 1em}.rich-edit-area h3{font:800 22px 'Barlow Condensed',Arial,sans-serif;margin:12px 0 7px}\n.rich-edit-area ul,.rich-edit-area ol{padding-left:24px}.rich-edit-area a{color:#5fcfff;text-decoration:underline;}\n.rich-hidden-source{display:none;}\n@media(max-width:800px){.detail .detail-top{grid-template-columns:200px minmax(0,1fr);gap:23px;}}\n@media(max-width:600px){.container.detail,.container.edit-wrap{width:calc(100% - 28px)}.detail .detail-top{grid-template-columns:1fr;}.detail .detail-poster{max-width:255px;margin-inline:auto}.detail h1{text-align:center}.detail .tags{justify-content:center}.detail .eyebrow{text-align:center}.rich-toolbar{padding:7px}.rich-toolbar button{padding:7px}.rich-edit-area{padding:15px;min-height:220px;}}\n\n/* 2026 newsroom release: replaces the dashboard statistics cards entirely */\n.news-hub,.archive-browse,.format-page,.compact-page,.article-page{padding-top:38px;padding-bottom:95px;min-height:52vh}\n.page-intro{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;margin:12px 0 32px;padding-bottom:25px;border-bottom:1px solid #233a5c}\n.page-intro h1{font:900 clamp(38px,4.3vw,66px)/.95 'Barlow Condensed',Impact,sans-serif;letter-spacing:.5px;color:#f4f8ff;margin:10px 0 12px;text-transform:uppercase}\n.page-intro p{font-size:14px;color:#8faed2;margin:0;max-width:700px;line-height:1.7}.eyebrow{font-size:11px;letter-spacing:2px;font-weight:800;color:#45c9ff}.back-link{display:inline-block;color:#66d7ff;font-weight:800;font-size:12px;margin:0 0 27px}.back-link:hover{color:white}\n.news-layout{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:28px;align-items:start}.news-stack{display:grid;gap:18px}\n.news-card{display:grid;grid-template-columns:minmax(200px,32%) 1fr;gap:22px;padding:17px;background:linear-gradient(110deg,#0a1b38,#091223);border:1px solid #223d67;border-radius:11px;min-width:0;transition:border-color .2s}.news-card:hover{border-color:#2d96d3}.news-card.lead-news{grid-template-columns:minmax(220px,45%) 1fr;min-height:280px}\n.news-art{display:block;overflow:hidden;border-radius:6px;background:#0e2540;min-height:175px}.news-art img{display:block;width:100%;height:100%;max-height:370px;min-height:175px;object-fit:cover}.news-card.lead-news .news-art img{max-height:390px}.news-art-placeholder{height:100%;min-height:175px;display:grid;place-content:center;text-align:center;gap:14px;font-size:40px;color:#55bff8;background:radial-gradient(circle at 50% 20%,#19427e,#080f23 70%)}.news-art-placeholder span{font:800 16px 'Barlow Condensed',sans-serif;letter-spacing:2px}\n.article-meta{display:flex;align-items:center;flex-wrap:wrap;gap:13px;font-size:11px;color:#8aa9cb;letter-spacing:.5px}.news-tag{display:inline-block;background:#0c4596;color:#a8ddff;border:1px solid #2c78cb;border-radius:4px;font-size:10px;font-weight:850;padding:5px 9px;letter-spacing:1px}.news-tag.upcoming{background:#502d15;color:#ffd48d;border-color:#ab682b}.news-copy{display:flex;flex-direction:column;align-items:flex-start;min-width:0}.news-copy h2{font:800 clamp(23px,2.8vw,38px)/1.09 'Barlow Condensed',sans-serif;color:#f4f8ff;margin:15px 0 9px}.news-copy h2 a:hover{color:#59caff}.news-copy p{font-size:13px;line-height:1.78;color:#adbfda;margin:0 0 15px}.read-more{margin-top:auto;color:#4fc6ff;font-size:11px;letter-spacing:1px;font-weight:800}.news-sidebar{display:grid;gap:15px}.news-sidebar .side-panel{padding:21px}.news-sidebar .side-panel h2{font-size:20px}.news-sidebar .side-panel p{color:#a0b7d7;line-height:1.65}.news-format-links{display:grid;gap:2px}.news-format-links a{display:flex;justify-content:space-between;align-items:center;padding:11px;border-bottom:1px solid #283852;color:#d9e7ff;font-weight:650}.news-format-links a:hover{color:#54d2ff}.full{width:100%}\n.empty-news{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:80px 20px;background:linear-gradient(130deg,#081c3a,#10112a);border:1px dashed #315b90;border-radius:14px}.empty-news-icon{font-size:48px;color:#3cbcff}.empty-news h2{font:800 36px 'Barlow Condensed',sans-serif;margin:7px 0}.empty-news p{color:#a6bbd8;max-width:500px}.recent-films{margin-top:55px}.recent-films .section-heading{display:flex;align-items:center;justify-content:space-between}.recent-films .section-heading h2{font:800 28px 'Barlow Condensed',sans-serif;margin:0}.recent-films .section-heading a{color:#6dcfff;font-size:12px}.recent-news-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:15px;margin-top:17px}.recent-news-card{display:flex;flex-direction:column;min-width:0;border:1px solid #234169;background:#0a1730;border-radius:7px;overflow:hidden}.recent-news-card img,.mini-placeholder{width:100%;aspect-ratio:2/3;object-fit:cover}.mini-placeholder{display:grid;place-items:center;color:#5bd4ff;font-size:50px}.recent-news-card strong{font:800 17px/1.15 'Barlow Condensed',sans-serif;margin:11px 10px 3px}.recent-news-card span{font-size:10px;color:#66c9fc;margin:0 10px 12px}\n.browse-controls{display:flex;align-items:flex-end;flex-wrap:wrap;gap:13px;background:#0a1831;border:1px solid #28456d;padding:19px;border-radius:9px;margin-bottom:22px}.browse-controls>div{flex:1 1 140px;min-width:140px}.browse-controls>div.browse-search{flex:2 1 210px}.browse-controls label{display:block;margin:0 0 7px;color:#70d5ff;font-weight:800;font-size:10px;letter-spacing:1px}.browse-controls input,.browse-controls select{width:100%;height:43px}.browse-controls>.button{min-height:43px}.browse-subhead{display:flex;align-items:center;justify-content:space-between;margin:18px 0;color:#b5d6f1;font-size:12px;letter-spacing:1px}.browse-subhead a{color:#53cfff}.archive-browse .movie-grid{grid-template-columns:repeat(5,minmax(0,1fr));gap:17px}\n.format-card-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px}.format-card{display:flex;position:relative;align-items:center;gap:20px;min-height:155px;padding:22px;background:linear-gradient(130deg,#0b1d3c,#0c1326);border:1px solid #2c5282;border-radius:10px;transition:transform .15s,border-color .15s}.format-card:hover{border-color:#4dc7ff;transform:translateY(-4px)}.format-icon{flex:0 0 66px;height:70px;display:grid;place-items:center;border:1px solid #356796;border-radius:8px;background:#102c52;font-size:38px;color:#55cbff}.format-card h2{font:800 30px 'Barlow Condensed',sans-serif;line-height:1.15;margin:0 0 7px}.format-card p{margin:0;color:#88b1d1;font-size:12px}.format-arrow{position:absolute;right:14px;top:12px;font-size:21px;color:#4cbaf9}\n.compact-page{max-width:920px}.compact-page .page-intro{margin-top:0}.contact-panel,.message-panel{border:1px solid #284773;background:linear-gradient(#0c1a34,#0a1226);border-radius:12px;padding:28px}.contact-panel label{display:block;font-size:12px;font-weight:700;color:#c4dcf6;margin:15px 0 9px}.contact-panel .form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.contact-panel textarea{resize:vertical;min-height:180px}.contact-panel .button{margin-top:14px}.honeypot{position:absolute!important;left:-10000px!important;width:1px;height:1px;overflow:hidden}.messages-list{display:grid;gap:15px}.message-panel header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px}.message-panel h2{font:800 25px 'Barlow Condensed',sans-serif;margin:10px 0 5px}.message-panel header p{margin:0;color:#9cbbe0}.message-panel header a{color:#60ccff}.message-panel small{color:#a7b9d3}.message-body{white-space:pre-wrap;color:#dde6f4;line-height:1.7;border-top:1px solid #294065;margin-top:16px;padding-top:15px}\n.article-page{max-width:1120px}.article-page .article-meta{margin-bottom:12px}.article-page h1{font:900 clamp(43px,5.5vw,76px)/.99 'Barlow Condensed',sans-serif;margin:12px 0 20px}.article-standfirst{font-size:20px;line-height:1.65;color:#a9c2df}.article-cover{display:block;max-width:100%;width:100%;max-height:580px;object-fit:cover;border-radius:9px;margin:24px 0 35px;border:1px solid #2b527f}.article-content{font-size:16px;line-height:1.9;color:#d5e4f5;max-width:920px;overflow-wrap:anywhere}.article-content h2{font:800 32px 'Barlow Condensed',sans-serif}.article-content a{color:#45c5ff;text-decoration:underline}.article-content blockquote{border-left:3px solid #39bdf5;padding-left:17px;color:#a7cde5}.article-page .admin-actions{margin-top:35px}.news-editor-wrap{max-width:980px}.news-editor-wrap h1{font:800 48px 'Barlow Condensed',sans-serif}.news-editor-wrap .rich-editor{min-height:280px}.news-editor-wrap .form-section{padding:26px}.news-editor-wrap .form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.news-editor-wrap .check{display:flex;align-items:center;gap:10px}.news-editor-wrap .check input{width:auto}.news-editor-wrap .editor-box{border:1px solid #395b80;background:#091124}.news-editor-wrap .rich-toolbar{display:flex;flex-wrap:wrap;gap:5px;padding:8px;border-bottom:1px solid #395b80}.news-editor-wrap .rich-toolbar button{background:#1a3152;color:white;border:1px solid #47648c;border-radius:4px;padding:8px 12px;cursor:pointer}.news-editor-wrap .rich-editor{padding:16px;outline:0;min-height:270px;color:#e5f0fc}.news-editor-wrap .rich-editor:focus{box-shadow:inset 0 0 0 2px #3bbbe980}.news-editor-wrap .rich-editor:empty:before{content:'Write your article here...';color:#6685a2}\n@media(max-width:1100px){.news-layout{grid-template-columns:minmax(0,1fr) 250px}.archive-browse .movie-grid{grid-template-columns:repeat(4,minmax(0,1fr))}.format-card-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.recent-news-grid{grid-template-columns:repeat(4,minmax(0,1fr))}}\n@media(max-width:780px){.news-layout{grid-template-columns:1fr}.news-sidebar{grid-template-columns:repeat(2,minmax(0,1fr))}.news-card,.news-card.lead-news{grid-template-columns:35% 1fr;min-height:0}.format-card-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.archive-browse .movie-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.page-intro{align-items:start;flex-direction:column}}\n@media(max-width:560px){.news-hub,.archive-browse,.format-page,.compact-page,.article-page{padding-top:23px;padding-bottom:58px}.news-card,.news-card.lead-news{display:block}.news-card .news-art{margin-bottom:18px}.news-art img{max-height:240px}.news-sidebar{grid-template-columns:1fr}.recent-news-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.archive-browse .movie-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.format-card-grid{grid-template-columns:1fr}.contact-panel .form-grid,.news-editor-wrap .form-grid{grid-template-columns:1fr}.contact-panel{padding:17px}.browse-controls>div{flex-basis:100%}.news-copy h2{font-size:30px}}\n\n/* Member accounts / administration */\n.member-panel{padding:44px 0 90px;max-width:1250px;margin:auto}.member-panel h1{font:800 clamp(30px,4vw,54px)/1.05 'Barlow Condensed',sans-serif;text-transform:uppercase;margin:13px 0 22px}.member-panel h2{font:800 29px 'Barlow Condensed',sans-serif;text-transform:uppercase;margin:30px 0 12px}.member-box{width:min(100%,590px);margin:auto;background:#0c1730;border:1px solid #28466c;padding:clamp(22px,4vw,42px);border-radius:14px;box-shadow:0 15px 50px #0004}.member-box a,.member-table a{color:#75cfff}.member-box .member-form{display:grid;gap:8px}.member-box label{font-weight:700;color:#b9ccef;font-size:13px;margin-top:8px}.member-box input,.member-search input,.member-controls select{background:#08162f;color:#fff;border:1px solid #2d4c75;padding:13px;border-radius:6px;max-width:100%;width:100%}.member-box .full{margin-top:16px}.member-card-row{display:flex;gap:16px;flex-wrap:wrap;margin:18px 0 25px}.member-card{background:#0c1933;border:1px solid #28486b;border-radius:10px;padding:19px 24px;flex:1 1 180px;display:grid;gap:6px}.member-card span{font-weight:800;font-size:12px;color:#8ac8f6}.member-card strong{font:800 36px 'Barlow Condensed',sans-serif;color:#60c6ff}.member-card small{color:#9dacbf}.member-table-wrap{width:100%;overflow-x:auto;background:#0b1429;border:1px solid #244068;border-radius:9px}.member-table{width:100%;border-collapse:collapse;text-align:left;min-width:580px}.member-table th{background:#101f3d;font-size:12px;text-transform:uppercase;color:#80c8fe}.member-table td,.member-table th{padding:13px 15px;border-bottom:1px solid #1e3455;overflow-wrap:anywhere}.member-table tr:last-child td{border-bottom:none}.member-search{display:flex;gap:12px;max-width:540px}.member-controls{display:flex;flex-wrap:wrap;gap:18px;align-items:end}.member-controls form{display:flex;gap:9px;align-items:end;flex-wrap:wrap}.member-controls label{display:block;width:100%}.member-controls select{width:220px}.member-download-panel{margin:22px 0;padding:18px;background:#10203b;border:1px solid #28567e;border-radius:9px}.member-download-panel .download{margin-top:8px}.member-download-panel button:disabled{opacity:.55;cursor:not-allowed}.trap{position:absolute;left:-10000px;height:0;overflow:hidden}.tiny{font-size:12px;color:#91a9c9}.muted{color:#91a9c9}@media(max-width:700px){.member-panel{padding:20px 0 60px}.member-table{font-size:12px}}\n\n\n/* YouTube videos in news: responsive embedded playback and authoring widgets */\n.article-video {position:relative;width:100%;max-width:960px;aspect-ratio:16/9;margin:26px auto;background:#050b1b;border:1px solid #335e8e;border-radius:12px;overflow:hidden;box-shadow:0 12px 40px #0008}\n.article-video iframe {position:absolute;inset:0;width:100%;height:100%;border:0}\n.toolbar-separator {width:1px;align-self:stretch;background:#394d70;margin:4px 6px}\n.video-insert-button {color:#6cddff!important;border:1px solid #3784aa!important;background:#06233c!important;white-space:nowrap}\n.video-insert-button:hover {background:#103c59!important}\n.editor-video-hint {font-size:12px;color:#a9bbd9;line-height:1.6;margin:10px 0}\n.rich-editor .youtube-embed {display:block;max-width:700px;margin:8px auto;padding:30px 18px;border:1px dashed #48baf1;border-radius:10px;background:linear-gradient(120deg,#07152c,#163454);text-align:center;color:#84e4ff;font-weight:700;cursor:pointer;user-select:none}\n.rich-editor .youtube-embed:hover,.rich-editor .youtube-embed:focus {outline:2px solid #5ed9ff}\n.rich-editor .editor-video-block {margin:12px 0}\n"
CATEGORIES = ("Workprint", "CAM", "35mm", "Screener", "VHS", "Betamax", "Laserdisc")
SORT = {
    "newest": "created_at DESC, id DESC",
    "oldest": "created_at ASC, id ASC",
    "az": "title COLLATE NOCASE ASC, id DESC",
    "za": "title COLLATE NOCASE DESC, id DESC",
    "year_new": "release_year IS NULL, release_year DESC, title COLLATE NOCASE ASC",
    "year_old": "release_year IS NULL, release_year ASC, title COLLATE NOCASE ASC",
    "updated": "updated_at DESC, id DESC",
}
# Explicit field allow-list: no external download links in this preview.
MOVIE_FIELDS = ("id,title,category,release_year,workprint_date,genre,director,"
                "runtime,official_runtime,synopsis,differences,differences_is_html,"
                "notes,source_details,file_size,file_format,video_resolution,"
                "audio_details,poster,published,created_at,updated_at")
ARTICLE_FIELDS = "id,title,excerpt,body,cover,status,published,created_at,updated_at"


def rows(sql, args=()):
    stmt = request.environ["workers.env"].DB.prepare(sql)
    if args:
        stmt = stmt.bind(*args)
    result = run_sync(stmt.all())
    records = result.results
    # Current Python Workers expose D1 results as native Python lists.
    # Retain support for older JS proxy results without converting twice.
    if hasattr(records, "to_py"):
        records = records.to_py()
    return [row.to_py() if hasattr(row, "to_py") else row for row in records]


def ready():
    found = rows("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('movies','articles','screenshots')")
    return {r["name"] for r in found} == {"movies", "articles", "screenshots"}


def render_catalogue(template, schema_ready, **kwargs):
    canonical = None
    if schema_ready and public_indexable():
        canonical = PUBLIC_ORIGIN + request.path
    return render_template(template, schema_ready=schema_ready, is_admin=False,
                           member=None, categories_nav=CATEGORIES, seo_canonical=canonical, **kwargs)


class PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)
    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p", "div", "li", "h2", "h3", "blockquote"):
            self.parts.append("\n")


@app.template_filter("rich_differences")
def preview_rich_text(value, is_html=0):
    # Render imported rich-text as escaped plain text in this staging build.
    # Full sanitised formatting/YouTube support is a later migration step.
    if is_html:
        parser = PlainHTML()
        parser.feed(value or "")
        value = "".join(parser.parts)
    return Markup("<br>").join(escape(value or "").split("\n"))


@app.get("/catalogue-preview/style.css")
def catalogue_css():
    return Response(CATALOGUE_CSS, mimetype="text/css")


@app.get("/catalogue-preview")
def home():
    ok = ready()
    articles = rows(f"SELECT {ARTICLE_FIELDS} FROM articles WHERE published=1 ORDER BY created_at DESC,id DESC LIMIT 100") if ok else []
    recent = rows(f"SELECT {MOVIE_FIELDS} FROM movies WHERE published=1 ORDER BY created_at DESC,id DESC LIMIT 6") if ok else []
    return render_catalogue("home.html", ok, articles=articles, recent=recent)


@app.get("/catalogue-preview/browse")
def browse():
    ok = ready()
    q = request.args.get("q", "").strip()[:120]
    category = request.args.get("category", "")
    genre = request.args.get("genre", "").strip()[:90]
    year = request.args.get("year", "")
    order = request.args.get("order", "newest")
    if order not in SORT:
        order = "newest"
    sql = f"SELECT {MOVIE_FIELDS} FROM movies WHERE published=1"
    args = []
    if q:
        sql += " AND (title LIKE ? OR synopsis LIKE ? OR differences LIKE ?)"
        args.extend([f"%{q}%"] * 3)
    if category in CATEGORIES:
        sql += " AND category=?"
        args.append(category)
    if genre:
        sql += " AND genre=?"
        args.append(genre)
    if re.fullmatch(r"[0-9]{4}", year):
        sql += " AND release_year=?"
        args.append(int(year))
    movies = rows(sql + " ORDER BY " + SORT[order] + " LIMIT 500", args) if ok else []
    genres = [r["genre"] for r in rows("SELECT DISTINCT genre FROM movies WHERE published=1 AND genre IS NOT NULL AND genre != '' ORDER BY genre")] if ok else []
    return render_catalogue("browse.html", ok, movies=movies, genres=genres,
                            categories=CATEGORIES, category=category, genre=genre,
                            q=q, year=year, order=order)


@app.get("/catalogue-preview/categories")
def category_index():
    ok = ready()
    counts = {r["category"]: r["total"] for r in rows("SELECT category, COUNT(*) AS total FROM movies WHERE published=1 GROUP BY category")} if ok else {}
    return render_catalogue("categories.html", ok, categories=CATEGORIES, counts=counts)


@app.get("/catalogue-preview/film/<int:mid>")
def detail(mid):
    if not ready():
        abort(404)
    movies = rows(f"SELECT {MOVIE_FIELDS} FROM movies WHERE published=1 AND id=?", (mid,))
    if not movies:
        abort(404)
    pics = rows("SELECT filename,caption FROM screenshots WHERE movie_id=? ORDER BY id", (mid,))
    available = approved_external_available(mid)
    token = ""
    if available and current_preview_member():
        token = signer(member_key(),"external-file-v1").dumps(str(mid)+":"+member_token_hash(request.cookies[MEMBER_COOKIE]))
    return render_catalogue("detail.html", True, movie=movies[0], pics=pics,
                            external_available=available, external_token=token)


@app.get("/catalogue-preview/news/<int:aid>")
def article_detail(aid):
    if not ready():
        abort(404)
    articles = rows(f"SELECT {ARTICLE_FIELDS} FROM articles WHERE published=1 AND id=?", (aid,))
    if not articles:
        abort(404)
    return render_catalogue("article.html", True, article=articles[0])


@app.get("/catalogue-preview/uploads/<path:name>")
def uploads(name):
    # Only an image linked to a published record may be read through this route.
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}\.(?:png|jpe?g|gif|webp)", name, re.I) or not ready():
        abort(404)
    match = rows("SELECT 1 AS ok FROM movies WHERE published=1 AND poster=? UNION ALL SELECT 1 FROM articles WHERE published=1 AND cover=? UNION ALL SELECT 1 FROM screenshots s JOIN movies m ON m.id=s.movie_id WHERE m.published=1 AND s.filename=? LIMIT 1", (name,name,name))
    if not match:
        abort(404)
    return serve_image_object(name)


def serve_image_object(name):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}\.(?:png|jpe?g|gif|webp)", name, re.I):
        abort(404)
    obj = run_sync(request.environ["workers.env"].UPLOADS.get(name))
    if not obj:
        abort(404)
    ext = name.rsplit(".",1)[-1].lower()
    mime = {"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png","gif":"image/gif","webp":"image/webp"}[ext]
    # Python Workers may expose R2 data directly as bytes, or as a JS
    # buffer depending on the runtime binding implementation.
    if hasattr(obj, "arrayBuffer"):
        raw = run_sync(obj.arrayBuffer())
    elif hasattr(obj, "array_buffer"):
        raw = run_sync(obj.array_buffer())
    else:
        from js import Response as JSResponse
        raw = run_sync(JSResponse.new(obj.body).arrayBuffer())
    if hasattr(raw, "to_py"):
        raw = raw.to_py()
    payload = raw.tobytes() if hasattr(raw, "tobytes") else bytes(raw)
    return Response(payload, mimetype=mime, headers={"X-Content-Type-Options":"nosniff"})


@app.after_request
def prevent_indexing(response):
    if response.status_code == 200 and (public_indexable() or (production_host() and request.endpoint in ("public_sitemap", "staging_robots", "catalogue_css", "uploads", "legacy_upload"))):
        response.headers.pop("X-Robots-Tag", None)
    else:
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if "Referrer-Policy" not in response.headers:
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response



# Stage: authenticated read-only administrator dashboard.
# Separate preview cookies; never expose credentials, hashes, or member data.
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from itsdangerous import URLSafeTimedSerializer, BadData
from flask import make_response, redirect, url_for

ADMIN_COOKIE = "__Host-workprint-preview-admin"
LOGIN_CSRF_COOKIE = "__Host-workprint-preview-login-csrf"
ADMIN_TTL = 1800


def admin_credentials():
    env = request.environ.get("workers.env")
    if env is None:
        return None
    try:
        password = getattr(env, "ADMIN_PASSWORD", None)
        secret = getattr(env, "SECRET_KEY", None)
    except Exception:
        return None
    if not isinstance(password, str) or not isinstance(secret, str):
        return None
    if len(secret) < 32 or len(password) < 12 or len(password) > 512:
        return None
    # Password rotation invalidates existing sessions. Only the derived key
    # is used for signing; the actual credentials never enter a cookie.
    key = hmac.new(secret.encode("utf-8"), password.encode("utf-8"),
                   hashlib.sha256).hexdigest()
    return password, key


def signer(key, purpose):
    return URLSafeTimedSerializer(key, salt="workprint-preview-" + purpose,
                                  signer_kwargs={"digest_method": hashlib.sha256})


def load_token(key, purpose, token, max_age=ADMIN_TTL):
    if not token or len(token) > 2048:
        return None
    try:
        value = signer(key, purpose).loads(token, max_age=max_age)
        return value if isinstance(value, str) else None
    except (BadData, ValueError, TypeError):
        return None


def equal(left, right):
    return isinstance(left, str) and isinstance(right, str) and hmac.compare_digest(
        left.encode("utf-8"), right.encode("utf-8"))


def admin_session():
    credentials = admin_credentials()
    if not credentials:
        return None
    return load_token(credentials[1], "session", request.cookies.get(ADMIN_COOKIE))


def set_private_cookie(response, name, value, age):
    response.set_cookie(name, value, max_age=age, secure=True,
                        httponly=True, samesite="Strict", path="/")


def login_page(credentials, error="", status=200):
    if not credentials:
        return render_catalogue("preview_admin_login.html", ready(),
                                configured=False, error=error, csrf_token=""), 503
    nonce = secrets.token_urlsafe(32)
    token = signer(credentials[1], "login-csrf").dumps(nonce)
    response = make_response(render_catalogue("preview_admin_login.html", ready(),
                             configured=True, error=error, csrf_token=token), status)
    set_private_cookie(response, LOGIN_CSRF_COOKIE, token, 600)
    return response


def record_admin_attempt(key):
    # Atomic conditional INSERT prevents parallel guesses bypassing the
    # per-connection quota. Existing auth_attempts table is reused with
    # a distinct hashed preview-admin prefix.
    ip = request.headers.get("CF-Connecting-IP") or request.remote_addr or "unknown"
    identity = "preview-admin:" + hmac.new(key.encode(), ip.encode(),
                                          hashlib.sha256).hexdigest()
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=15)).isoformat()
    attempt = rows(
        "INSERT INTO auth_attempts (ip, attempted_at) "
        "SELECT ?, ? WHERE (SELECT COUNT(*) FROM auth_attempts "
        "WHERE ip=? AND attempted_at>?) < 8 RETURNING id",
        (identity, now.isoformat(), identity, cutoff))
    # Limit old preview admin entries without modifying existing member history.
    rows("DELETE FROM auth_attempts WHERE ip LIKE 'preview-admin:%' AND attempted_at < ?",
         ((now - timedelta(days=2)).isoformat(),))
    return bool(attempt)


@app.route("/catalogue-preview/admin/login", methods=["GET", "POST"])
def preview_admin_login():
    credentials = admin_credentials()
    if not credentials:
        return login_page(None)
    if admin_session():
        return redirect(url_for("preview_admin_dashboard"), code=303)
    if request.method == "GET":
        return login_page(credentials)
    if request.content_length is None or request.content_length > 8192:
        abort(413)
    supplied = request.form.get("csrf_token", "")
    cookie = request.cookies.get(LOGIN_CSRF_COOKIE, "")
    if not equal(supplied, cookie) or not load_token(credentials[1], "login-csrf", supplied, 600):
        return login_page(credentials, "Sign-in form expired. Please try again.", 400)
    try:
        allowed = record_admin_attempt(credentials[1])
    except Exception:
        # Fail closed if the rate-limit database cannot be reached.
        return login_page(credentials, "Sign-in temporarily unavailable.", 503)
    if not allowed:
        return login_page(credentials, "Too many attempts. Try again in 15 minutes.", 429)
    password = request.form.get("password", "")
    if len(password) > 512 or not equal(password, credentials[0]):
        return login_page(credentials, "Incorrect admin password.", 401)
    token = signer(credentials[1], "session").dumps(secrets.token_urlsafe(32))
    response = redirect(url_for("preview_admin_dashboard"), code=303)
    set_private_cookie(response, ADMIN_COOKIE, token, ADMIN_TTL)
    response.delete_cookie(LOGIN_CSRF_COOKIE, path="/", secure=True,
                           httponly=True, samesite="Strict")
    return response


@app.get("/catalogue-preview/admin")
def preview_admin_dashboard():
    session_id = admin_session()
    if not session_id:
        return redirect(url_for("preview_admin_login"), code=303)
    credentials = admin_credentials()
    # Fixed table names only, and counts rather than any personal records.
    tables = (("Films", "movies"), ("News articles", "articles"),
              ("Members", "members"), ("Screenshots", "screenshots"),
              ("Download history", "download_requests"))
    counts = [(label, rows("SELECT COUNT(*) AS n FROM " + table)[0]["n"])
              for label, table in tables]
    token = signer(credentials[1], "logout-csrf").dumps(session_id)
    return render_catalogue("preview_admin_dashboard.html", True,
                            counts=counts, csrf_token=token)


@app.post("/catalogue-preview/admin/logout")
def preview_admin_logout():
    session_id = admin_session()
    credentials = admin_credentials()
    if not session_id or not credentials:
        abort(403)
    token = request.form.get("csrf_token", "")
    if not equal(load_token(credentials[1], "logout-csrf", token), session_id):
        abort(403)
    response = redirect(url_for("preview_admin_login"), code=303)
    response.delete_cookie(ADMIN_COOKIE, path="/", secure=True,
                           httponly=True, samesite="Strict")
    return response



# Stage: film metadata and reversible publication status; no hard deletion.
DRAFT_FIELDS = (
    ("workprint_date", "Edition date / label", 200, False),
    ("genre", "Genre", 160, False),
    ("director", "Director", 200, False),
    ("runtime", "Edition runtime", 100, False),
    ("official_runtime", "Official runtime", 100, False),
    ("synopsis", "Synopsis", 12000, True),
    ("differences", "Differences from official release", 75000, True),
    ("notes", "Archivist notes", 12000, True),
    ("source_details", "Source details", 4000, True),
    ("file_size", "File size", 100, False),
    ("file_format", "File format", 100, False),
    ("video_resolution", "Video resolution", 100, False),
    ("audio_details", "Audio details", 500, False),
)


def film_action_token(session_id):
    credentials = admin_credentials()
    if not credentials:
        abort(403)
    return signer(credentials[1], "film-write-csrf").dumps(session_id)


def verify_film_action(session_id):
    if request.content_length is None or request.content_length > 400000:
        abort(413)
    credentials = admin_credentials()
    if not credentials or not equal(load_token(credentials[1], "film-write-csrf",
                    request.form.get("csrf_token", "")), session_id):
        abort(403)


def draft_values(existing=None):
    values = {}
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "")
    year = request.form.get("release_year", "").strip()
    if not title or len(title) > 200:
        raise ValueError("Enter a film title of at most 200 characters.")
    if category not in CATEGORIES:
        raise ValueError("Select a valid category.")
    if year and (not re.fullmatch(r"[0-9]{4}", year) or not 1880 <= int(year) <= 2200):
        raise ValueError("Enter a valid release year.")
    values.update(title=title, category=category, release_year=int(year) if year else None)
    for name, label, limit, multiline in DRAFT_FIELDS:
        raw = request.form.get(name, "")
        original = existing.get(name) if existing else None
        if existing and raw.replace("\r\n", "\n").replace("\r", "\n") == (original or "").replace("\r\n", "\n").replace("\r", "\n"):
            values[name] = original
            continue
        value = raw.strip()
        if len(value) > limit:
            raise ValueError(label + " is too long.")
        values[name] = value
    return values


def blank_draft():
    return dict({"id": None, "title": "", "category": "Workprint", "release_year": None,
                 "updated_at": "", "differences_is_html": 0},
                **{name: "" for name, _, _, _ in DRAFT_FIELDS})


def draft_form(movie, session_id, error="", status=200):
    return render_catalogue("preview_film_form.html", True, movie=movie,
                            fields=DRAFT_FIELDS, csrf_token=film_action_token(session_id),
                            error=error, saved=request.args.get("saved") == "1"), status


@app.get("/catalogue-preview/admin/films")
def preview_film_manager():
    if not admin_session():
        return redirect(url_for("preview_admin_login"), code=303)
    films = rows("SELECT id,title,category,release_year,published FROM movies ORDER BY id DESC LIMIT 1000")
    return render_catalogue("preview_film_manager.html", True, films=films)


@app.route("/catalogue-preview/admin/films/new", methods=["GET", "POST"])
def preview_film_new():
    session_id = admin_session()
    if not session_id:
        return redirect(url_for("preview_admin_login"), code=303)
    if request.method == "GET":
        return draft_form(blank_draft(), session_id)
    verify_film_action(session_id)
    try:
        values = draft_values()
    except ValueError as exc:
        movie = blank_draft()
        movie.update({name: request.form.get(name, "") for name in movie if name not in ("id", "updated_at", "differences_is_html")})
        return draft_form(movie, session_id, str(exc), 400)
    now = datetime.now(timezone.utc).isoformat()
    values.update(published=0, differences_is_html=int(request.form.get("differences_visual")=="1"), created_at=now, updated_at=now)
    columns = ",".join(values)
    placeholders = ",".join("?" for _ in values)
    inserted = rows("INSERT INTO movies (" + columns + ") VALUES (" + placeholders + ") RETURNING id",
                    tuple(values.values()))
    if len(inserted) != 1:
        abort(503)
    return redirect(url_for("preview_film_edit", mid=inserted[0]["id"], saved=1), code=303)


@app.route("/catalogue-preview/admin/films/<int:mid>/edit", methods=["GET", "POST"])
def preview_film_edit(mid):
    session_id = admin_session()
    if not session_id:
        return redirect(url_for("preview_admin_login"), code=303)
    found = rows("SELECT " + MOVIE_FIELDS + " FROM movies WHERE id=?", (mid,))
    if not found:
        abort(404)
    movie = found[0]
    if request.method == "GET":
        return draft_form(movie, session_id)
    verify_film_action(session_id)
    try:
        values = draft_values(movie)
    except ValueError as exc:
        return draft_form(movie, session_id, str(exc), 400)
    expected = request.form.get("updated_at", "")
    if not equal(expected, movie["updated_at"]):
        return draft_form(movie, session_id, "This draft has changed. Reload it before saving.", 409)
    # Preserve original HTML if the editor did not change the differences.
    if values["differences"] != movie.get("differences"):
        values["differences_is_html"] = int(request.form.get("differences_visual")=="1")
    values["updated_at"] = datetime.now(timezone.utc).isoformat()
    assignments = ",".join(name + "=?" for name in values)
    changed = rows("UPDATE movies SET " + assignments + " WHERE id=? AND updated_at=? RETURNING id",
                   (*values.values(), mid, expected))
    if len(changed) != 1:
        return draft_form(movie, session_id, "This draft changed. Reload before saving.", 409)
    return redirect(url_for("preview_film_edit", mid=mid, saved=1), code=303)



@app.post("/catalogue-preview/admin/films/<int:mid>/visibility")
def preview_film_visibility(mid):
    session_id = admin_session()
    if not session_id:
        abort(403)
    verify_film_action(session_id)
    wanted = request.form.get("published", "")
    expected = request.form.get("updated_at", "")
    if wanted not in ("0", "1") or not expected:
        abort(400)
    # Never delete a record or detach images. Optimistic concurrency protects edits.
    changed = rows("UPDATE movies SET published=?, updated_at=? WHERE id=? AND updated_at=? RETURNING id",
                   (int(wanted), datetime.now(timezone.utc).isoformat(), mid, expected))
    if len(changed) != 1:
        abort(409, "Film changed. Reload the edit page before trying again.")
    return redirect(url_for("preview_film_edit", mid=mid, saved=1), code=303)



# Stage: authenticated film artwork management. One bounded upload per request.
MAX_IMAGE = 5 * 1024 * 1024


def image_form(movie, session_id, error="", status=200):
    pics = rows("SELECT id,filename,caption FROM screenshots WHERE movie_id=? ORDER BY id", (movie["id"],))
    return render_catalogue("preview_film_images.html", True, movie=movie, pics=pics,
                            csrf_token=film_action_token(session_id), error=error,
                            saved=request.args.get("saved") == "1"), status


def image_kind(data):
    # Derive the extension from signature, not the user-supplied filename.
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif", "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    raise ValueError("Choose a valid JPG, PNG, GIF or WebP file.")


@app.route("/catalogue-preview/admin/films/<int:mid>/images", methods=["GET", "POST"])
def preview_film_images(mid):
    session_id = admin_session()
    if not session_id:
        return redirect(url_for("preview_admin_login"), code=303)
    found = rows("SELECT id,title,poster,published,updated_at FROM movies WHERE id=?", (mid,))
    if not found:
        abort(404)
    movie = found[0]
    if request.method == "GET":
        return image_form(movie, session_id)
    if request.content_length is None or request.content_length > MAX_IMAGE + 65536:
        abort(413, "Image upload exceeds 5 MiB.")
    credentials = admin_credentials()
    if not credentials or not equal(load_token(credentials[1], "film-write-csrf",
                    request.form.get("csrf_token", "")), session_id):
        abort(403)
    kind = request.form.get("kind")
    if kind not in ("poster", "screenshot"):
        abort(400)
    expected = request.form.get("updated_at", "")
    if kind == "poster" and not equal(expected, movie["updated_at"]):
        return image_form(movie, session_id, "The film changed. Reload this page.", 409)
    caption = request.form.get("caption", "").strip()
    if len(caption) > 200:
        return image_form(movie, session_id, "Caption is too long.", 400)
    file = request.files.get("image")
    if not file or not file.filename:
        return image_form(movie, session_id, "Select an image first.", 400)
    try:
        data = file.stream.read(MAX_IMAGE + 1)
        if len(data) > MAX_IMAGE:
            raise ValueError("The image exceeds 5 MiB.")
        extension, mime = image_kind(data)
    except ValueError as exc:
        return image_form(movie, session_id, str(exc), 400)
    from pyodide.ffi import to_js
    from js import Object, Uint8Array
    key = secrets.token_hex(16) + "." + extension
    options = to_js({"httpMetadata": {"contentType": mime}}, dict_converter=Object.fromEntries)
    # R2 accepts ArrayBufferView; explicitly convert Python bytes to a typed array.
    buffer = Uint8Array.new(to_js(data))
    stored = run_sync(request.environ["workers.env"].UPLOADS.put(key, buffer, options))
    if not stored:
        return image_form(movie, session_id, "Image storage did not confirm the upload.", 503)
    if kind == "poster":
        changed = rows("UPDATE movies SET poster=?,updated_at=? WHERE id=? AND updated_at=? RETURNING id",
                       (key, datetime.now(timezone.utc).isoformat(), mid, expected))
    else:
        changed = rows("INSERT INTO screenshots (movie_id,filename,caption) SELECT id,?,? FROM movies WHERE id=? RETURNING id",
                       (key, caption, mid))
    if len(changed) != 1:
        # Do not delete objects when the database outcome is uncertain.
        # Unreferenced objects are private; retain for later reconciliation.
        return image_form(movie, session_id, "The film changed before the image could be linked. Reload and check the gallery.", 409)
    return redirect(url_for("preview_film_images", mid=mid, saved=1), code=303)


@app.get("/catalogue-preview/admin/films/<int:mid>/image/<path:name>")
def preview_admin_image(mid, name):
    if not admin_session():
        abort(403)
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}\.(?:png|jpe?g|gif|webp)", name, re.I):
        abort(404)
    found = rows("SELECT 1 AS ok FROM movies WHERE id=? AND poster=? UNION ALL SELECT 1 FROM screenshots WHERE movie_id=? AND filename=? LIMIT 1",
                 (mid,name,mid,name))
    if not found:
        abort(404)
    return serve_image_object(name)



# News editor and safe rich-text rendering. No arbitrary HTML attributes,
# scripts, or iframe sources are copied from stored content.
from urllib.parse import urlsplit

class SafeArticleHTML(HTMLParser):
    TAGS = {"p","div","strong","b","em","i","u","h2","h3","ul","ol","li","blockquote","a","span"}
    def __init__(self, editor=False):
        super().__init__(convert_charrefs=True)
        self.editor = editor
        self.parts = []
        self.stack = []
        self.skip = None
        self.depth = 0
    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if self.skip:
            if tag == self.skip:
                self.depth += 1
            return
        if tag in ("script","style","iframe","object","svg"):
            self.skip, self.depth = tag, 1
            return
        video = attributes.get("data-youtube-id") or ""
        if tag == "span" and attributes.get("class") == "youtube-embed" and re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
            if self.editor:
                self.parts.append('<span class="youtube-embed" data-youtube-id="' + video + '">[YouTube video: ' + video + ']</span>')
            else:
                self.parts.append('<div class="article-video"><iframe src="https://www.youtube-nocookie.com/embed/' + video + '" title="YouTube video player" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe></div>')
            self.skip, self.depth = "span", 1
            return
        if tag == "br":
            self.parts.append("<br>")
            return
        if tag not in self.TAGS:
            return
        opening = "<" + tag
        if tag == "a":
            href = attributes.get("href") or ""
            try:
                valid = not any(ord(ch) < 33 or ord(ch) == 127 for ch in href) and urlsplit(href).scheme.lower() in ("http","https","mailto")
            except ValueError:
                valid = False
            if valid:
                opening += ' href="' + str(escape(href)) + '" rel="noopener noreferrer"'
        self.parts.append(opening + ">")
        self.stack.append(tag)
    def handle_endtag(self, tag):
        if self.skip:
            if tag == self.skip:
                self.depth -= 1
                if self.depth == 0:
                    self.skip = None
            return
        if tag in self.stack:
            while self.stack:
                last = self.stack.pop()
                self.parts.append("</" + last + ">")
                if last == tag:
                    break
    def handle_data(self, data):
        if not self.skip:
            self.parts.append(str(escape(data)))
    def finish(self):
        self.close()
        while self.stack:
            self.parts.append("</" + self.stack.pop() + ">")
        return Markup("".join(self.parts))


@app.template_filter("rich_differences")
def safe_rich_text(value, is_html=0):
    value = value or ""
    if is_html:
        parser = SafeArticleHTML()
        parser.feed(value)
        return parser.finish()
    return Markup("<br>").join(escape(value).split("\n"))


@app.template_filter("editor_safe_html")
def editor_safe_html(value, is_html=0):
    value = value or ""
    if is_html:
        parser = SafeArticleHTML(editor=True)
        parser.feed(value)
        return parser.finish()
    return Markup("<br>").join(escape(value).split("\n"))


def news_form(article, session_id, error="", status=200):
    return render_catalogue("preview_news_form.html", True, article=article,
                            csrf_token=film_action_token(session_id), error=error,
                            saved=request.args.get("saved") == "1"), status


def news_values():
    title = request.form.get("title", "").strip()
    excerpt = request.form.get("excerpt", "").strip()
    body = request.form.get("body", "")
    status = request.form.get("status", "")
    video = request.form.get("video", "").strip()
    if not title or len(title) > 200 or len(excerpt) > 500 or len(body) > 150000:
        raise ValueError("Check the title, summary and article length.")
    if status not in ("published", "coming_soon"):
        raise ValueError("Select a valid article type.")
    if video:
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
            raise ValueError("Enter a valid 11-character YouTube video ID.")
        body += '<p><span class="youtube-embed" data-youtube-id="' + video + '">YouTube video</span></p>'
    if len(body) > 150000:
        raise ValueError("Article is too long.")
    # Store source unchanged; the allowlisted renderer escapes all data
    # and generates any permitted embeds itself on public display.
    return (title, excerpt, body, status, int(request.form.get("published") == "1"))


@app.get("/catalogue-preview/admin/news")
def preview_news_manager():
    if not admin_session():
        return redirect(url_for("preview_admin_login"), code=303)
    articles = rows("SELECT id,title,created_at,published FROM articles ORDER BY created_at DESC,id DESC LIMIT 1000")
    return render_catalogue("preview_news_manager.html", True, articles=articles)


@app.route("/catalogue-preview/admin/news/new", methods=["GET","POST"])
def preview_news_new():
    session_id = admin_session()
    if not session_id:
        return redirect(url_for("preview_admin_login"), code=303)
    article = dict(id=None,title="",excerpt="",body="",status="published",published=0,updated_at="",cover=None)
    if request.method == "GET":
        return news_form(article, session_id)
    verify_film_action(session_id)
    try:
        title, excerpt, body, status, published = news_values()
    except ValueError as exc:
        article.update({k:request.form.get(k,"") for k in ("title","excerpt","body","status")})
        return news_form(article, session_id, str(exc), 400)
    now = datetime.now(timezone.utc).isoformat()
    # New articles always start private, even if the checkbox was selected.
    created = rows("INSERT INTO articles (title,excerpt,body,status,published,created_at,updated_at) VALUES (?,?,?,?,0,?,?) RETURNING id",
                   (title,excerpt,body,status,now,now))
    if len(created) != 1:
        abort(503)
    return redirect(url_for("preview_news_edit", aid=created[0]["id"], saved=1), code=303)


@app.route("/catalogue-preview/admin/news/<int:aid>/edit", methods=["GET","POST"])
def preview_news_edit(aid):
    session_id = admin_session()
    if not session_id:
        return redirect(url_for("preview_admin_login"), code=303)
    found = rows("SELECT " + ARTICLE_FIELDS + " FROM articles WHERE id=?", (aid,))
    if not found:
        abort(404)
    article = found[0]
    if request.method == "GET":
        return news_form(article, session_id)
    verify_film_action(session_id)
    expected = request.form.get("updated_at", "")
    if not equal(expected, article["updated_at"]):
        return news_form(article, session_id, "Article changed. Reload before saving.", 409)
    try:
        values = news_values()
    except ValueError as exc:
        article.update({k:request.form.get(k,"") for k in ("title","excerpt","body","status")})
        return news_form(article, session_id, str(exc), 400)
    changed = rows("UPDATE articles SET title=?,excerpt=?,body=?,status=?,published=?,updated_at=? WHERE id=? AND updated_at=? RETURNING id",
                   (*values,datetime.now(timezone.utc).isoformat(),aid,expected))
    if len(changed) != 1:
        abort(409, "Article changed. Reload before saving.")
    return redirect(url_for("preview_news_edit", aid=aid, saved=1), code=303)


@app.post("/catalogue-preview/admin/news/<int:aid>/cover")
def preview_news_cover(aid):
    session_id = admin_session()
    if not session_id:
        abort(403)
    if request.content_length is None or request.content_length > MAX_IMAGE + 65536:
        abort(413)
    credentials = admin_credentials()
    if not credentials or not equal(load_token(credentials[1], "film-write-csrf",
                    request.form.get("csrf_token", "")), session_id):
        abort(403)
    found = rows("SELECT " + ARTICLE_FIELDS + " FROM articles WHERE id=?", (aid,))
    if not found:
        abort(404)
    article = found[0]
    expected = request.form.get("updated_at", "")
    if not equal(expected, article["updated_at"]):
        abort(409, "Article changed. Reload before uploading.")
    file = request.files.get("image")
    if not file or not file.filename:
        return news_form(article, session_id, "Choose an image first.", 400)
    try:
        data = file.stream.read(MAX_IMAGE + 1)
        if len(data) > MAX_IMAGE:
            raise ValueError("Image exceeds 5 MiB.")
        ext,mime = image_kind(data)
    except ValueError as exc:
        return news_form(article, session_id, str(exc), 400)
    from pyodide.ffi import to_js
    from js import Object, Uint8Array
    key = secrets.token_hex(16) + "." + ext
    options = to_js({"httpMetadata":{"contentType":mime}},dict_converter=Object.fromEntries)
    stored = run_sync(request.environ["workers.env"].UPLOADS.put(key,Uint8Array.new(to_js(data)),options))
    if not stored:
        abort(503,"Storage did not confirm upload.")
    changed = rows("UPDATE articles SET cover=?,updated_at=? WHERE id=? AND updated_at=? RETURNING id",
                   (key,datetime.now(timezone.utc).isoformat(),aid,expected))
    if len(changed) != 1:
        abort(409,"Article changed. Reload before uploading.")
    return redirect(url_for("preview_news_edit",aid=aid,saved=1),code=303)


@app.get("/catalogue-preview/admin/news/<int:aid>/cover")
def preview_news_cover_view(aid):
    if not admin_session():
        abort(403)
    found = rows("SELECT cover FROM articles WHERE id=?", (aid,))
    if not found or not found[0]["cover"]:
        abort(404)
    return serve_image_object(found[0]["cover"])



# Member administration, with public account authentication deliberately disabled
# until the legacy password algorithm is verified on the deployed runtime.
@app.get("/catalogue-preview/admin/members")
def preview_member_manager():
    if not admin_session():
        return redirect(url_for("preview_admin_login"), code=303)
    q = request.args.get("q", "").strip()[:120]
    sql = ("SELECT m.id,m.username,m.email,m.created_at,m.suspended,m.daily_limit,"
           "(SELECT COUNT(*) FROM download_requests d WHERE d.member_id=m.id) AS total FROM members m")
    args = ()
    if q:
        sql += " WHERE m.username LIKE ? OR m.email LIKE ?"
        args = ("%"+q+"%", "%"+q+"%")
    records = rows(sql + " ORDER BY m.created_at DESC LIMIT 500", args)
    return render_catalogue("preview_member_manager.html", True, members=records, q=q)


@app.route("/catalogue-preview/admin/members/<int:mid>", methods=["GET","POST"])
def preview_member_detail(mid):
    sid = admin_session()
    if not sid:
        return redirect(url_for("preview_admin_login"), code=303)
    found = rows("SELECT id,username,email,suspended,daily_limit FROM members WHERE id=?", (mid,))
    if not found:
        abort(404)
    record = found[0]
    if request.method == "POST":
        verify_film_action(sid)
        status = request.form.get("suspended", "")
        limit = request.form.get("limit", "").strip()
        expected = request.form.get("expected_suspended", "")
        old_limit = request.form.get("expected_limit", "")
        if status not in ("0","1") or expected not in ("0","1"):
            abort(400)
        if any(v != "default" and (not re.fullmatch(r"[0-9]{1,2}",v) or not 1<=int(v)<=50) for v in (limit,old_limit)):
            abort(400, "Enter default or a number from 1 to 50.")
        changed = rows("UPDATE members SET suspended=?,daily_limit=? WHERE id=? AND suspended=? AND daily_limit IS ? RETURNING id",
                       (int(status),None if limit=="default" else int(limit),mid,int(expected),None if old_limit=="default" else int(old_limit)))
        if len(changed) != 1:
            abort(409,"Member settings changed. Reload before saving.")
        if status == "1":
            member_session_table()
            rows("DELETE FROM preview_member_sessions WHERE member_id=?",(mid,))
        return redirect(url_for("preview_member_detail",mid=mid,saved=1),code=303)
    history = rows("SELECT movie_title,requested_at,provider FROM download_requests WHERE member_id=? ORDER BY requested_at DESC,id DESC LIMIT 500",(mid,))
    return render_catalogue("preview_member_detail.html",True,record=record,history=history,csrf_token=film_action_token(sid),saved=request.args.get("saved")=="1")


@app.route("/catalogue-preview/admin/members/password-check", methods=["GET","POST"])
def preview_member_check():
    sid = admin_session()
    if not sid:
        return redirect(url_for("preview_admin_login"),code=303)
    # Group only by the fixed class of the hash algorithm, never return hashes/salts.
    formats = rows("SELECT CASE WHEN password_hash LIKE 'scrypt:%' THEN 'scrypt' WHEN password_hash LIKE 'pbkdf2:%' THEN 'PBKDF2' ELSE 'other' END AS method, COUNT(*) AS total FROM members GROUP BY 1")
    result = ""
    if request.method == "POST":
        verify_film_action(sid)
        from werkzeug.security import check_password_hash
        fixture = "scrypt:32768:8:1$public-test-salt$867a75bb83d09f72cbd2dd52e07bbe55ddb9329941d49110c4868f3127fb7e215bca5559d4298d58bb606a7a1812415a00c9bab9a7bac5baa94b15946c543404"
        try:
            result = "passed" if check_password_hash(fixture,"workprint-public-test") else "failed"
        except Exception:
            result = "unavailable in this runtime"
        # Fixed dummy vector only; no real password or member hash leaves this Worker.
        try:
            from js import Request as JSRequest
            helper = getattr(request.environ["workers.env"], "AUTH_COMPAT", None)
            if helper is not None:
                response = run_sync(helper.fetch(JSRequest.new("https://internal/self-test")))
                data = run_sync(response.json())
                if hasattr(data, "to_py"):
                    data = data.to_py()
                result = "passed" if response.status == 200 and data["passed"] is True else "private helper test failed"
        except Exception:
            result = "private helper unavailable or exceeded runtime limits"
    return render_catalogue("preview_member_check.html",True,formats=formats,result=result,csrf_token=film_action_token(sid))



# Member authentication uses a private Worker service, never an Internet URL.
# Sessions are server-side, random, revocable, and separate from admin sessions.
import json
import time
MEMBER_COOKIE = "__Host-workprint-preview-member"
MEMBER_FORM_COOKIE = "__Host-workprint-preview-member-form"
MEMBER_TTL = 3600
DUMMY_MEMBER_HASH = "scrypt:32768:8:1$public-test-salt$867a75bb83d09f72cbd2dd52e07bbe55ddb9329941d49110c4868f3127fb7e215bca5559d4298d58bb606a7a1812415a00c9bab9a7bac5baa94b15946c543404"


def member_key():
    env = request.environ.get("workers.env")
    secret = getattr(env, "SECRET_KEY", None) if env else None
    if not isinstance(secret, str) or len(secret) < 32:
        abort(503)
    return hmac.new(secret.encode(), b"workprint-member-preview-v1", hashlib.sha256).hexdigest()


def member_helper(path, payload):
    from js import Request as JSRequest, Object
    from pyodide.ffi import to_js
    try:
        helper = request.environ["workers.env"].AUTH_COMPAT
        options = to_js({"method":"POST","headers":{"Content-Type":"application/json"},
                         "body":json.dumps(payload)}, dict_converter=Object.fromEntries)
        response = run_sync(helper.fetch(JSRequest.new("https://internal/" + path, options)))
        if response.status != 200:
            raise RuntimeError("private auth helper not ready")
        data = run_sync(response.json())
        return data.to_py() if hasattr(data,"to_py") else data
    except Exception:
        # Do not log passwords, hashes, request bodies or helper errors.
        abort(503, "Member authentication temporarily unavailable.")


def member_csrf_page(register, error="", status=200):
    key = member_key()
    token = signer(key,"member-form").dumps(secrets.token_urlsafe(32))
    response = make_response(render_catalogue("preview_member_auth.html",ready(),
                         register=register,error=error,csrf_token=token),status)
    set_private_cookie(response,MEMBER_FORM_COOKIE,token,600)
    return response


def member_verify_form():
    if request.content_length is None or request.content_length > 8192:
        abort(413)
    submitted = request.form.get("csrf_token","")
    if not equal(submitted,request.cookies.get(MEMBER_FORM_COOKIE,"")) or not load_token(member_key(),"member-form",submitted,600):
        abort(403,"Form expired. Return to the sign-in page and try again.")


def member_rate(identity, action):
    key=member_key()
    ip=request.headers.get("CF-Connecting-IP") or request.remote_addr or "unknown"
    now=datetime.now(timezone.utc)
    cutoff=(now-timedelta(minutes=15)).isoformat()
    ip_tag="preview-member-ip:"+hmac.new(key.encode(),ip.encode(),hashlib.sha256).hexdigest()
    acct_tag="preview-member-id:"+hmac.new(key.encode(),identity.casefold().encode(),hashlib.sha256).hexdigest()
    # Each throttle is a single conditional D1 insert, not a separate count then write.
    for tag,maximum in ((ip_tag,8),(acct_tag,12)):
        recorded=rows("INSERT INTO auth_attempts(ip,attempted_at) SELECT ?,? WHERE (SELECT COUNT(*) FROM auth_attempts WHERE ip=? AND attempted_at>?) < ? RETURNING id",
                      (tag,now.isoformat(),tag,cutoff,maximum))
        if not recorded:
            return False
    rows("DELETE FROM auth_attempts WHERE ip LIKE 'preview-member-%' AND attempted_at < ?",((now-timedelta(days=2)).isoformat(),))
    return True


def member_session_table():
    rows("CREATE TABLE IF NOT EXISTS preview_member_sessions (token_hash TEXT PRIMARY KEY, member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE, expires_at INTEGER NOT NULL)")


def member_token_hash(token):
    return hmac.new(member_key().encode(),token.encode(),hashlib.sha256).hexdigest()


def current_preview_member():
    token=request.cookies.get(MEMBER_COOKIE,"")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}",token):
        return None
    member_session_table()
    found=rows("SELECT m.id,m.username,m.daily_limit FROM preview_member_sessions s JOIN members m ON m.id=s.member_id WHERE s.token_hash=? AND s.expires_at>? AND m.suspended=0",
               (member_token_hash(token),int(time.time())))
    return found[0] if found else None


def begin_member_session(mid):
    member_session_table()
    now=int(time.time())
    rows("DELETE FROM preview_member_sessions WHERE expires_at<=?",(now,))
    token=secrets.token_urlsafe(32)
    old=request.cookies.get(MEMBER_COOKIE,"")
    if re.fullmatch(r"[A-Za-z0-9_-]{43}",old):
        rows("DELETE FROM preview_member_sessions WHERE token_hash=?",(member_token_hash(old),))
    created=rows("INSERT INTO preview_member_sessions(token_hash,member_id,expires_at) SELECT ?,id,? FROM members WHERE id=? AND suspended=0 RETURNING member_id",
                 (member_token_hash(token),now+MEMBER_TTL,mid))
    if not created:
        abort(403)
    rows("UPDATE members SET last_login_at=? WHERE id=?",(datetime.now(timezone.utc).isoformat(),mid))
    response=redirect(url_for("preview_member_account"),code=303)
    set_private_cookie(response,MEMBER_COOKIE,token,MEMBER_TTL)
    response.delete_cookie(MEMBER_FORM_COOKIE,path="/",secure=True,httponly=True,samesite="Strict")
    return response


@app.route("/catalogue-preview/members/login",methods=["GET","POST"])
def preview_member_login():
    if current_preview_member():
        return redirect(url_for("preview_member_account"),code=303)
    if request.method=="GET":
        return member_csrf_page(False)
    member_verify_form()
    login=request.form.get("login","").strip()
    password=request.form.get("password","")
    if not login or len(login)>254 or not 1<=len(password)<=256:
        return member_csrf_page(False,"Incorrect credentials or account unavailable.",401)
    if not member_rate(login,"login"):
        return member_csrf_page(False,"Too many attempts. Try again in 15 minutes.",429)
    records=rows("SELECT id,password_hash,suspended FROM members WHERE username=? OR email=? LIMIT 1",(login,login))
    record=records[0] if records else None
    candidate=record["password_hash"] if record else DUMMY_MEMBER_HASH
    verified=member_helper("verify",{"password":password,"hash":candidate})
    if not record or record["suspended"] or verified.get("valid") is not True:
        return member_csrf_page(False,"Incorrect credentials or account unavailable.",401)
    return begin_member_session(record["id"])


@app.route("/catalogue-preview/members/register",methods=["GET","POST"])
def preview_member_register():
    if current_preview_member():
        return redirect(url_for("preview_member_account"),code=303)
    if request.method=="GET":
        return member_csrf_page(True)
    member_verify_form()
    username=request.form.get("username","").strip()
    email=request.form.get("email","").strip().lower()
    password=request.form.get("password","")
    if (request.form.get("website") or not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}",username)
        or len(email)>254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email)
        or not 12<=len(password)<=256 or password!=request.form.get("confirm","")):
        return member_csrf_page(True,"Check your username, email and matching passwords (at least 12 characters).",400)
    if not member_rate(email,"registration"):
        return member_csrf_page(True,"Too many attempts. Try again in 15 minutes.",429)
    generated=member_helper("hash",{"password":password}).get("hash","")
    if not re.fullmatch(r"scrypt:32768:8:1\$[a-f0-9]{32}\$[a-f0-9]{128}",generated):
        abort(503,"Member authentication temporarily unavailable.")
    # Verify the generated hash before creating an account.
    if member_helper("verify",{"password":password,"hash":generated}).get("valid") is not True:
        abort(503,"Member authentication temporarily unavailable.")
    created=rows("INSERT INTO members(username,email,password_hash,created_at) VALUES (?,?,?,?) ON CONFLICT DO NOTHING RETURNING id",
                 (username,email,generated,datetime.now(timezone.utc).isoformat()))
    if not created:
        return member_csrf_page(True,"Unable to register with these details. Try signing in instead.",409)
    return begin_member_session(created[0]["id"])


@app.get("/catalogue-preview/members/account")
def preview_member_account():
    record=current_preview_member()
    if not record:
        return redirect(url_for("preview_member_login"),code=303)
    history=rows("SELECT movie_title,requested_at,provider FROM download_requests WHERE member_id=? ORDER BY requested_at DESC,id DESC LIMIT 150",(record["id"],))
    total=rows("SELECT COUNT(*) AS n FROM download_requests WHERE member_id=?",(record["id"],))[0]["n"]
    limit=record["daily_limit"] if record["daily_limit"] is not None else 3
    csrf=signer(member_key(),"member-logout").dumps(member_token_hash(request.cookies[MEMBER_COOKIE]))
    today = preview_uk_date()
    used = rows("SELECT COUNT(*) AS n FROM download_requests WHERE member_id=? AND uk_date=?",
                (record["id"],today))[0]["n"]
    quota_token = signer(member_key(),"quota-test").dumps(member_token_hash(request.cookies[MEMBER_COOKIE])) if admin_session() else ""
    return render_catalogue("preview_member_account.html",True,record=record,history=history,total=total,
                            limit=limit,csrf_token=csrf,used=used,remaining=max(0,limit-used),
                            quota_test_token=quota_token,test_result=request.args.get("quota",""),
                            guide_token=signer(member_key(),"original-guide-v1").dumps(member_token_hash(request.cookies[MEMBER_COOKIE])),
                            guide_limited=request.args.get("guide")=="limit",
                            approved_files=approved_download_list(),
                            approved_token=signer(member_key(),"approved-doc-v1").dumps(member_token_hash(request.cookies[MEMBER_COOKIE])))


@app.post("/catalogue-preview/members/logout")
def preview_member_logout():
    token=request.cookies.get(MEMBER_COOKIE,"")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}",token) or request.content_length is None or request.content_length>8192:
        abort(403)
    digest=member_token_hash(token)
    if not equal(load_token(member_key(),"member-logout",request.form.get("csrf_token",""),MEMBER_TTL),digest):
        abort(403)
    member_session_table()
    rows("DELETE FROM preview_member_sessions WHERE token_hash=?",(digest,))
    response=redirect(url_for("preview_member_login"),code=303)
    response.delete_cookie(MEMBER_COOKIE,path="/",secure=True,httponly=True,samesite="Strict")
    return response



# Test the daily request limit without releasing any archive files or links.
# Use the same D1 history table and atomic conditional insert as future authorised
# file delivery. Test rows have a reserved provider and no associated film ID.
QUOTA_TEST_PROVIDER = "Migration quota test"
QUOTA_TEST_TITLE = "Migration test (no file delivered)"


def preview_uk_date():
    now = datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return now.astimezone(ZoneInfo("Europe/London")).date().isoformat()
    except Exception:
        # The current UK clock rules: last Sundays of March and October,
        # transition at 01:00 UTC. Fallback for runtimes without tzdata.
        march = now.replace(month=3,day=31,hour=1,minute=0,second=0,microsecond=0)
        march -= timedelta(days=(march.weekday()+1)%7)
        october = now.replace(month=10,day=31,hour=1,minute=0,second=0,microsecond=0)
        october -= timedelta(days=(october.weekday()+1)%7)
        return (now + timedelta(hours=int(march <= now < october))).date().isoformat()


@app.post("/catalogue-preview/members/quota-test")
def preview_quota_test():
    # Both a valid administrator and member session are required.
    if not admin_session():
        abort(403)
    record = current_preview_member()
    if not record:
        abort(403)
    if request.content_length is None or request.content_length > 8192:
        abort(413)
    digest = member_token_hash(request.cookies[MEMBER_COOKIE])
    if not equal(load_token(member_key(),"quota-test",request.form.get("csrf_token",""),MEMBER_TTL),digest):
        abort(403)
    action = request.form.get("action","")
    if action == "clear":
        rows("DELETE FROM download_requests WHERE member_id=? AND movie_id IS NULL AND provider=? AND movie_title=?",
             (record["id"],QUOTA_TEST_PROVIDER,QUOTA_TEST_TITLE))
        return redirect(url_for("preview_member_account",quota="cleared"),code=303)
    if action != "request":
        abort(400)
    date = preview_uk_date()
    now = datetime.now(timezone.utc).isoformat()
    # A single conditional INSERT keeps the count and allowance check atomic
    # even if several requests arrive concurrently. Read the current limit,
    # suspension status and session expiry inside the same statement.
    inserted = rows(
        "INSERT INTO download_requests(member_id,movie_id,movie_title,requested_at,uk_date,provider) "
        "SELECT m.id,NULL,?,?,?,? FROM members m JOIN preview_member_sessions s ON s.member_id=m.id "
        "WHERE m.id=? AND m.suspended=0 AND s.token_hash=? AND s.expires_at>? "
        "AND (SELECT COUNT(*) FROM download_requests d WHERE d.member_id=m.id AND d.uk_date=?) "
        "< COALESCE(m.daily_limit,3) RETURNING id",
        (QUOTA_TEST_TITLE,now,date,QUOTA_TEST_PROVIDER,record["id"],digest,int(time.time()),date))
    return redirect(url_for("preview_member_account",quota="accepted" if inserted else "limit"),code=303)



# Contact messages remain in a private D1 inbox, with separate CSRF and
# per-IP throttle. Public pages never query or display inbox contents.
CONTACT_FORM_COOKIE = "__Host-workprint-preview-contact"


def contact_page(values=None,error="",status=200,sent=False):
    key=member_key()
    token=signer(key,"contact-form").dumps(secrets.token_urlsafe(32))
    response=make_response(render_catalogue("preview_contact.html",ready(),
        values=values or dict(name="",email="",subject="",message=""),
        error=error,sent=sent,csrf_token=token),status)
    set_private_cookie(response,CONTACT_FORM_COOKIE,token,600)
    return response


@app.route("/catalogue-preview/contact",methods=["GET","POST"])
def preview_contact():
    if request.method=="GET":
        return contact_page(sent=request.args.get("sent")=="1")
    if request.content_length is None or request.content_length>65536:
        abort(413)
    token=request.form.get("csrf_token","")
    key=member_key()
    if not equal(token,request.cookies.get(CONTACT_FORM_COOKIE,"")) or not load_token(key,"contact-form",token,600):
        return contact_page(error="Form expired. Please try again.",status=403)
    if request.form.get("website","").strip():
        return redirect(url_for("preview_contact",sent=1),code=303)
    fields={"name":120,"email":254,"subject":140,"message":5000}
    values={name:request.form.get(name,"").strip() for name in fields}
    if any(not v or len(v)>fields[n] for n,v in values.items()) or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",values["email"]):
        return contact_page({n:v[:fields[n]] for n,v in values.items()},"Check your name, email, subject and message.",400)
    now=datetime.now(timezone.utc)
    ip=request.headers.get("CF-Connecting-IP") or request.remote_addr or "unknown"
    tag="preview-contact:"+hmac.new(key.encode(),ip.encode(),hashlib.sha256).hexdigest()
    cutoff=(now-timedelta(hours=1)).isoformat()
    attempt=rows("INSERT INTO contact_attempts(ip,created_at) SELECT ?,? WHERE (SELECT COUNT(*) FROM contact_attempts WHERE ip=? AND created_at>?) < 5 RETURNING id",
                 (tag,now.isoformat(),tag,cutoff))
    if not attempt:
        return contact_page(values,"Too many messages. Try again in an hour.",429)
    added=rows("INSERT INTO contact_messages(name,email,subject,message,created_at) VALUES (?,?,?,?,?) RETURNING id",
               (values["name"],values["email"],values["subject"],values["message"],now.isoformat()))
    if len(added)!=1:
        return contact_page(values,"Message could not be saved. Please try again.",503)
    rows("DELETE FROM contact_attempts WHERE ip LIKE 'preview-contact:%' AND created_at<?",((now-timedelta(days=2)).isoformat(),))
    response=redirect(url_for("preview_contact",sent=1),code=303)
    response.delete_cookie(CONTACT_FORM_COOKIE,path="/",secure=True,httponly=True,samesite="Strict")
    return response


@app.get("/catalogue-preview/donate")
def preview_donate():
    env=request.environ.get("workers.env")
    # The verified public Ko-fi address is also a deployment fallback.
    # A configured nonempty URL takes precedence and is validated below.
    link=getattr(env,"DONATION_URL",None) if env is not None else None
    if not isinstance(link,str) or not link.strip():
        link="https://ko-fi.com/switchcritch"
    link=link.strip()
    try:
        parsed=urlsplit(link)
        if (parsed.scheme!="https" or parsed.hostname not in ("ko-fi.com","www.ko-fi.com")
            or parsed.netloc not in ("ko-fi.com","www.ko-fi.com") or not parsed.path.strip("/")
            or any(ord(ch)<33 or ord(ch)==127 for ch in link)):
            link=""
    except ValueError:
        link=""
    return render_catalogue("preview_donate.html",ready(),donation_url=link)


@app.get("/catalogue-preview/admin/messages")
def preview_inbox():
    sid=admin_session()
    if not sid:
        return redirect(url_for("preview_admin_login"),code=303)
    before=request.args.get("before","")
    sql="SELECT id,name,email,subject,message,created_at,read FROM contact_messages"
    args=()
    if re.fullmatch(r"[0-9]{1,15}",before):
        sql+=" WHERE id<?"
        args=(int(before),)
    messages=rows(sql+" ORDER BY id DESC LIMIT 51",args)
    unread=rows("SELECT COUNT(*) AS n FROM contact_messages WHERE read=0")[0]["n"]
    return render_catalogue("preview_inbox.html",True,messages=messages[:50],unread=unread,
        has_more=len(messages)>50,saved=request.args.get("saved")=="1",csrf_token=film_action_token(sid))


@app.post("/catalogue-preview/admin/messages/<int:mid>/read")
def preview_inbox_read(mid):
    sid=admin_session()
    if not sid:
        abort(403)
    verify_film_action(sid)
    changed=rows("UPDATE contact_messages SET read=1 WHERE id=? RETURNING id",(mid,))
    if not changed:
        abort(404)
    return redirect(url_for("preview_inbox",saved=1),code=303)



@app.get("/catalogue-preview/admin/news/<int:aid>/preview")
def preview_news_view(aid):
    if not admin_session():
        return redirect(url_for("preview_admin_login"), code=303)
    found = rows("SELECT " + ARTICLE_FIELDS + " FROM articles WHERE id=?", (aid,))
    if not found:
        abort(404)
    response = make_response(render_catalogue("article.html", True, article=found[0], private_preview=True))
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response



# Deliberate, separate deletion confirmation for private drafts only.
# Never delete R2 objects or any member history in this action.
@app.route("/catalogue-preview/admin/delete-draft/<kind>/<int:rid>", methods=["GET","POST"])
def preview_delete_draft(kind,rid):
    sid=admin_session()
    if not sid:
        return redirect(url_for("preview_admin_login"),code=303)
    if kind not in ("film","article"):
        abort(404)
    table="movies" if kind=="film" else "articles"
    found=rows("SELECT id,title,published,updated_at FROM "+table+" WHERE id=?",(rid,))
    if not found:
        abort(404)
    record=found[0]
    if record["published"] != 0:
        abort(409,"Unpublish this record before deleting it.")
    def page(error="",status=200):
        return render_catalogue("preview_delete_draft.html",True,record=record,kind=kind,error=error,csrf_token=film_action_token(sid)),status
    if request.method=="GET":
        return page()
    verify_film_action(sid)
    if request.form.get("confirm","")!="DELETE":
        return page("Type DELETE exactly to confirm.",400)
    expected=request.form.get("updated_at","")
    if not equal(expected,record["updated_at"]):
        return page("This record has changed. Reload before deleting.",409)
    if kind=="film":
        # Confirm the imported database actually has the expected screenshot
        # cascade and FK enforcement before doing a destructive operation.
        # Guard request history in the same statement to prevent races.
        fks=rows("PRAGMA foreign_key_list(screenshots)")
        enabled=rows("PRAGMA foreign_keys")
        if not enabled or enabled[0].get("foreign_keys") != 1 or not any(
            fk.get("table")=="movies" and fk.get("from")=="movie_id" and fk.get("on_delete")=="CASCADE" for fk in fks):
            return page("Film deletion unavailable: screenshot foreign key enforcement could not be verified.",409)
        changed=rows("DELETE FROM movies WHERE id=? AND published=0 AND updated_at=? AND NOT EXISTS (SELECT 1 FROM download_requests WHERE movie_id=movies.id) RETURNING id",(rid,expected))
    else:
        changed=rows("DELETE FROM articles WHERE id=? AND published=0 AND updated_at=? RETURNING id",(rid,expected))
    if len(changed)!=1:
        return page("Deletion blocked: the record changed or has protected request history.",409)
    return redirect(url_for("preview_film_manager" if kind=="film" else "preview_news_manager",deleted=1),code=303)



# Preserve old public bookmarks on the staging Worker, without enabling
# legacy state-changing endpoints or changing the live domain.
@app.get("/browse")
def legacy_browse():
    params = {name: request.args.get(name, "") for name in
              ("q", "category", "genre", "year", "order") if name in request.args}
    return redirect(url_for("browse", **params), code=302)


@app.get("/categories")
def legacy_categories():
    return redirect(url_for("category_index"), code=302)


@app.get("/workprint/<int:mid>")
def legacy_film(mid):
    return redirect(url_for("detail", mid=mid), code=302)


@app.get("/news/<int:aid>")
def legacy_news(aid):
    return redirect(url_for("article_detail", aid=aid), code=302)


@app.get("/uploads/<path:name>")
def legacy_upload(name):
    return uploads(name)


@app.get("/contact")
def legacy_contact():
    return redirect(url_for("preview_contact"), code=302)


@app.get("/donate")
def legacy_donate():
    return redirect(url_for("preview_donate"), code=302)


@app.get("/members/login")
def legacy_member_login():
    return redirect(url_for("preview_member_login"), code=302)


@app.get("/members/register")
def legacy_member_register():
    return redirect(url_for("preview_member_register"), code=302)


@app.get("/members/account")
def legacy_member_account():
    return redirect(url_for("preview_member_account"), code=302)


@app.get("/login")
def legacy_admin_login():
    return redirect(url_for("preview_admin_login"), code=302)


PUBLIC_ORIGIN = "https://theworkprintproject.com"
PUBLIC_INDEX_ENDPOINTS = frozenset(("home", "browse", "category_index", "detail", "article_detail", "preview_donate"))


def production_host():
    return request.host.lower().split(":")[0] == "theworkprintproject.com"


def public_indexable():
    if not production_host() or request.endpoint not in PUBLIC_INDEX_ENDPOINTS or request.method not in ("GET","HEAD"):
        return False
    # Avoid indexing search/filter combinations and tracking URL variants.
    return not request.args


@app.get("/robots.txt")
def staging_robots():
    if not production_host():
        return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")
    # Account and admin routes retain noindex response headers and authentication.
    return Response("User-agent: *\nDisallow: /catalogue-preview/admin\nDisallow: /catalogue-preview/members\nDisallow: /admin\nDisallow: /members\nDisallow: /login\nDisallow: /health\nSitemap: "+PUBLIC_ORIGIN+"/sitemap.xml\n", mimetype="text/plain")


@app.get("/sitemap.xml")
def public_sitemap():
    if not production_host():
        abort(404)
    if not ready():
        abort(503)
    from xml.sax.saxutils import escape as xml_escape
    paths = [url_for("home"),url_for("browse"),url_for("category_index"),url_for("preview_donate")]
    paths.extend(url_for("detail",mid=r["id"]) for r in rows("SELECT id FROM movies WHERE published=1 ORDER BY id"))
    paths.extend(url_for("article_detail",aid=r["id"]) for r in rows("SELECT id FROM articles WHERE published=1 ORDER BY id"))
    body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    body += "".join("<url><loc>"+xml_escape(PUBLIC_ORIGIN+p)+"</loc></url>" for p in paths)
    return Response(body+"</urlset>", mimetype="application/xml")



# First actual file delivery: authored project documentation only.
# No inherited movie links, R2 object keys or arbitrary redirect targets.
ORIGINAL_GUIDE_TITLE = "The Workprint Project - Archive Guide (TXT)"
ORIGINAL_GUIDE_TEXT = """THE WORKPRINT PROJECT
Archive documentation guide

The purpose of a catalogue is to record the history of alternative film editions.
When documenting a version, identify the title, release year, edition label,
source format and measured running time. Record differences in your own words,
and distinguish confirmed observations from unverified claims.

Keep a private record of provenance and of any permission to distribute a file.
Only distribute material you created, material in the public domain in the
relevant jurisdiction, or material for which you hold suitable permission.
Membership alone does not establish a right to distribute a film.

This original text guide demonstrates the project's member file delivery.
It contains no film footage or third-party download links.
"""


@app.post("/catalogue-preview/members/download-guide")
def member_original_guide():
    record = current_preview_member()
    if not record:
        abort(403)
    if request.content_length is None or request.content_length > 8192:
        abort(413)
    digest = member_token_hash(request.cookies[MEMBER_COOKIE])
    if not equal(load_token(member_key(),"original-guide-v1",request.form.get("csrf_token",""),MEMBER_TTL),digest):
        abort(403)
    # Prepare the known, fixed original file before consuming allowance.
    response = Response(ORIGINAL_GUIDE_TEXT.encode("utf-8"), content_type="text/plain; charset=utf-8")
    response.headers["Content-Disposition"] = 'attachment; filename="workprint-archive-guide.txt"'
    response.headers["Cache-Control"] = "private, no-store"
    now = datetime.now(timezone.utc)
    date = preview_uk_date()
    inserted = rows(
        "INSERT INTO download_requests(member_id,movie_id,movie_title,requested_at,uk_date,provider) "
        "SELECT m.id,NULL,?,?,?,? FROM members m JOIN preview_member_sessions s ON s.member_id=m.id "
        "WHERE m.id=? AND m.suspended=0 AND s.token_hash=? AND s.expires_at>? "
        "AND (SELECT COUNT(*) FROM download_requests d WHERE d.member_id=m.id AND d.uk_date=?) "
        "< COALESCE(m.daily_limit,3) RETURNING id",
        (ORIGINAL_GUIDE_TITLE,now.isoformat(),date,"Original project documentation",record["id"],digest,int(time.time()),date))
    if len(inserted)!=1:
        return redirect(url_for("preview_member_account",guide="limit"),code=303)
    return response



# Separate approval registry for original/licensed/public-domain documents.
# The reserved private R2 prefix cannot match existing public image routes.
APPROVED_MAX = 5 * 1024 * 1024
APPROVED_PREFIX = "approved-documents/"


def approved_table_exists():
    return bool(rows("SELECT 1 AS ok FROM sqlite_master WHERE type='table' AND name='approved_documents'"))


def approved_init():
    rows("CREATE TABLE IF NOT EXISTS approved_documents (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, filename TEXT NOT NULL, object_key TEXT NOT NULL UNIQUE, size INTEGER NOT NULL CHECK(size BETWEEN 1 AND 5242880), digest TEXT NOT NULL, basis TEXT NOT NULL, evidence TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)), created_at TEXT NOT NULL)")


def approved_download_list():
    if not approved_table_exists():
        return []
    return rows("SELECT id,title,filename,size FROM approved_documents WHERE enabled=1 ORDER BY id DESC LIMIT 100")


def approved_admin_page(sid,error="",status=200):
    approved_init()
    files = rows("SELECT id,title,filename,size,basis,evidence,enabled FROM approved_documents ORDER BY id DESC LIMIT 100")
    return render_catalogue("approved_downloads_admin.html",True,files=files,csrf_token=film_action_token(sid),error=error,saved=request.args.get("saved")=="1"),status


@app.get("/catalogue-preview/admin/downloads")
def approved_downloads_admin():
    sid=admin_session()
    if not sid:
        return redirect(url_for("preview_admin_login"),code=303)
    return approved_admin_page(sid)


@app.post("/catalogue-preview/admin/downloads/upload")
def approved_downloads_upload():
    sid=admin_session()
    if not sid:
        abort(403)
    if request.content_length is None or request.content_length > APPROVED_MAX+65536:
        abort(413)
    credentials=admin_credentials()
    if not credentials or not equal(load_token(credentials[1],"film-write-csrf",request.form.get("csrf_token","")),sid):
        abort(403)
    title=request.form.get("title","").strip()
    basis=request.form.get("basis","")
    evidence=request.form.get("evidence","").strip()
    file=request.files.get("file")
    if not title or len(title)>150 or basis not in ("original","licensed","public-domain") or not evidence or len(evidence)>2000 or request.form.get("confirm_rights")!="1" or not file:
        return approved_admin_page(sid,"Complete the file and permission record.",400)
    filename=file.filename or ""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.-]{0,119}\.(?:txt|pdf)",filename,re.I):
        return approved_admin_page(sid,"Use a simple TXT or PDF filename.",400)
    data=file.stream.read(APPROVED_MAX+1)
    if not data or len(data)>APPROVED_MAX:
        return approved_admin_page(sid,"Files must be between 1 byte and 5 MiB.",400)
    ext=filename.rsplit(".",1)[-1].lower()
    if ext=="pdf" and not data.startswith(b"%PDF-"):
        return approved_admin_page(sid,"Not a valid PDF header.",400)
    if ext=="txt":
        try:
            data.decode("utf-8")
            if b"\x00" in data:
                raise ValueError()
        except (UnicodeError,ValueError):
            return approved_admin_page(sid,"TXT files must be UTF-8 text.",400)
    approved_init()
    from js import Object, Uint8Array
    from pyodide.ffi import to_js
    key=APPROVED_PREFIX+secrets.token_hex(24)
    digest=hashlib.sha256(data).hexdigest()
    stored=run_sync(request.environ["workers.env"].UPLOADS.put(key,Uint8Array.new(to_js(data)),to_js({"httpMetadata":{"contentType":"application/octet-stream"}},dict_converter=Object.fromEntries)))
    if not stored:
        abort(503)
    created=rows("INSERT INTO approved_documents(title,filename,object_key,size,digest,basis,evidence,created_at) VALUES (?,?,?,?,?,?,?,?) RETURNING id",
                 (title,filename,key,len(data),digest,basis,evidence,datetime.now(timezone.utc).isoformat()))
    if len(created)!=1:
        abort(503)
    return redirect(url_for("approved_downloads_admin",saved=1),code=303)


@app.post("/catalogue-preview/admin/downloads/<int:fid>/toggle")
def approved_downloads_toggle(fid):
    sid=admin_session()
    if not sid:
        abort(403)
    verify_film_action(sid)
    expected=request.form.get("expected","")
    if expected not in ("0","1") or (expected=="0" and request.form.get("confirm_rights")!="1"):
        abort(400)
    changed=rows("UPDATE approved_documents SET enabled=? WHERE id=? AND enabled=? RETURNING id",(1-int(expected),fid,int(expected)))
    if len(changed)!=1:
        abort(409)
    return redirect(url_for("approved_downloads_admin",saved=1),code=303)


@app.post("/catalogue-preview/members/downloads/<int:fid>")
def approved_download(fid):
    record=current_preview_member()
    if not record:
        abort(403)
    if request.content_length is None or request.content_length>8192:
        abort(413)
    digest=member_token_hash(request.cookies[MEMBER_COOKIE])
    if not equal(load_token(member_key(),"approved-doc-v1",request.form.get("csrf_token",""),MEMBER_TTL),digest):
        abort(403)
    if not approved_table_exists():
        abort(404)
    found=rows("SELECT id,title,filename,object_key,size,digest FROM approved_documents WHERE id=? AND enabled=1",(fid,))
    if not found:
        abort(404)
    file=found[0]
    if not re.fullmatch(r"approved-documents/[a-f0-9]{48}",file["object_key"]) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.-]{0,119}\.(?:txt|pdf)",file["filename"],re.I) or not 1<=file["size"]<=APPROVED_MAX:
        abort(503)
    date=preview_uk_date()
    used=rows("SELECT COUNT(*) AS n FROM download_requests WHERE member_id=? AND uk_date=?",(record["id"],date))[0]["n"]
    if used >= (record["daily_limit"] if record["daily_limit"] is not None else 3):
        return redirect(url_for("preview_member_account",guide="limit"),code=303)
    obj=run_sync(request.environ["workers.env"].UPLOADS.get(file["object_key"]))
    if not obj or obj.size!=file["size"]:
        abort(503)
    if hasattr(obj,"arrayBuffer"):
        raw=run_sync(obj.arrayBuffer())
    elif hasattr(obj,"array_buffer"):
        raw=run_sync(obj.array_buffer())
    else:
        from js import Response as JSResponse
        raw=run_sync(JSResponse.new(obj.body).arrayBuffer())
    if hasattr(raw,"to_py"):
        raw=raw.to_py()
    data=raw.tobytes() if hasattr(raw,"tobytes") else bytes(raw)
    if len(data)!=file["size"] or hashlib.sha256(data).hexdigest()!=file["digest"]:
        abort(503)
    response=Response(data,content_type="application/octet-stream")
    response.headers["Content-Disposition"]='attachment; filename="'+file["filename"]+'"'
    inserted=rows("INSERT INTO download_requests(member_id,movie_id,movie_title,requested_at,uk_date,provider) "
                  "SELECT m.id,NULL,f.title,?,?,? FROM members m JOIN preview_member_sessions s ON s.member_id=m.id JOIN approved_documents f ON f.id=? "
                  "WHERE m.id=? AND m.suspended=0 AND s.token_hash=? AND s.expires_at>? AND f.enabled=1 AND f.digest=? "
                  "AND (SELECT COUNT(*) FROM download_requests d WHERE d.member_id=m.id AND d.uk_date=?) < COALESCE(m.daily_limit,3) RETURNING id",
                  (datetime.now(timezone.utc).isoformat(),date,"Approved project document",fid,record["id"],digest,int(time.time()),file["digest"],date))
    if len(inserted)!=1:
        abort(409,"Download unavailable or daily allowance reached. No request recorded.")
    return response



# Explicit per-file permission registry. No legacy download field is read,
# migrated or exposed by this code. External delivery uses normal share pages.
def approved_external_exists():
    return bool(rows("SELECT 1 AS ok FROM sqlite_master WHERE type='table' AND name='approved_external_files'"))


def approved_external_init():
    rows("CREATE TABLE IF NOT EXISTS approved_external_files (movie_id INTEGER PRIMARY KEY REFERENCES movies(id) ON DELETE CASCADE, link TEXT NOT NULL, basis TEXT NOT NULL, evidence TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)), revision TEXT NOT NULL, updated_at TEXT NOT NULL)")


def approved_pixeldrain_link(value):
    # Accept approved Pixeldrain share links.
    if not isinstance(value, str) or len(value) > 150:
        return ""

    match = re.fullmatch(
        r"https://pixeldrain\.com/(u|d)/([A-Za-z0-9]{8})/?",
        value.strip()
    )

    if not match:
        return ""

    return f"https://pixeldrain.com/{match.group(1)}/{match.group(2)}"


def approved_external_available(mid):
    if not approved_external_exists():
        return False
    return bool(rows("SELECT 1 AS ok FROM approved_external_files WHERE movie_id=? AND enabled=1",(mid,)))


@app.route("/catalogue-preview/admin/films/<int:mid>/external-download",methods=["GET","POST"])
def approved_external_settings(mid):
    sid=admin_session()
    if not sid:
        return redirect(url_for("preview_admin_login"),code=303)
    films=rows("SELECT id,title,published FROM movies WHERE id=?",(mid,))
    if not films:
        abort(404)
    approved_external_init()
    existing=rows("SELECT link,basis,evidence,enabled,revision FROM approved_external_files WHERE movie_id=?",(mid,))
    record=existing[0] if existing else {}
    def page(error="",status=200):
        return render_catalogue("approved_external_settings.html",True,movie=films[0],record=record,
                                csrf_token=film_action_token(sid),error=error,saved=request.args.get("saved")=="1"),status
    if request.method=="GET":
        return page()
    verify_film_action(sid)
    expected=request.form.get("revision","")
    if expected != record.get("revision",""):
        return page("The record has changed. Reload before continuing.",409)
    action=request.form.get("action","")
    revision=secrets.token_hex(24)
    now=datetime.now(timezone.utc).isoformat()
    if action=="save":
        link=approved_pixeldrain_link(request.form.get("link",""))
        basis=request.form.get("basis","")
        evidence=request.form.get("evidence","").strip()
        if not link or basis not in ("original","licensed","public-domain") or not 20<=len(evidence)<=2000 or request.form.get("confirm")!="1":
            return page("Enter a valid Pixeldrain single-file share URL and a specific permission record of at least 20 characters.",400)
        if existing:
            updated=rows("UPDATE approved_external_files SET link=?,basis=?,evidence=?,enabled=0,revision=?,updated_at=? WHERE movie_id=? AND revision=? RETURNING movie_id",
                         (link,basis,evidence,revision,now,mid,expected))
        else:
            updated=rows("INSERT INTO approved_external_files(movie_id,link,basis,evidence,revision,updated_at) VALUES (?,?,?,?,?,?) ON CONFLICT DO NOTHING RETURNING movie_id",
                         (mid,link,basis,evidence,revision,now))
    elif action in ("enable","disable") and existing:
        if action=="enable" and (request.form.get("confirm")!="1" or not approved_pixeldrain_link(record["link"])):
            return page("Confirm current distribution rights before enabling.",400)
        updated=rows("UPDATE approved_external_files SET enabled=?,revision=?,updated_at=? WHERE movie_id=? AND revision=? RETURNING movie_id",
                     (int(action=="enable"),revision,now,mid,expected))
    else:
        abort(400)
    if len(updated)!=1:
        return page("The record has changed. Reload before continuing.",409)
    return redirect(url_for("approved_external_settings",mid=mid,saved=1),code=303)


@app.post("/catalogue-preview/film/<int:mid>/external-download")
def approved_external_request(mid):
    record=current_preview_member()
    if not record:
        abort(403)
    if request.content_length is None or request.content_length>8192:
        abort(413)
    digest=member_token_hash(request.cookies[MEMBER_COOKIE])
    if not equal(load_token(member_key(),"external-file-v1",request.form.get("csrf_token",""),MEMBER_TTL),str(mid)+":"+digest):
        abort(403)
    if not approved_external_exists():
        abort(404)
    found=rows("SELECT f.link,f.revision FROM approved_external_files f JOIN movies v ON v.id=f.movie_id WHERE f.movie_id=? AND f.enabled=1 AND v.published=1",(mid,))
    if not found:
        abort(404)
    link=approved_pixeldrain_link(found[0]["link"])
    if not link:
        abort(503)
    date=preview_uk_date()
    inserted=rows("INSERT INTO download_requests(member_id,movie_id,movie_title,requested_at,uk_date,provider) "
                  "SELECT m.id,v.id,v.title,?,?,? FROM members m JOIN preview_member_sessions s ON s.member_id=m.id "
                  "JOIN movies v ON v.id=? JOIN approved_external_files f ON f.movie_id=v.id "
                  "WHERE m.id=? AND m.suspended=0 AND s.token_hash=? AND s.expires_at>? "
                  "AND v.published=1 AND f.enabled=1 AND f.revision=? AND f.link=? "
                  "AND (SELECT COUNT(*) FROM download_requests d WHERE d.member_id=m.id AND d.uk_date=?) < COALESCE(m.daily_limit,3) RETURNING id",
                  (datetime.now(timezone.utc).isoformat(),date,"Pixeldrain (authorised link)",mid,record["id"],digest,int(time.time()),found[0]["revision"],link,date))
    if len(inserted)!=1:
        return redirect(url_for("preview_member_account",guide="limit"),code=303)
    response=redirect(link,code=303)
    response.headers["Referrer-Policy"]="no-referrer"
    return response


Default = wsgi.entrypoint(app)
