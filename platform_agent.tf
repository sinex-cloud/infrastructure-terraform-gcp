resource "google_cloud_run_v2_service" "agent" {
  name     = "infra-review-agent-${var.env}" # e.g. infra-review-agent-dev
  location = var.region
  project  = var.project

  template {
    service_account = google_service_account.agent_review.email # runtime identity from File 4

    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"
      # ^ placeholder image so we can verify the pipeline end-to-end.
      # Swap for <region>-docker.pkg.dev/<project>/infra-agent-images-<env>/agent:<tag>
      # (the repo from platform_registry.tf) once the real agent image is built and pushed.
    }
  }

  labels = {
    platform    = "data-platform"
    owner       = "data-engineering"
    application = "infra-review"
    environment = var.env
    managed_by  = "terraform"
    component   = "review-agent"
  }

  lifecycle {
    precondition {
      condition     = var.env == "dev"
      error_message = "Platform infrastructure (Cloud Run agent, Artifact Registry, Secret Manager, service accounts) is dev-only by design — the review-agent platform itself is explicitly not deployed to int. A failing plan here blocks the whole apply, including the other platform_*.tf resources."
    }
  }
}

# GitHub webhooks can't carry a GCP identity token, so the service must accept
# unauthenticated calls. Signature verification (webhook secret, in app code)
# is the real auth boundary, not this IAM binding.
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  project  = google_cloud_run_v2_service.agent.project
  location = google_cloud_run_v2_service.agent.location
  name     = google_cloud_run_v2_service.agent.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}