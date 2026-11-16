import re
from pathlib import Path

import pytest
import requests
import responses as responses_lib

from app import app

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = REPO_ROOT / "templates"
STATIC = REPO_ROOT / "static"

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c

def test_index_renders_title(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"ClusterKeep" in resp.data

def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}

def test_index_renders_banner(client):
    """From base.html, so every page inherits it."""
    body = client.get("/").get_data(as_text=True)
    assert "<header" in body
    assert 'class="brand-mark"' in body
    assert "GitHub" in body

def test_index_links_favicon(client):
    body = client.get("/").get_data(as_text=True)
    assert 'type="image/svg+xml"' in body
    assert "images/favicon.svg" in body

def test_favicon_is_served(client):
    resp = client.get("/static/images/favicon.svg")
    assert resp.status_code == 200
    assert "svg" in resp.headers["Content-Type"]

def test_security_headers_on_every_response(client):
    """after_request, so static files carry them too."""
    for path in ["/", "/healthz", "/static/css/style.css"]:
        headers = client.get(path).headers
        assert headers["X-Content-Type-Options"] == "nosniff", path
        assert headers["X-Frame-Options"] == "DENY", path
        assert headers["Referrer-Policy"] == "no-referrer", path
        assert "Content-Security-Policy" in headers, path

def test_content_security_policy_stays_strict(client):
    """Relaxing any of these is a real change in exposure -- do it knowingly."""
    csp = client.get("/").headers["Content-Security-Policy"]
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "default-src 'self'" in csp

def test_no_inline_scripts_or_handlers():
    """CSP blocks these at runtime; catch them at author time instead."""
    for template in TEMPLATES.rglob("*.html"):
        markup = template.read_text()
        assert not re.search(r"<script(?![^>]*\bsrc=)", markup), (
            f"{template.name} has an inline <script>; CSP blocks it -- put the "
            "code in static/js/ and load it with src="
        )
        assert not re.search(r"\son[a-z]+\s*=\s*[\"']", markup), (
            f"{template.name} has an inline event handler; CSP blocks it"
        )

def test_logo_and_favicon_geometry_match():
    """Nothing else would catch the two copies of the mark drifting apart."""
    inline = (TEMPLATES / "partials" / "logo.html").read_text()
    favicon = (STATIC / "images" / "favicon.svg").read_text()
    assert re.findall(r'd="([^"]+)"', inline) == re.findall(r'd="([^"]+)"', favicon)

def test_mark_is_built_on_the_cell_grid():
    """Integer coordinates are what make the mark exact at 16px."""
    inline = (TEMPLATES / "partials" / "logo.html").read_text()
    assert 'viewBox="0 0 16 16"' in inline
    assert 'shape-rendering="crispEdges"' in inline
    (data,) = re.findall(r'd="([^"]+)"', inline)
    for number in re.findall(r"-?\d+(?:\.\d+)?", data):
        assert "." not in number, f"non-integer coordinate {number!r} in the mark"

def test_mark_path_is_not_duplicated_into_pages():
    """A third copy would escape the drift guard, which only checks two."""
    for template in TEMPLATES.rglob("*.html"):
        if template.name == "logo.html":
            continue
        assert 'fill-rule="evenodd"' not in template.read_text(), (
            f"{template.name} appears to inline the mark; include the partial instead"
        )

FETCHING_TAGS = r"link|script|img|iframe|source|video|audio|embed|object|track"

def test_templates_request_no_third_party_assets():
    tags = re.compile(rf"<(?:{FETCHING_TAGS})\b[^>]*>", re.I | re.S)
    urls = re.compile(r'(?:href|src)\s*=\s*"(https?://[^"]+)"', re.I)
    for template in TEMPLATES.rglob("*.html"):
        for tag in tags.findall(template.read_text()):
            for url in urls.findall(tag):
                assert False, f"{template.name} loads a remote asset: {url}"

def test_fonts_are_self_hosted():
    """@font-face sources must be local and must actually exist."""
    css = (STATIC / "css" / "style.css").read_text()
    sources = re.findall(r'src:\s*url\("([^"]+)"\)', css)
    assert sources, "no @font-face rules found in the built stylesheet"
    for src in sources:
        assert not src.startswith("http"), f"remote font source: {src}"
        resolved = (STATIC / "css" / src).resolve()
        assert resolved.is_file(), f"missing font file: {resolved}"

def test_stylesheet_is_built_from_current_source():
    """Marker classes the templates rely on must be in the build."""
    css = (STATIC / "css" / "style.css").read_text()
    for marker in [".mark-lg .brand-mark", "Cinzel", "Inter"]:
        assert marker in css, f"{marker!r} missing -- run `npm run build:css`"

