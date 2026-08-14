# infrastructure-terraform-gcp

GitHub App + Cloud Run agent that AI-reviews Terraform pull requests against
a GCP project, gated by deterministic policy checks, with `terraform apply`
running only after a human adds an approval label. Uses reusable modules
from [`gcp-foundation-module`](https://github.com/sinex-cloud/gcp-foundation-module).

Full architecture: [`docs/technical_design.md`](docs/technical_design.md).
GitHub App details: [`docs/github_app_design.md`](docs/github_app_design.md).
Apply pipeline detail: [`docs/apply_workflow.md`](docs/apply_workflow.md).

## Setup

Requires: `terraform` >= 1.15, `gcloud`, a GCP project with a deployment
service account already created (`sa-tf-deployer-<env>`, impersonated by
Terraform via `provider.tf` — no local key files) and a GCS backend bucket
matching `environments/<env>.tfbackend`.

```bash
terraform init -backend-config=environments/dev.tfbackend
terraform plan -var-file=environments/dev.tfvars
terraform apply -var-file=environments/dev.tfvars
```

In practice this runs through Cloud Build (`cloudbuild/review.cloudbuild.yaml`,
`cloudbuild/apply.cloudbuild.yaml`), not by hand — see below.

## Local development

The agent service (`agent-service/app/`) is a plain FastAPI app with no GCP
dependency at request-handling time other than the metadata server for
token minting:

```bash
cd agent-service
pip install -r requirements.txt
uvicorn app.main:app --reload
```

`scripts/` (policy checks, plan summary, AI review generation, PR comment
posting) run standalone with just `PyYAML` and stdlib — no service needed
to test them locally.

## GitHub App setup

The App (`sinex-infra-review-agent-dev`) is created once by hand in GitHub
settings, not by Terraform — see `docs/github_app_design.md` for the exact
permission set (`Contents: read`, `Pull requests: read & write`, `Metadata:
read`) and the single subscribed webhook event (`Pull request`). After
creation:

1. Install the App on the target repo.
2. Store its webhook secret and private key in Secret Manager
   (`infra-agent-github-webhook-secret-dev`, `infra-agent-github-app-key-dev`
   — both created as empty containers by `gcp-foundation-module/agent-hosting/secrets.tf`,
   values added by hand, never in Terraform state).
3. Point the App's webhook URL at the deployed Cloud Run service's
   `/webhook/github` path.

## Cloud Run deployment

`agent-hosting/agent.tf` provisions the Cloud Run service but deliberately
doesn't manage its container image (`lifecycle.ignore_changes` on the image
field) — Terraform sets up everything else (env vars, secret mounts, IAM),
the image itself is built and deployed separately:

```bash
cd agent-service
gcloud builds submit --tag <region>-docker.pkg.dev/<project>/infra-agent-images-dev/agent:<tag>
gcloud run deploy infra-review-agent-dev --image <region>-docker.pkg.dev/<project>/infra-agent-images-dev/agent:<tag>
```

## Cloud Build setup

Cloud Build reaches this repo through a Developer Connect connection
(`agent-hosting/cloudbuild_connection.tf`) — separate from the GitHub App
above; it only fetches source, never posts comments. The agent service
triggers builds directly via the Cloud Build API (`POST .../builds`), not
through a `BuildTrigger` resource, so the pipeline YAML is fetched from the
PR's exact commit each time rather than a fixed trigger config.

## Adding a dataset, bucket, or IAM permission

Everything in `gcp-foundation-module`'s data platform is driven by
`foundation-config/foundation.yaml` — no direct `.tf` edits needed for
routine changes:

```yaml
managed_datasets:
  my_new_dataset:
    location: europe-west1
    environments: [dev, int]
    permissions:
      - role: bigquery.dataViewer
        members:
          users: [someone@example.com]

buckets:
  my-new-bucket:
    location: europe-west1
    environments: [dev]
    permissions:
      - role: storage.objectViewer
        members:
          users: [someone@example.com]

additional_project_permissions:
  - role: bigquery.jobUser
    environments: [dev]
    members:
      users: [someone@example.com]
```

Open a PR with the change — the review pipeline plans it, runs policy
checks, and posts an AI-generated review before anyone approves the apply.

## Running tests

No CI wired up for this yet; run locally:

```bash
pip install pytest
pytest scripts/ agent-service/app/
```

## Known limitations

- `int` environment is configured (`environments/int.tfvars`) but never
  applied — dev is the only environment actually deployed.
- The apply pipeline trusts the `approved-for-apply` label without checking
  `pull_request.merged`; enforced by convention, not code.
- `terraform-apply` regenerates its own plan rather than applying the exact
  plan a human reviewed.
- `policy_checks.py` covers broad IAM, public access, and required labels
  only — naming-convention, invalid-YAML, and module-usage checks aren't
  implemented yet.

Full list, with rationale: `docs/technical_design.md`'s Known Limitations
section.

## Future improvements

- Parameterize the hardcoded dev-only values (project, region, connection
  name) across `agent-service/` for a second environment.
- Diff the apply-time plan against the review-time plan instead of
  regenerating it.
- Finish the remaining policy checks.
- Dataform analytics layer on top of the provisioned BigQuery datasets.
- GitHub Check Runs instead of PR-comment-only review status.
