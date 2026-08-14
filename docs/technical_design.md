# Technical Design

## Objective

Automate review and apply of Terraform changes to GCP infrastructure: every
pull request gets an AI-generated review comment backed by deterministic
policy checks, and merged changes only reach GCP after a human adds an
approval label. Deterministic checks decide pass/fail; the AI explains;
a human approves the apply.

## Architecture

```
GitHub PR event (opened/labeled)
        │  webhook (HMAC-signed)
        ▼
Cloud Run: infra-review-agent-dev  (agent-service/)
        │  verifies signature, filters event, triggers a build inline
        ▼
Cloud Build (europe-west1, source = Developer Connect connection)
  ├── review.cloudbuild.yaml   (PR opened/updated)
  └── apply.cloudbuild.yaml    (approval label added)
        │  posts result back via a GitHub App
        ▼
PR comment
```

Two repos:
- `infrastructure-terraform-gcp` — the agent service, both Cloud Build
  pipelines, and the environment-level Terraform that deploys them.
- `gcp-foundation-module` — reusable, tagged Terraform modules
  (`agent-hosting`, plus the data-platform module at repo root: BigQuery
  datasets, buckets, project IAM). `infrastructure-terraform-gcp/main.tf`
  pins both by git tag (currently `agent-hosting` at `v0.3.9`).

## GitHub App flow

Covered in full in `docs/github_app_design.md`. Summary: a GitHub App
(not a PAT) delivers webhooks to the Cloud Run agent and, separately, is
used by Cloud Build to post comments back — `scripts/github_app.py` mints a
short-lived RS256 JWT from the App's private key (Secret Manager), exchanges
it for an installation token, then calls the REST API. The private key never
enters Terraform state; it's a Secret Manager secret with no
`google_secret_manager_secret_version` resource, added by hand after
`terraform apply` creates the empty secret.

## Cloud Run agent service (`agent-service/`)

`app/main.py` is the only HTTP surface: one route, `POST /webhook/github`.