LOCAL_CLASSES = {"brand-mark", "mark-lg", "group", "antialiased"}

def tailwind_selector(cls):
    """Escapes a class name the way Tailwind writes its selector, variant prefix included."""
    return "." + re.sub(r"([^A-Za-z0-9_-])", r"\\\1", cls)

def tailwind_classes_used():
    """Every class referenced by a template, minus our own non-generated ones."""
    used = set()
    for template in TEMPLATES.rglob("*.html"):
        for value in re.findall(r'class="([^"]*)"', template.read_text()):
            used.update(c for c in value.split() if c not in LOCAL_CLASSES)
    return used

def test_every_utility_used_by_a_template_is_in_the_build():
    """style.css is committed and not rebuilt in CI, so it can ship stale after a template edit."""
    css = (STATIC / "css" / "style.css").read_text()
    missing = sorted(
        cls for cls in tailwind_classes_used() if tailwind_selector(cls) not in css
    )
    assert not missing, (
        f"utilities used in templates but absent from style.css: {missing}\n"
        "run `npm run build:css` and commit the result"
    )

def test_header_links_to_log_in(client):
    body = client.get("/").get_data(as_text=True)
    assert 'href="/login"' in body


def test_log_in_page_links_to_join(client):
    body = client.get("/login").get_data(as_text=True)
    assert 'href="/join"' in body

def test_join_page_renders_invite_and_account_form_and_login_link(client):
    body = client.get("/join").get_data(as_text=True)
    assert 'name="invite_code"' in body
    assert 'name="username"' in body
    assert 'name="email"' in body
    assert 'name="password"' in body
    assert 'href="/login?next=https://storage-dev.clusterkeep.dev.net"' in body

def assert_continues_to(response, target):
    """Cross-site redirects after a form POST are blocked by form-action 'self', so sign-in continues via meta refresh."""
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Location" not in response.headers
    assert f'<meta http-equiv="refresh" content="0; url={target}"' in body
    assert f'href="{target}"' in body


def test_form_action_stays_self_only(client):
    csp = client.get("/login").headers["Content-Security-Policy"]
    assert "form-action 'self'" in csp


JOIN_FORM = {
    "invite_code": "c1u513r01K3Ep",
    "username": "newuser",
    "email": "newuser@example.com",
    "password": "a-long-enough-password",
    "password_confirm": "a-long-enough-password",
}

def test_correct_invite_code_registers_via_auth_api_and_relays_the_session_cookie(client, monkeypatch):
    monkeypatch.setitem(app.config, "INVITE_CODE", "c1u513r01K3Ep")
    monkeypatch.setitem(app.config, "AUTH_API_REGISTRATION_TOKEN", "test-registration-token")
    with responses_lib.RequestsMock() as rsps:
        rsps.add(
            responses_lib.POST,
            "http://auth-api.clusterkeep-dev-priv.svc.cluster.local/api/v1/register",
            status=201,
            headers={"Set-Cookie": "ck_sso=opaque-token; Domain=.clusterkeep.dev.net; HttpOnly"},
        )
        response = client.post("/join", data=JOIN_FORM, follow_redirects=False)
    assert_continues_to(response, "https://storage-dev.clusterkeep.dev.net")
    assert "ck_sso" in response.headers.get("Set-Cookie", "")

def test_wrong_invite_code_is_rejected_without_calling_auth_api(client, monkeypatch):
    monkeypatch.setitem(app.config, "INVITE_CODE", "c1u513r01K3Ep")
    with responses_lib.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        response = client.post("/join", data={**JOIN_FORM, "invite_code": "wrong-code"})
        assert len(rsps.calls) == 0
    assert response.status_code == 200
    assert "is not valid" in response.get_data(as_text=True)

def test_invite_code_check_fails_closed_when_unconfigured(client, monkeypatch):
    monkeypatch.setitem(app.config, "INVITE_CODE", "")
    response = client.post("/join", data={**JOIN_FORM, "invite_code": ""})
    assert response.status_code == 200
    assert "is not valid" in response.get_data(as_text=True)

def test_mismatched_passwords_are_rejected(client, monkeypatch):
    monkeypatch.setitem(app.config, "INVITE_CODE", "c1u513r01K3Ep")
    response = client.post("/join", data={**JOIN_FORM, "password_confirm": "something-else"})
    assert response.status_code == 200
    assert "do not match" in response.get_data(as_text=True)

