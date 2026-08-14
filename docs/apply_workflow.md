# Apply Workflow

How a Terraform change goes from an approved PR to a live GCP change, and
how each failure mode is handled. Architecture-level summary lives in
`docs/technical_design.md`; this is the operational detail.

## Trigger

Apply runs only when a human adds the `approved-for-apply` label to a pull
request. `github_webhook.py`'s `extract_apply_event` matches on the GitHub
`labeled` action + that exact label name, then `cloudbuild_client.py`
triggers `cloudbuild/apply.cloudbuild.yaml` against the PR's head commit SHA
via the Cloud Build API.

Convention, not code, keeps this safe: the label is only ever added on a PR
that's already been merged. The webhook does not check `pull_request.merged`
itself — see `docs/technical_design.md`'s Known Limitations for the gap this
leaves.

## Step chain

1. **terraform-init** — `-backend-config=environments/dev.tfbackend`.
2. **terraform-plan** — `-var-file=environments/dev.tfvars`, output saved to
   `tfplan`. This is a fresh plan generated in this run, not the plan a
   human reviewed in the PR comment (see Known Limitations).
3. **terraform-plan-json** — `terraform show -json` for the policy checker.
4. **policy-checks** — `scripts/policy_checks.py plan.json`, output written
   to `findings.json`. Same script the review pipeline uses; here it's a
   gate, not just a comment.
5. **policy-gate** — aborts the build before `terraform-apply` if
   `findings.json` status is `"failed"`. This is what actually stops a
   high-severity change from being applied, not just flagged.
6. **terraform-apply** — `terraform apply -no-color tfplan`. Exit code and
   output are captured to `apply_status.txt` / `apply_output.txt` instead of
   failing the build immediately, so the next step still runs and reports
   the outcome on the PR either way.
7. **post-apply-comment** — `scripts/post_apply_comment.py` posts a
   ✅/❌ comment with the last 5000 chars of apply output to the PR.
8. **apply-result-gate** — re-reads `apply_status.txt` and fails the build
   now, after the comment is already posted. Cloud Build's own status
   (SUCCESS/FAILURE) ends up matching the actual `terraform apply` result,
   but only after the PR has been told either way.

## Service accounts

The pipeline runs as `sa-cb-apply-dev`. It doesn't hold GCP write
permissions itself — both `terraform-init`/`terraform-plan`/`terraform-apply`
impersonate `sa-tf-deployer-dev` (`roles/iam.serviceAccountTokenCreator`),
and `post-apply-comment` uses a GitHub App installation token minted with
the `github-app-key` secret, same flow `post_pr_comment.py` uses in the
review pipeline. Neither the Cloud Run agent nor its service account ever
touches Terraform state or apply permissions directly.

## Logging

Cloud Build logging is set to `CLOUD_LOGGING_ONLY` — every step's output,
including the full `terraform apply` output, lands in Cloud Logging tied to
the build ID. The PR comment carries a truncated copy (5000 chars) for
quick review; the full record is the Cloud Build log.

## Operating it

1. Open a PR with the Terraform change.
2. Review pipeline runs automatically, posts an AI-assisted review comment.
3. Merge the PR once it's approved.
4. Add the `approved-for-apply` label to trigger the apply build.
5. Watch the PR for the apply-result comment, or check the build in Cloud
   Build directly for full logs.

Known limitations of this pipeline (unmerged-PR gap, fresh-plan-vs-reviewed-
plan gap) are tracked in `docs/technical_design.md`, not duplicated here.