1. Recompute the HMAC-SHA256 signature over the raw body using the shared
   webhook secret (`GITHUB_WEBHOOK_SECRET`, from Secret Manager) and compare
   in constant time (`app/github_webhook.py:verify_signature`). Reject
   (401) on mismatch — this is the actual authentication boundary, since
   the Cloud Run service itself allows unauthenticated invocations (GitHub
   webhooks can't carry a GCP identity token).
2. Ignore anything that isn't a `pull_request` event.
3. `extract_pr_event` — supported actions
   (`opened`/`synchronize`/`reopened`/`ready_for_review`), draft PRs and
   repos outside `ALLOWED_REPOS` filtered out → triggers the **review**
   build.
4. `extract_apply_event` — action `labeled` with label name
   `approved-for-apply` → triggers the **apply** build. (Same draft/allow-list
   filtering; there is no separate check that the PR is merged — see
   Known Limitations.)

`app/cloudbuild_client.py` triggers builds directly against the Cloud Build
v1 API rather than a pre-registered `BuildTrigger`: it fetches the pipeline
YAML from the PR's exact commit over `raw.githubusercontent.com`, parses it,
and submits the steps inline with `source.connectedRepository` pointing at
the Developer Connect-managed GitHub connection. Auth is the Cloud Run
service's own identity via the metadata server (`sa-agent-review-dev`) — no
`google-auth` dependency, one token fetch is enough.

The deployed container image is currently a placeholder
(`us-docker.pkg.dev/cloudrun/container/hello`) in Terraform, with
`lifecycle.ignore_changes` on the image field — the real agent image is
built and deployed with `gcloud run deploy` outside Terraform, so Terraform
never fights a manual deploy or reverts it back to the placeholder.

## Cloud Build review pipeline (`cloudbuild/review.cloudbuild.yaml`)

Runs as `sa-cb-plan-dev`. Steps, in order:

1. `terraform fmt -check -recursive`
2. `terraform init` (dev backend)
3. `terraform validate`
4. `terraform plan -var-file=environments/dev.tvars -out=tfplan`
5. `terraform show -json tfplan > plan.json`
6. `scripts/policy_checks.py plan.json` → `findings.json`
7. `scripts/summarize_plan.py plan.json` → `summary.md`
8. `scripts/review_generator.py plan.json findings.json` → `review.md`
   (calls an OpenAI-compatible LLM endpoint — currently Gemini's, via
   `MODEL_API_URL`/`MODEL_NAME` substitutions and a Secret Manager API key)
9. `scripts/post_pr_comment.py` — renders `## Policy Checks: ✅/❌` from
   `findings.json` (deterministic, computed independently of the AI output)
   followed by the AI review markdown, and posts it as one PR comment.

Step 9 no-ops (prints and returns) if `PR_NUMBER`/`REPO_FULL_NAME` aren't set
— lets the same pipeline run standalone via `gcloud builds submit` without
erroring.

## Cloud Build apply pipeline (`cloudbuild/apply.cloudbuild.yaml`)

Runs as `sa-cb-apply-dev`, triggered only by the `approved-for-apply` label.
Full detail in `docs/apply_workflow.md`; summary of the step chain:

`terraform-init` → `terraform-plan` → `plan-json` → `policy-checks` →
`policy-gate` (aborts before apply if any policy finding is high-severity)
→ `terraform-apply` (never fails the build directly — exit code is captured
to a file so the next step still runs) → `post-apply-comment` (posts
success/failure + apply output to the PR) → `apply-result-gate` (fails the
build *after* the comment is posted, if the captured exit code was
non-zero).

Both `cb_plan` and `cb_apply` impersonate `sa-tf-deployer-dev`
(`roles/iam.serviceAccountTokenCreator`) to actually run Terraform — neither
pipeline's own service account holds project-level write permissions
directly.

## Terraform module structure

- `infrastructure-terraform-gcp/main.tf` — environment composition: pins
  `gcp-foundation-module` (root = data-platform, `//agent-hosting` =
  agent platform) by tag, passes `foundation-config/foundation.yaml` and
  `var.env`/`var.project`.
- `gcp-foundation-module/` (root) — data-platform module: `bigquery.tf`,
  `storage.tf`, `iam.tf`, driven entirely by `foundation.yaml`
  (datasets, buckets, per-role/per-environment IAM grants, labels).
- `gcp-foundation-module/agent-hosting/` — the review/apply platform itself:
  `agent.tf` (Cloud Run), `agent_iam.tf` (service accounts + grants),
  `secrets.tf`, `registry.tf` (Artifact Registry), `review_artifacts.tf`
  (GCS bucket for plan artifacts), `cloudbuild_connection.tf` (Developer
  Connect GitHub connection). Gated to `env == "dev"` only by a
  `lifecycle.precondition` — this platform is intentionally not deployed to
  `int`.

## Security assumptions

- Webhook authenticity relies entirely on HMAC signature verification with
  a secret only GitHub and this service know (Secret Manager-held, never in
  code or logs).
- Every service account is scoped to what it does: `agent_review` can
  trigger builds and read its own two secrets, not apply Terraform;
  `cb_plan`/`cb_apply` reach GCP write access only by impersonating
  `sa-tf-deployer-dev`, not by holding project IAM roles themselves; secret
  access grants are secret-scoped (`google_secret_manager_secret_iam_member`),
  never project-wide `secretmanager.admin`.
- The GitHub App private key and webhook secret are Secret Manager secrets
  with no Terraform-managed version — they're written by hand once and never
  appear in state or git history.
- `policy_checks.py` runs in both pipelines but only *blocks* in the apply
  pipeline (`policy-gate`); the review pipeline surfaces findings without
  failing the build, since PR feedback should stay visible even when checks
  fail.

## Manual approval model

Approval is a GitHub PR label (`approved-for-apply`), not a Cloud Build
manual-approval trigger or a separate approval service — adding the label is
itself the event the webhook listens for. There's no requirement in the
webhook handler that the PR be merged before the label triggers an apply
build; in practice the label is only ever added after merge, but that's a
process convention, not something the code enforces (see Known Limitations).

## Known limitations

- `extract_apply_event` doesn't verify `pull_request.merged` — labeling an
  *open, unmerged* PR would still trigger the apply pipeline, which would
  then apply whatever `main` currently looks like, not the PR's own changes.
  Low risk in a single-maintainer repo where the label is only ever added
  after merge, but not code-enforced.
- `terraform-apply` in the apply pipeline generates and applies its own
  fresh plan rather than the exact plan a human reviewed in the PR comment —
  state could have moved between review and approval. Upgrade path (see
  `apply.cloudbuild.yaml` comment): have the review pipeline upload
  `plan.json` to the review-artifacts bucket, have the apply pipeline
  download and diff it before applying.
- `policy_checks.py` implements broad-IAM, public-access, and
  required-label checks only — naming-convention, invalid-YAML, and
  "direct resource instead of approved module" checks from the original
  scope aren't implemented yet.
- Everything in `agent-hosting` (the review/apply platform itself) is
  dev-only by design; there's no review/apply automation for other
  environments, only Terraform *config* for them (`environments/int.*`).
- Most hardcoding (project ID, region, Developer Connect connection name,
  GitHub App ID, `env=dev`) is deliberate for a single-environment MVP and
  called out inline (`ponytail:` comments) at each call site as the upgrade
  path once a second environment's pipeline exists.
