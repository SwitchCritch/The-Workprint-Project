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
    # For now, do not expose login, downloads, admin, or user-data endpoints.
    if path not in ("", "index.html", "style.css"):
        return {"error": "The full archive is not yet migrated."}, 404
    assets = request.environ["workers.env"].ASSETS
    asset_response = run_sync(assets.fetch(f"https://assets.local/{'' if path == 'index.html' else path}"))
    body = run_sync(asset_response.bytes())
    return Response(body, status=asset_response.status, headers=asset_response.headers)


Default = wsgi.entrypoint(app)
