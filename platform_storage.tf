resource "google_storage_bucket" "review_artifacts" {
  project       = var.project
  name          = "${var.project}-review-artifacts" # e.g. data-platform-aab-dev-review-artifacts
  location      = var.region
  force_destroy = true # same as module buckets — safe to nuke/rebuild during dev

  uniform_bucket_level_access = true       # IAM-only access, no legacy per-object ACLs
  public_access_prevention    = "enforced" # cannot be made public even by mistake

  labels = {
    platform    = "data-platform"
    owner       = "data-engineering"
    application = "infra-review"
    environment = var.env
    managed_by  = "terraform"
    component   = "review-artifacts"
  }
}