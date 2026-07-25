locals {
  # secret_id suffix -> human-readable purpose, used only in the description
  platform_secrets = {
    "github-app-key"        = "GitHub App private key (PEM) used to sign JWTs for GitHub API auth"
    "github-webhook-secret" = "Shared secret used to verify GitHub webhook payload signatures"
    "model-api-key"         = "LLM provider API key for the AI review layer"
  }
}

resource "google_secret_manager_secret" "platform" {
  for_each = local.platform_secrets

  project   = var.project
  secret_id = "infra-agent-${each.key}-${var.env}" # e.g. infra-agent-github-app-key-dev

  replication {
    auto {} # let Google pick replica regions; we don't need region-pinned replication for secrets this small
  }

  labels = {
    platform    = "data-platform"
    owner       = "data-engineering"
    application = "infra-review"
    environment = var.env
    managed_by  = "terraform"
    component   = "secret-manager"
  }

  # Intentionally no `secret_data` / no google_secret_manager_secret_version resource here.
  # Values are added by hand after apply so they never enter Terraform state or git history.
}