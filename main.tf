module "data_platform" {
  # Local path during development. Once gcp-foundation-module is pushed to GitHub
  # and tagged, swap this for the pinned remote ref:
  # source = "git::https://github.com/<your-username>/gcp-foundation-module.git?ref=v0.1.0"
  source = "../gcp-foundation-module"

  path_to_yaml_resources_file = "${path.module}/foundation-config/foundation.yaml"
  env                          = var.env
  project                      = var.project
}