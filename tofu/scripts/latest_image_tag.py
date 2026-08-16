#!/usr/bin/env python3
"""Resolves the newest pushed image tag matching a prefix from a Docker
Registry v2 API (Nexus's docker-hosted repo here), doing the bearer-token
challenge/response dance `docker pull` does under the hood , plain Basic
auth doesn't work directly against `/v2/.../tags/list` once Nexus's Docker
Bearer Token Realm is enabled.

Used as a Terraform `external` data source: reads a JSON query object on
stdin, writes a JSON object of strings on stdout. Runnable standalone for
testing without touching tofu at all, e.g.:

  echo '{"registry_host":"registry.clusterkeep.dev.net","repo":"clusterkeep-ui","prefix":"DEV-","username":"","password":""}' \\
    | python3 latest_image_tag.py
"""
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from base64 import b64encode

CHALLENGE_RE = re.compile(r'Bearer realm="([^"]+)",service="([^"]+)"')

# Every *.clusterkeep.dev.net host sits behind ingress-nginx's self-signed default
# cert (see cluster-config/README.md) , same "accept self-signed on the
# LAN" reasoning cluster-cli's client.py and Kaniko's --skip-tls-verify use.
_UNVERIFIED_SSL_CONTEXT = ssl._create_unverified_context()


def http_get(url: str, headers: dict) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15, context=_UNVERIFIED_SSL_CONTEXT) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def bearer_token(challenge: str, repo: str, username: str, password: str) -> str:
    match = CHALLENGE_RE.match(challenge)
    if not match:
        raise ValueError(f"unrecognized registry auth challenge: {challenge!r}")
    realm, service = match.groups()

    headers = {}
    if username:
        basic = b64encode(f"{username}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {basic}"

    status, _, body = http_get(f"{realm}?service={service}&scope=repository:{repo}:pull", headers)
    if status != 200:
        raise ValueError(f"token request to {realm} failed ({status}): {body.decode(errors='replace')}")
    return json.loads(body)["token"]


def main() -> None:
    query = json.load(sys.stdin)
    host = query["registry_host"]
    repo = query["repo"]
    prefix = query.get("prefix", "")
    username = query.get("username", "")
    password = query.get("password", "")

    tags_url = f"https://{host}/v2/{repo}/tags/list"
    status, headers, body = http_get(tags_url, {"Accept": "application/json"})

    if status == 401:
        challenge = headers.get("Www-Authenticate") or headers.get("WWW-Authenticate", "")
        token = bearer_token(challenge, repo, username, password)
        status, headers, body = http_get(
            tags_url, {"Accept": "application/json", "Authorization": f"Bearer {token}"}
        )

    if status != 200:
        raise SystemExit(f"tags/list on {tags_url} failed ({status}): {body.decode(errors='replace')}")

    tags = json.loads(body).get("tags") or []
    if prefix:
        candidates = [t for t in tags if t.startswith(prefix)]
    else:
        candidates = [t for t in tags if t.isdigit()]

    print(json.dumps({"tag": max(candidates) if candidates else ""}))


if __name__ == "__main__":
    main()
