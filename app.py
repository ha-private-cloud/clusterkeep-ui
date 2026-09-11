import os
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit

import requests
from flask import Flask, redirect, render_template, request

app = Flask(__name__)

APP_TITLE = os.environ.get("APP_TITLE", "ClusterKeep")

app.config["AUTH_API_BASE_URL"] = os.environ.get(
    "AUTH_API_BASE_URL", "https://auth-dev.clusterkeep.dev.net"
).strip()
# The public hostname above only resolves for browsers; this backend's own registration
# call needs the in-cluster Service DNS name (or the dev-env's docker-compose service name).
app.config["AUTH_API_INTERNAL_URL"] = os.environ.get(
    "AUTH_API_INTERNAL_URL", "http://auth-api.clusterkeep-dev-priv.svc.cluster.local"
).strip()
app.config["STORAGE_UI_URL"] = os.environ.get(
    "STORAGE_UI_URL", "https://storage-dev.clusterkeep.dev.net"
).strip()
app.config["INVITE_CODE"] = os.environ.get("INVITE_CODE", "").strip()
app.config["AUTH_API_REGISTRATION_TOKEN"] = os.environ.get("AUTH_API_REGISTRATION_TOKEN", "").strip()

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "font-src 'self'",
        "img-src 'self'",
        "connect-src 'self'",
        "base-uri 'none'",
        "form-action 'self'",
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


def storage_login_url():
    auth_api_base_url = app.config["AUTH_API_BASE_URL"]
    storage_ui_url = app.config["STORAGE_UI_URL"]
    if not (auth_api_base_url and storage_ui_url):
        return None
    if not (_is_http_url(auth_api_base_url) and _is_http_url(storage_ui_url)):
        return None
    query = urlencode({"next": storage_ui_url})
    return f"{auth_api_base_url.rstrip('/')}/login?{query}"


def _register_with_auth_api(username, password, email):
    """Server-to-server, gated by a bearer token only this backend holds -- the invite
    code alone is not enough to reach auth-api's registration endpoint."""
    auth_api_internal_url = app.config["AUTH_API_INTERNAL_URL"]
    registration_token = app.config["AUTH_API_REGISTRATION_TOKEN"]
    if not (auth_api_internal_url and registration_token):
        return None, "Account creation is not configured."

    try:
        upstream = requests.post(
            f"{auth_api_internal_url.rstrip('/')}/api/v1/register",
            json={"username": username, "password": password, "email": email},
            headers={"Authorization": f"Bearer {registration_token}"},
            timeout=5,
        )
    except requests.RequestException:
        return None, "Could not reach the account service. Try again shortly."

    if upstream.status_code == 201:
        response = redirect(app.config["STORAGE_UI_URL"])
        cookie_header = upstream.headers.get("Set-Cookie")
        if cookie_header:
            response.headers["Set-Cookie"] = cookie_header
        return response, None
    if upstream.status_code == 409:
        return None, "That username is already taken."
    if upstream.status_code == 422:
        return None, _describe_validation_error(upstream)
    return None, "Could not create that account."


def _describe_validation_error(upstream):
    try:
        detail = upstream.json()["detail"]
        messages = [item["msg"] for item in detail]
    except (ValueError, KeyError, TypeError):
        return "Check your email address and make sure the password is at least 12 characters."
    return " ".join(messages) if messages else "Check your account details and try again."


@app.context_processor
def inject_globals():
    return {
        "title": APP_TITLE,
        "year": datetime.now(timezone.utc).year,
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/game")
def game():
    return render_template("game.html")


@app.route("/join", methods=["GET", "POST"])
def join():
    error = None
    if request.method == "POST":
        submitted_code = request.form.get("invite_code", "")
        username = request.form.get("username", "")
        email = request.form.get("email", "")
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        expected = app.config["INVITE_CODE"]

        if not (expected and submitted_code == expected):
            error = "That invite code is not valid."
        elif not email:
            error = "An email address is required."
        elif password != password_confirm:
            error = "Passwords do not match."
        else:
            response, error = _register_with_auth_api(username, password, email)
            if response is not None:
                return response

    return render_template(
        "join.html",
        error=error,
        storage_login_url=storage_login_url(),
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