def test_missing_email_is_rejected_without_calling_auth_api(client, monkeypatch):
    monkeypatch.setitem(app.config, "INVITE_CODE", "c1u513r01K3Ep")
    with responses_lib.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        response = client.post("/join", data={**JOIN_FORM, "email": ""})
        assert len(rsps.calls) == 0
    assert response.status_code == 200
    assert "email address is required" in response.get_data(as_text=True)

def test_taken_username_shows_auth_apis_error(client, monkeypatch):
    monkeypatch.setitem(app.config, "INVITE_CODE", "c1u513r01K3Ep")
    monkeypatch.setitem(app.config, "AUTH_API_REGISTRATION_TOKEN", "test-registration-token")
    with responses_lib.RequestsMock() as rsps:
        rsps.add(
            responses_lib.POST,
            "http://auth-api.clusterkeep-dev-priv.svc.cluster.local/api/v1/register",
            status=409,
        )
        response = client.post("/join", data=JOIN_FORM)
    assert response.status_code == 200
    assert "already taken" in response.get_data(as_text=True)

def test_invalid_password_shows_auth_apis_specific_error(client, monkeypatch):
    monkeypatch.setitem(app.config, "INVITE_CODE", "c1u513r01K3Ep")
    monkeypatch.setitem(app.config, "AUTH_API_REGISTRATION_TOKEN", "test-registration-token")
    with responses_lib.RequestsMock() as rsps:
        rsps.add(
            responses_lib.POST,
            "http://auth-api.clusterkeep-dev-priv.svc.cluster.local/api/v1/register",
            json={"detail": [{"msg": "String should have at least 12 characters"}]},
            status=422,
        )
        response = client.post("/join", data=JOIN_FORM)
    assert response.status_code == 200
    assert "String should have at least 12 characters" in response.get_data(as_text=True)

def test_game_page_has_been_removed(client):
    assert client.get("/game").status_code == 404


def test_score_endpoint_has_been_removed(client):
    assert client.post("/game/score", json={"initials": "abc", "score": 1}).status_code in (404, 405)


def test_index_no_longer_links_to_the_game(client):
    assert "Play Game" not in client.get("/").get_data(as_text=True)


def test_unknown_path_shows_the_not_found_page(client):
    resp = client.get("/does-not-exist")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 404
    assert "Page not found" in body
    assert "Back to ClusterKeep" in body
    assert 'href="/"' in body


SESSIONS_URL = "http://auth-api.clusterkeep-dev-priv.svc.cluster.local/api/v1/sessions"
COOKIE = {"name": "ck_sso", "domain": ".clusterkeep.dev.net", "max_age": 604800, "secure": True}
SIGN_IN_FORM = {"username": "alice", "password": "a-long-enough-password", "next": "https://storage-dev.clusterkeep.dev.net"}


@pytest.fixture
def frontend_token(monkeypatch):
    monkeypatch.setitem(app.config, "AUTH_API_REGISTRATION_TOKEN", "test-registration-token")


def test_sign_in_page_renders_the_form_with_next(client):
    body = client.get("/login?next=https://storage-dev.clusterkeep.dev.net").get_data(as_text=True)
    assert 'action="/login"' in body
    assert 'name="username"' in body
    assert 'name="password"' in body
    assert 'name="next" value="https://storage-dev.clusterkeep.dev.net"' in body


def test_successful_sign_in_sets_the_session_cookie_and_redirects(client, frontend_token):
    with responses_lib.RequestsMock() as rsps:
        rsps.add(
            responses_lib.POST,
            SESSIONS_URL,
            status=201,
            json={"session_token": "opaque-token", "redirect_to": "https://storage-dev.clusterkeep.dev.net", "cookie": COOKIE},
            match=[
                responses_lib.matchers.header_matcher({"Authorization": "Bearer test-registration-token"}),
                responses_lib.matchers.json_params_matcher(SIGN_IN_FORM),
            ],
        )
        response = client.post("/login", data=SIGN_IN_FORM, follow_redirects=False)
    assert_continues_to(response, "https://storage-dev.clusterkeep.dev.net")
    cookie = response.headers["Set-Cookie"]
    for part in ("ck_sso=opaque-token", "Domain=clusterkeep.dev.net", "Max-Age=604800", "Secure", "HttpOnly", "SameSite=Lax", "Path=/"):
        assert part in cookie


