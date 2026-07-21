terraform {
  required_version = ">= 1.1.3"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.35"
    }
  }
}

provider "google" {
  project = local.project_id
  region  = var.region

  impersonate_service_account = "sa-tf-deployer-${var.env}@${local.project_id}.iam.gserviceaccount.com"

  user_project_override = true
  billing_project        = local.project_id
}