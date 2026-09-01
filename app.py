import os
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit

from flask import Flask, render_template

app = Flask(__name__)

APP_TITLE = os.environ.get("APP_TITLE", "ClusterKeep")

app.config["AUTH_API_BASE_URL"] = os.environ.get(
    "AUTH_API_BASE_URL", "https://auth-dev.clusterkeep.dev.net"
).strip()
app.config["HEADLAMP_URL"] = os.environ.get(
    "HEADLAMP_URL", "https://headlamp.clusterkeep.dev.net"
).strip()

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "font-src 'self'",
        "img-src 'self'",
        "connect-src 'self'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
    ]
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), interest-cohort=()",
}


@app.after_request
def set_security_headers(response):
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    return response


def _is_http_url(value):
    return urlsplit(value).scheme in ("http", "https")


def headlamp_login_url():
    auth_api_base_url = app.config["AUTH_API_BASE_URL"]
    headlamp_url = app.config["HEADLAMP_URL"]
    if not (auth_api_base_url and headlamp_url):
        return None
    if not (_is_http_url(auth_api_base_url) and _is_http_url(headlamp_url)):
        return None
    query = urlencode({"next": headlamp_url})
    return f"{auth_api_base_url.rstrip('/')}/login?{query}"


@app.context_processor
def inject_globals():
    return {
        "title": APP_TITLE,
        "year": datetime.now(timezone.utc).year,
        "headlamp_login_url": headlamp_login_url(),
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/game")
def game():
    return render_template("game.html")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
