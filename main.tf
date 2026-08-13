module "data_platform" {
  source = "git::https://github.com/sinex-cloud/gcp-foundation-module.git?ref=v0.2.0"

  path_to_yaml_resources_file = "${path.module}/foundation-config/foundation.yaml"
  env                         = var.env
  project                     = var.project
}

module "agent_hosting" {
  source = "git::https://github.com/sinex-cloud/gcp-foundation-module.git//agent-hosting?ref=v0.3.6"

  env     = var.env
  project = var.project
  region  = var.region
}

# test: verify review pipeline end-to-end