data "kubernetes_namespace" "clusterkeep_ui" {
  metadata {
    name = var.namespace
  }
}


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
    var.image_tag_prefix != "" && data.external.clusterkeep_ui_latest_tag.result.tag != ""
    ? data.external.clusterkeep_ui_latest_tag.result.tag
    : var.image_tag
  )
}

resource "helm_release" "clusterkeep_ui" {
  name      = "clusterkeep-ui"
  chart     = "${path.module}/../../charts/clusterkeep-ui"
  namespace = data.kubernetes_namespace.clusterkeep_ui.metadata[0].name

  atomic = true

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
