# Demo Scenario

Reproducible walkthrough of the full review-and-apply flow. Two example
changes below aren't fabricated output — `plan.json` in each folder is a
minimal fixture matching `terraform show -json` shape, and `findings.json`
next to it was produced by actually running the real checker against it:

```bash
python3 scripts/policy_checks.py examples/valid-change/plan.json
python3 scripts/policy_checks.py examples/risky-change/plan.json
```

## 1. Valid infrastructure change

`valid-change/foundation.yaml.diff` — adds a new bucket to
`foundation-config/foundation.yaml`. The module derives all seven required
labels automatically, so the plan (`valid-change/plan.json`) passes
policy checks clean: `valid-change/findings.json` → `"status": "passed"`.

## 2. Risky infrastructure change

`risky-change/foundation.yaml.diff` — grants `roles/owner` at the project
level through `additional_project_permissions`, something the platform
should never hand out. Same fixture pattern: `risky-change/plan.json` in,
run through the real checker.

## 3 & 4. Pull request review flow + policy failure

Opening either diff as a PR triggers `cloudbuild/review.cloudbuild.yaml`:
`terraform plan` → policy checks → AI review → PR comment. For the risky
change, `risky-change/findings.json` is exactly what that pipeline step
would produce and post:

```json
{
  "status": "failed",
  "findings": [{
    "severity": "high",
    "rule": "no_broad_iam_role",
    "message": "roles/owner is too broad for google_project_iam_member.",
    "resource": "module.data_platform.google_project_iam_member.project[\"owner_user:someone@example.com\"]"
  }]
}
```

`policy-checks` never blocks the review pipeline itself (findings should
stay visible on the PR even when they fail) — it's the apply pipeline's
`policy-gate` step that would actually refuse to run `terraform apply` on
this change.

## 5. AI-generated review comment

Real comments posted by this pipeline, unedited, from merged PRs in this
repo:

> ## Policy Checks: ✅ passed
>
> **Risk level:** Low
>
> **Summary:** This pull request updates
> `module.agent_hosting.google_cloud_run_v2_service.agent` in the `dev`
> environment.
>
> **Findings:**
> - Missing required labels: data_classification.
>   (`module.agent_hosting.google_cloud_run_v2_service.agent`)
>
> **Required action:** None.

(from [PR #5](https://github.com/sinex-cloud/infrastructure-terraform-gcp/pull/5))

## 6. Merge after approval

Same PR #5 — merged into `main` after the review comment above.

## 7. CI apply workflow with manual approval

Also from PR #5: adding the `approved-for-apply` label triggered
`cloudbuild/apply.cloudbuild.yaml`, which ran a fresh plan, passed
`policy-gate`, applied, and posted the real result:

> ## Terraform Apply: ✅ succeeded
>
> ```
> Apply complete! Resources: 0 added, 0 changed, 1 destroyed.
> ```

Full step-by-step for this pipeline: `docs/apply_workflow.md`.
