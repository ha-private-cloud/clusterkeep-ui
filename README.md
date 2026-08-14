# clusterkeep-ui

A small Flask app that serves as the frontend for the clusterkeep service landing page, plus the OpenTofu config used to deploy it.

## Local development

```sh
uv sync
uv run flask --app app run --debug
```

The page title defaults to "ClusterKeep" and can be overridden with the `APP_TITLE` environment variable.

## Tests

```sh
uv run pytest
```

## Container image

Built and pushed to the in-cluster Nexus docker-hosted repo (see
`../cluster-config`'s `nexus.tf`):

```sh
docker build -t registry.talos.lab/clusterkeep-ui:<tag> .
docker push registry.talos.lab/clusterkeep-ui:<tag>
```

## Helm chart

Lives at [`../charts/clusterkeep-ui`](../charts/clusterkeep-ui) ,
deliberately **outside** this (or any) git repo, so it's local-machine-only
and never pushed to GitHub. A standard chart (Chart.yaml, values.yaml,
templates/), installable on its own with
`helm install clusterkeep-ui ../charts/clusterkeep-ui`.

## Deploying

`tofu/clusterkeep-ui.tf` does the initial install and owns structural
changes (chart version, ingress config) via a `helm_release` pointed at
`../charts/clusterkeep-ui`. The namespace itself is **not** created here ,
it's a cluster-wide primitive owned by `../cluster-config` (see its
`clusterkeep-ui-namespaces.tf`); this repo's Tofu only looks it up by name
and will fail with a clear "not found" error if it doesn't exist yet, so
apply `cluster-config` first when standing up a new environment. Its Nexus
pull-credentials Secret, if the registry needs auth, is created there too.

Image tags are picked up automatically: every `tofu apply` queries Nexus's
Docker Registry API (see `scripts/latest_image_tag.py`, an `external` data
source , testable standalone without touching tofu at all) for the newest
tag on this environment's channel and deploys that, no manual `image_tag`
edit or separate CLI step needed. Which channel an environment tracks is
`image_tag_prefix`:

| workspace | tfvars      | channel   | picks the newest tag that...        |
|-----------|-------------|-----------|--------------------------------------|
| `default` | (built-in)  | dev       | starts with `DEV-`                   |
| `prv`     | `prv.tfvars`| preview   | starts with `PREVIEW-`               |
| `prd`     | `prd.tfvars`| release   | is plain digits (no prefix)          |

Tags in the right shape come from `cluster-cli build`, which derives them
from the app repo's checked-out branch (`dev`/`preview`/`main` , see
`../cluster-cli/README.md`). `image_tag` is only a fallback, used if
nothing on that channel has been pushed yet.

All `.tf` files live under `tofu/`. Create `tofu/terraform.tfvars`:

```
kubeconfig_path = "../../proxmox-tofu/_out/kubeconfig"
image_tag       = ""
```

If the Nexus docker-hosted repo requires auth (anonymous pulls are the
default), set `clusterkeep_ui_registry_username`/`_password` in
`cluster-config`'s tfvars instead , this repo's Tofu reads them from there
via remote state, both to query the registry for the latest tag and (if
`image_pull_secret_name = "clusterkeep-ui-registry"` is set here) to
reference the imagePullSecret it creates.

Run tofu:

```sh
cd tofu
tofu init
tofu plan
tofu apply
```

`cluster-cli deploy --tag <tag>` still works for a one-off rollback (runs
`helm upgrade` directly, bypassing tofu), but the next `tofu apply` moves
the release back to whatever's newest on that environment's channel , to
actually pin a rollback, push nothing newer to that channel, or lower
`image_tag_prefix` to something that won't match new pushes.

## Continuous deployment

`.github/workflows/build.yml` runs on a self-hosted GitHub Actions runner
(see `../proxmox-tofu`'s "CI bastion") on every push to `dev`, `preview`,
or `main`: builds+pushes via `cluster-ci`, then runs this repo's own Tofu
against the matching workspace to deploy , the auto tag-selection above is
what makes that deploy step pick up the image the same push just built.
