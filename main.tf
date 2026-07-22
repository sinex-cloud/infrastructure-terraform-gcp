module "data_platform" {
  source = "git::https://github.com/sinex-cloud/gcp-foundation-module.git?ref=v0.1.3"

  path_to_yaml_resources_file = "${path.module}/foundation-config/foundation.yaml"
  env                          = var.env
  project                      = var.project
}

