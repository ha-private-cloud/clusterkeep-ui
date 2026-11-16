import os
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests
from flask import Flask, make_response, redirect, render_template, request, url_for

app = Flask(__name__)

APP_TITLE = os.environ.get("APP_TITLE", "ClusterKeep")
SESSION_COOKIE_NAME = "ck_sso"

app.config["AUTH_API_INTERNAL_URL"] = os.environ.get(
    "AUTH_API_INTERNAL_URL", "http://auth-api.auth-dev-pub.svc.cluster.local"
).strip()
app.config["STORAGE_UI_URL"] = os.environ.get(
    "STORAGE_UI_URL", "https://storage-dev.clusterkeep.dev.net"
).strip()
app.config["STORAGE_API_URL"] = os.environ.get("STORAGE_API_URL", "").strip()
app.config["STORAGE_API_TOKEN"] = os.environ.get("STORAGE_API_TOKEN", "").strip()
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


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html", home_url=url_for("index")), 404


@app.after_request
def set_security_headers(response):
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    return response


def _is_http_url(value):
    return urlsplit(value).scheme in ("http", "https")


def storage_login_url():
    storage_ui_url = app.config["STORAGE_UI_URL"]
    if storage_ui_url and _is_http_url(storage_ui_url):
        return url_for("login", next=storage_ui_url)
    return url_for("login")


def _register_with_auth_api(username, password, email):
    """Registers the account with auth-api server-to-server, using this backend's bearer token."""
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
        response = _continue_to(app.config["STORAGE_UI_URL"])
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


SIGN_IN_ERRORS = {
    401: "Incorrect username or password.",
    429: "Too many failed attempts. Try again later.",
}
NEW_PASSWORD_ERRORS = {
    "too_short": "Use at least 12 characters.",
    "unchanged": "Choose a password different from your current one.",
}
UNAVAILABLE = "Sign-in is unavailable right now. Try again shortly."


def _sessions_api(path, payload):
    base = app.config["AUTH_API_INTERNAL_URL"]
    token = app.config["AUTH_API_REGISTRATION_TOKEN"]
    if not (base and token):
        return None
    try:
        return requests.post(
            f"{base.rstrip('/')}/api/v1/sessions{path}",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
    except requests.RequestException:
        return None


def _storage_vault(path, session_token, payload=None):
    base = app.config["STORAGE_API_URL"]
    token = app.config["STORAGE_API_TOKEN"]
    if not (base and token and session_token):
        return None
    try:
        return requests.post(
            f"{base.rstrip('/')}/api/v1/vault{path}",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            cookies={SESSION_COOKIE_NAME: session_token},
            timeout=15,
        )
    except requests.RequestException:
        return None


def _continue_to(target):
    return make_response(render_template("continue.html", target=target))


def _recover_page(status=200, error=None):
    return render_template("recover.html", error=error), status


def _after_sign_in(body, password):
    target = body["redirect_to"]
    vault = _storage_vault("/unlock", body["session_token"], {"password": password})
    if vault is not None and vault.status_code == 201:
        response = make_response(
            render_template("recovery_code.html", recovery_code=vault.json()["recovery_code"], target=target)
        )
        response.headers["Cache-Control"] = "no-store"
        return response
    if vault is not None and vault.status_code == 409:
        return make_response(_recover_page())
    return _continue_to(target)


def _signed_in(upstream, password):
    body = upstream.json()
    cookie = body["cookie"]
    response = _after_sign_in(body, password)
    response.set_cookie(
        cookie["name"],
        body["session_token"],
        max_age=cookie["max_age"],
        domain=cookie["domain"],
        secure=cookie["secure"],
        httponly=True,
        samesite="Lax",
        path="/",
    )
    return response


def _sign_in_page(status=200, error=None, next_url=""):
    return render_template("login.html", mode="sign_in", error=error, next=next_url), status


def _change_page(change_token, status=200, error=None):
    return render_template("login.html", mode="change", error=error, change_token=change_token), status


@app.get("/login")
def login():
    return _sign_in_page(next_url=request.args.get("next", ""))


@app.post("/login")
def login_submit():
    next_url = request.form.get("next", "")
    upstream = _sessions_api(
        "",
        {
            "username": request.form.get("username", ""),
            "password": request.form.get("password", ""),
            "next": next_url,
        },
    )
    if upstream is None:
        return _sign_in_page(503, UNAVAILABLE, next_url)
    if upstream.status_code == 201:
        return _signed_in(upstream, request.form.get("password", ""))
    if upstream.status_code == 409:
        return _change_page(upstream.json().get("change_token", ""))
    if upstream.status_code in SIGN_IN_ERRORS:
        return _sign_in_page(upstream.status_code, SIGN_IN_ERRORS[upstream.status_code], next_url)
    return _sign_in_page(503, UNAVAILABLE, next_url)


@app.post("/login/change-password")
def change_password_submit():
    change_token = request.form.get("change_token", "")
    password = request.form.get("password", "")
    if password != request.form.get("password_repeat", ""):
        return _change_page(change_token, 400, "Passwords do not match.")

    upstream = _sessions_api("/password-change", {"change_token": change_token, "password": password})
    if upstream is None:
        return _change_page(change_token, 503, UNAVAILABLE)
    if upstream.status_code == 201:
        return _signed_in(upstream, password)
    if upstream.status_code == 410:
        return _sign_in_page(410, "That request has expired. Sign in again.")
    if upstream.status_code == 400:
        detail = upstream.json().get("detail")
        return _change_page(change_token, 400, NEW_PASSWORD_ERRORS.get(detail, "Choose a different password."))
    return _change_page(change_token, 503, UNAVAILABLE)


@app.post("/login/recover")
def recover_submit():
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    if not token:
        return _sign_in_page(401, "Your session has ended. Log in again.")
    upstream = _storage_vault(
        "/recover",
        token,
        {"recovery_code": request.form.get("recovery_code", ""), "password": request.form.get("password", "")},
    )
    if upstream is None:
        return _recover_page(503, UNAVAILABLE)
    if upstream.status_code == 200:
        return _continue_to(app.config["STORAGE_UI_URL"])
    if upstream.status_code == 400:
        return _recover_page(400, "That recovery code didn't work.")
    if upstream.status_code == 401:
        return _sign_in_page(401, "Your session has ended. Log in again.")
    return _recover_page(503, UNAVAILABLE)


@app.route("/logout", methods=["GET", "POST"])
def logout():
    response = redirect("/", code=303)
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    if not token:
        return response
    _storage_vault("/lock", token)
    upstream = _sessions_api("/revoke", {"session_token": token})
    if upstream is not None and upstream.status_code == 200:
        cookie = upstream.json()["cookie"]
        response.delete_cookie(cookie["name"], domain=cookie["domain"], path="/")
    return response


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
