provider "google" {
  project = var.project
  region  = var.region

  impersonate_service_account = "sa-tf-deployer-${var.env}@${var.project}.iam.gserviceaccount.com"

  user_project_override = true
  billing_project       = var.project
}
