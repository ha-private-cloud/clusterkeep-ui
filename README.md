# clusterkeep-ui

The public front page of ClusterKeep. It's where people join with an invite code, log in, change their password and recover their storage, and it sends them on to their files afterwards.

## What it does

- Landing page with links to join and log in.
- Joining checks the invite code and creates the account through auth-api.
- Logging in sends the username and password to auth-api's internal sessions API, then sets the `ck_sso` session cookie that every ClusterKeep site uses.
- The first log-in after storage-api is set up unlocks the user's storage and shows their recovery code once.
- If an admin has reset someone's password, logging in asks for their recovery code so their storage can be unlocked again.
- Logging out locks storage and ends the session.
- Unknown pages show the same 404 page as the other sites.

auth-api never serves any of these pages itself. Everything the browser sees comes from here, and auth-api only answers clusterkeep-ui's backend over the cluster network.

## Endpoints

| Method | Path | What it does |
|---|---|---|
| GET | `/` | Landing page |
| GET, POST | `/join` | Create an account with an invite code |
| GET | `/login` | Login form. `next` sets where to go afterwards |
| POST | `/login` | Log in through auth-api, unlock storage and continue |
| POST | `/login/change-password` | Choose a new password when auth-api asks for one |
| POST | `/login/recover` | Unlock storage with the recovery code after a password reset |
| GET, POST | `/logout` | Lock storage, end the session and clear the cookie |
| GET | `/healthz` | Kubernetes health check |

After logging in or joining, the page shows a short "Signing you in" page that moves on by itself instead of redirecting straight to another site. The content security policy uses `form-action 'self'`, which also blocks redirects to other sites after a form is posted.

## Technologies

- Python 3.13 and Flask, served by gunicorn
- Jinja2 templates styled with Tailwind CSS, built ahead of time so nothing loads from a CDN
- Small vanilla JavaScript files, no frameworks
- requests for the server-to-server calls to auth-api and storage-api
- pytest with the responses library for the tests
- uv for dependencies, Docker for the image, Helm and OpenTofu for deployment

## Configuration

| Variable | What it's for |
|---|---|
| `AUTH_API_INTERNAL_URL` | auth-api's address inside the cluster |
| `AUTH_API_REGISTRATION_TOKEN` | Token for auth-api's registration and sessions APIs |
| `INVITE_CODE` | Code people need to join |
| `STORAGE_UI_URL` | Where people go after joining |
| `STORAGE_API_URL` | storage-api's address inside the cluster. Leave it blank to turn storage unlocking off |
| `STORAGE_API_TOKEN` | Service token for storage-api |
| `APP_TITLE` | Site title, defaults to ClusterKeep |

## Running locally

The easiest way is [common-dev-env](https://github.com/LandRegistry/common-dev-env) with the [dev-env-config](https://github.com/ha-private-cloud/dev-env-config) repository, set up as the [organisation README](https://github.com/ha-private-cloud/.github/blob/main/profile/README.md#running-it-locally) describes. That runs it on http://localhost:9080 alongside the other services. You can also run it on its own.

```sh
uv sync
npm install
npm run build:css
uv run flask --app app run --debug
```

Run the tests with `uv run pytest`. Rebuild the CSS after changing a template, because a test checks every class a template uses is in the built stylesheet.

## Deployment

The GitHub workflows come from the shared `pipelines` repo.

- Pushes to `development` and `preview` build the image in the cluster through cluster-ci and deploy it to dev and preview.
- Merges to `main` build the image without deploying it.
- Pushing a `vX.Y.Z` tag builds the release image, and running the release workflow with that tag deploys it to production.

`preview` and `main` only take changes through pull requests. The Helm chart is in `charts/clusterkeep-ui` and the OpenTofu config is in `tofu/`, with one workspace per environment. Production is public through the Cloudflare Tunnel.
