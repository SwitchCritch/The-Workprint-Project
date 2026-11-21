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


@app.route("/", defaults={"path": ""}, methods=["GET", "HEAD"])
@app.route("/<path:path>", methods=["GET", "HEAD"])
def static_preview(path):
    # For now, do not expose login, downloads, admin, or user-data endpoints.
    if path not in ("", "index.html", "style.css"):
        return {"error": "The full archive is not yet migrated."}, 404
    assets = request.environ["workers.env"].ASSETS
    asset_response = run_sync(assets.fetch(f"https://assets.local/{'' if path == 'index.html' else path}"))
    body = run_sync(asset_response.bytes())
    return Response(body, status=asset_response.status, headers=asset_response.headers)


Default = wsgi.entrypoint(app)
