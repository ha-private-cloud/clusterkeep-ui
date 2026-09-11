import re
from pathlib import Path

import pytest
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
    """Variants keep their prefix (`hover:bg-x` -> `.hover\\:bg-x:hover`), so do
    not strip it. Everything outside [A-Za-z0-9_-] is backslash-escaped."""
    return "." + re.sub(r"([^A-Za-z0-9_-])", r"\\\1", cls)

def tailwind_classes_used():
    """Every class referenced by a template, minus our own non-generated ones."""
    used = set()
    for template in TEMPLATES.rglob("*.html"):
        for value in re.findall(r'class="([^"]*)"', template.read_text()):
            used.update(c for c in value.split() if c not in LOCAL_CLASSES)
    return used

def test_every_utility_used_by_a_template_is_in_the_build():
    """style.css is committed and nothing rebuilds it in CI, so it can ship
    stale after a template edit. The page still renders -- just wrong."""
    css = (STATIC / "css" / "style.css").read_text()
    missing = sorted(
        cls for cls in tailwind_classes_used() if tailwind_selector(cls) not in css
    )
    assert not missing, (
        f"utilities used in templates but absent from style.css: {missing}\n"
        "run `npm run build:css` and commit the result"
    )

DEV_HEADLAMP_LOGIN_URL = (
    "https://auth-dev.clusterkeep.dev.net/login"
    "?next=https%3A%2F%2Fheadlamp.clusterkeep.dev.net"
)

def headlamp_login_href(body):
    hrefs = re.findall(r'<a\s+href="([^"]*)"\s+data-headlamp-login\b', body)
    return hrefs[0] if hrefs else None

def test_headlamp_button_renders_with_dev_defaults(client):
    body = client.get("/").get_data(as_text=True)
    assert "Log in to Headlamp" in body
    assert headlamp_login_href(body) == DEV_HEADLAMP_LOGIN_URL

def test_headlamp_button_encodes_the_next_parameter(client, monkeypatch):
    """auth-api reads `next` as one value; an unencoded URL would split it."""
    monkeypatch.setitem(app.config, "AUTH_API_BASE_URL", "https://auth.example.net/")
    monkeypatch.setitem(app.config, "HEADLAMP_URL", "https://lamp.example.net/c?a=1&b=2")
    href = headlamp_login_href(client.get("/").get_data(as_text=True))
    assert href == (
        "https://auth.example.net/login"
        "?next=https%3A%2F%2Flamp.example.net%2Fc%3Fa%3D1%26b%3D2"
    )

@pytest.mark.parametrize(
    ("auth_api_base_url", "headlamp_url"),
    [
        ("", "https://headlamp.clusterkeep.dev.net"),
        ("https://auth-dev.clusterkeep.dev.net", ""),
        ("", ""),
        ("javascript:alert(1)", "https://headlamp.clusterkeep.dev.net"),
        ("https://auth-dev.clusterkeep.dev.net", "javascript:alert(1)"),
    ],
)
def test_headlamp_button_absent_when_not_configured(
    client, monkeypatch, auth_api_base_url, headlamp_url
):
    monkeypatch.setitem(app.config, "AUTH_API_BASE_URL", auth_api_base_url)
    monkeypatch.setitem(app.config, "HEADLAMP_URL", headlamp_url)
    body = client.get("/").get_data(as_text=True)
    assert "Log in to Headlamp" not in body
    assert headlamp_login_href(body) is None

def test_header_links_to_join(client):
    body = client.get("/").get_data(as_text=True)
    assert 'href="/join"' in body

def test_join_page_renders_invite_and_account_form_and_login_link(client):
    body = client.get("/join").get_data(as_text=True)
    assert 'name="invite_code"' in body
    assert 'name="username"' in body
    assert 'name="email"' in body
    assert 'name="password"' in body
    assert (
        "https://auth-dev.clusterkeep.dev.net/login"
        "?next=https%3A%2F%2Fstorage-dev.clusterkeep.dev.net"
    ) in body

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
    assert response.status_code == 302
    assert response.headers["Location"] == "https://storage-dev.clusterkeep.dev.net"
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
