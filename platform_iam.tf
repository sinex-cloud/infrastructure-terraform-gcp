# --- Service accounts -------------------------------------------------

resource "google_service_account" "agent_review" {
  account_id   = "sa-agent-review-${var.env}"
  display_name = "Infra review agent (Cloud Run) - ${var.env}"
}

resource "google_service_account" "cb_plan" {
  account_id   = "sa-cb-plan-${var.env}"
  display_name = "Cloud Build PR review/plan pipeline - ${var.env}"
}

resource "google_service_account" "cb_apply" {
  account_id   = "sa-cb-apply-${var.env}"
  display_name = "Cloud Build apply pipeline - ${var.env}"
}

# --- Existing deployment SA, created manually during bootstrap --------
# Referenced by constructed resource path, not a data source: reading the SA
# via the API would run as the impersonated deployer SA itself, which was
# never granted iam.serviceAccounts.get during bootstrap.

locals {
  tf_deployer_id = "projects/${var.project}/serviceAccounts/sa-tf-deployer-${var.env}@${var.project}.iam.gserviceaccount.com"
}

# --- Logging: every custom SA needs this explicitly (no default compute SA here) ---

resource "google_project_iam_member" "agent_review_log_writer" {
  project = var.project
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.agent_review.email}"
}

resource "google_project_iam_member" "cb_plan_log_writer" {
  project = var.project
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.cb_plan.email}"
}

resource "google_project_iam_member" "cb_apply_log_writer" {
  project = var.project
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.cb_apply.email}"
}

# --- Plan pipeline needs to write review artifacts (bucket-scoped, not project-wide) ---

resource "google_storage_bucket_iam_member" "cb_plan_writes_artifacts" {
  bucket = google_storage_bucket.review_artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.cb_plan.email}"
}

# --- Agent needs to read its two secrets (secret-scoped, not project-wide) ---

resource "google_secret_manager_secret_iam_member" "agent_reads_github_app_key" {
  secret_id = google_secret_manager_secret.platform["github-app-key"].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_review.email}"
}

resource "google_secret_manager_secret_iam_member" "agent_reads_webhook_secret" {
  secret_id = google_secret_manager_secret.platform["github-webhook-secret"].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_review.email}"
}

# --- cb_plan / cb_apply impersonate sa-tf-deployer to run Terraform, same as done manually ---

resource "google_service_account_iam_member" "cb_plan_impersonates_deployer" {
  service_account_id = local.tf_deployer_id
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.cb_plan.email}"
}

resource "google_service_account_iam_member" "cb_apply_impersonates_deployer" {
  service_account_id = local.tf_deployer_id
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.cb_apply.email}"
}