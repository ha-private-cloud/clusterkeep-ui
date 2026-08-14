# Namespace itself is owned by cluster-config (see its
# clusterkeep-ui-namespaces.tf) , a namespace is a cluster-wide primitive,
# not something this app repo should be creating/destroying. This just
# looks it up so the secret and helm_release below can depend on it
# existing.
data "kubernetes_namespace" "clusterkeep_ui" {
  metadata {
    name = var.namespace
  }
}

# clusterkeep-ui-registry_* creds live in cluster-config's tfvars (see its
# clusterkeep-ui-namespaces.tf) , read here rather than duplicated, same
# pattern headlamp.tf/nfs-storage-secret.tf already use for cross-repo
# state.
data "terraform_remote_state" "cluster_config" {
  backend = "local"

  config = {
    path = "${path.module}/../../cluster-config/tofu/terraform.tfstate"
  }
}

locals {
  registry_host = split("/", var.image_repository)[0]
  registry_repo = join("/", slice(split("/", var.image_repository), 1, length(split("/", var.image_repository))))
}

# Resolves the newest pushed tag for this environment's channel (see
# scripts/latest_image_tag.py , testable standalone, no tofu involved).
# `cluster-cli build` prefixes tags by branch (DEV-/PREVIEW-/none), and
# image_tag_prefix picks which channel this environment tracks, so every
# `tofu apply` deploys whatever's newest on that channel without hand-
# editing image_tag first. Falls back to var.image_tag if nothing on that
# channel has been pushed yet (e.g. a brand-new environment).
data "external" "clusterkeep_ui_latest_tag" {
  program = ["python3", "${path.module}/scripts/latest_image_tag.py"]

  query = {
    registry_host = local.registry_host
    repo          = local.registry_repo
    prefix        = var.image_tag_prefix
    username      = data.terraform_remote_state.cluster_config.outputs.clusterkeep_ui_registry_username
    password      = data.terraform_remote_state.cluster_config.outputs.clusterkeep_ui_registry_password
  }
}

locals {
  deployed_image_tag = (
    data.external.clusterkeep_ui_latest_tag.result.tag != ""
    ? data.external.clusterkeep_ui_latest_tag.result.tag
    : var.image_tag
  )
}

# Chart lives at ~/project/charts/clusterkeep-ui , outside every git repo,
# not just this one , so it's local filesystem only, never pushed to
# GitHub. Every `tofu apply` deploys local.deployed_image_tag (the newest
# pushed tag on this environment's channel, see the external data source
# above); `cluster-cli deploy` still works for one-off rollbacks via a
# direct `helm upgrade`, but the next `tofu apply` moves it back to
# whatever's newest on the registry.
resource "helm_release" "clusterkeep_ui" {
  name      = "clusterkeep-ui"
  chart     = "${path.module}/../../charts/clusterkeep-ui"
  namespace = data.kubernetes_namespace.clusterkeep_ui.metadata[0].name

  values = [
    yamlencode({
      image = {
        repository = var.image_repository
        tag        = local.deployed_image_tag
      }
      ingress = {
        enabled = var.ingress_enabled
        host    = var.ingress_hostname
      }
      imagePullSecrets = var.image_pull_secret_name != "" ? [
        { name = var.image_pull_secret_name }
      ] : []
    })
  ]
}