@pytest.mark.parametrize(
    ("status", "message"),
    [(401, "Incorrect username or password."), (429, "Too many failed attempts. Try again later.")],
)
def test_rejected_sign_in_shows_a_fixed_message(client, frontend_token, status, message):
    with responses_lib.RequestsMock() as rsps:
        rsps.add(responses_lib.POST, SESSIONS_URL, status=status, json={"detail": "<script>x</script>"})
        response = client.post("/login", data=SIGN_IN_FORM)
    body = response.get_data(as_text=True)
    assert response.status_code == status
    assert message in body
    assert "<script>x" not in body
    assert "Set-Cookie" not in response.headers


def test_sign_in_fails_closed_when_auth_api_is_unreachable(client, frontend_token):
    with responses_lib.RequestsMock() as rsps:
        rsps.add(responses_lib.POST, SESSIONS_URL, body=requests.exceptions.ConnectionError("down"))
        response = client.post("/login", data=SIGN_IN_FORM)
    assert response.status_code == 503
    assert "Set-Cookie" not in response.headers


def test_flagged_account_is_shown_the_change_password_form(client, frontend_token):
    with responses_lib.RequestsMock() as rsps:
        rsps.add(responses_lib.POST, SESSIONS_URL, status=409, json={"detail": "password_change_required", "change_token": "change-123"})
        response = client.post("/login", data=SIGN_IN_FORM)
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'action="/login/change-password"' in body
    assert 'name="change_token" value="change-123"' in body
    assert "Set-Cookie" not in response.headers


CHANGE_FORM = {"change_token": "change-123", "password": "a-brand-new-passphrase", "password_repeat": "a-brand-new-passphrase"}


def test_changing_the_password_signs_in(client, frontend_token):
    with responses_lib.RequestsMock() as rsps:
        rsps.add(
            responses_lib.POST,
            f"{SESSIONS_URL}/password-change",
            status=201,
            json={"session_token": "fresh-token", "redirect_to": "https://storage-dev.clusterkeep.dev.net", "cookie": COOKIE},
            match=[responses_lib.matchers.json_params_matcher({"change_token": "change-123", "password": "a-brand-new-passphrase"})],
        )
        response = client.post("/login/change-password", data=CHANGE_FORM, follow_redirects=False)
    assert_continues_to(response, "https://storage-dev.clusterkeep.dev.net")
    assert "ck_sso=fresh-token" in response.headers["Set-Cookie"]


def test_mismatched_new_passwords_never_reach_auth_api(client, frontend_token):
    with responses_lib.RequestsMock():
        response = client.post("/login/change-password", data={**CHANGE_FORM, "password_repeat": "something-else-entirely"})
    assert response.status_code == 400
    assert "Passwords do not match." in response.get_data(as_text=True)


@pytest.mark.parametrize(
    ("detail", "message"),
    [("too_short", "Use at least 12 characters."), ("unchanged", "Choose a password different from your current one.")],
)
def test_refused_new_password_keeps_the_change_form(client, frontend_token, detail, message):
    with responses_lib.RequestsMock() as rsps:
        rsps.add(responses_lib.POST, f"{SESSIONS_URL}/password-change", status=400, json={"detail": detail})
        response = client.post("/login/change-password", data=CHANGE_FORM)
    body = response.get_data(as_text=True)
    assert response.status_code == 400
    assert message in body
    assert 'name="change_token" value="change-123"' in body


def test_expired_change_request_returns_to_sign_in(client, frontend_token):
    with responses_lib.RequestsMock() as rsps:
        rsps.add(responses_lib.POST, f"{SESSIONS_URL}/password-change", status=410, json={"detail": "expired"})
        response = client.post("/login/change-password", data=CHANGE_FORM)
    body = response.get_data(as_text=True)
    assert response.status_code == 410
    assert "That request has expired. Sign in again." in body
    assert 'action="/login"' in body


def test_sign_out_revokes_the_session_and_clears_the_cookie(client, frontend_token):
    client.set_cookie("ck_sso", "opaque-token")
    with responses_lib.RequestsMock() as rsps:
        rsps.add(
            responses_lib.POST,
            f"{SESSIONS_URL}/revoke",
            status=200,
            json={"cookie": COOKIE},
            match=[responses_lib.matchers.json_params_matcher({"session_token": "opaque-token"})],
        )
        response = client.get("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["Location"] == "/"
    cookie = response.headers["Set-Cookie"]
    assert cookie.startswith("ck_sso=;")
    assert "Domain=clusterkeep.dev.net" in cookie


def test_sign_out_without_a_session_just_goes_home(client, frontend_token):
    with responses_lib.RequestsMock():
        response = client.get("/logout", follow_redirects=False)
    assert response.headers["Location"] == "/"
