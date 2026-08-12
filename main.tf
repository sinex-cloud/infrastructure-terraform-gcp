module "data_platform" {
  source = "git::https://github.com/sinex-cloud/gcp-foundation-module.git?ref=v0.2.0"

  path_to_yaml_resources_file = "${path.module}/foundation-config/foundation.yaml"
  env                         = var.env
  project                     = var.project
}

module "agent_hosting" {
  # TODO: v0.3.0 doesn't exist yet — tag it in gcp-foundation-module once
  # the agent-hosting/ subfolder is committed and pushed, then this resolves.
  source = "git::https://github.com/sinex-cloud/gcp-foundation-module.git//agent-hosting?ref=v0.3.0"

  env     = var.env
  project = var.project
  region  = var.region
}
