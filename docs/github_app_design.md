# GitHub App Design

Deliverable 2. Documents the registered GitHub App and the design it implies for
the agent service (Phase 2/3 build out the code; this records what's already live).

## App identity

- Name: `sinex-infra-review-agent-dev`
- App ID: `4388945`
- Owned by: `@sinex-cloud` (personal account, not an org — the two Terraform repos
  live there, so App ownership follows the repos)
- Installed on: `sinex-cloud/infrastructure-terraform-gcp`
- Installation scope: "Only on this account" — not a public/marketplace App

## Required permissions

Repository permissions only; no organization or account permissions.

| Permission | Level | Why |
|---|---|---|
| Metadata | Read-only | Mandatory baseline GitHub forces on every App. |
| Contents | Read-only | Read repo content / identify changed files for the diff. Not write — the apply pipeline (Phase 4) uses Cloud Build's own service account, never this App's installation token, so the App never needs to push code. |
| Pull requests | Read & write | Read for PR metadata; write is what lets the agent post the review comment. |

**Explicitly not granted**: Checks (`checks:write`). The scope document lists GitHub
Checks integration as optional/"improved version"; the phase plan cuts it for the
MVP deadline. A PR comment is the full review surface for now — see "Optional
Checks integration" below.

## Required webhook events

Subscribed to a single event:

- **Pull request** — covers the `opened`, `synchronize`, `reopened`, and
  `ready_for_review` actions GitHub groups under this one event. The webhook
  handler filters on the `action` field of the payload rather than subscribing
  to four separate events.

**Explicitly not subscribed**: `Issue comment`. The `/infra-review` slash-command
feature is also cut for this phase.

## Webhook endpoint

```
https://infra-review-agent-dev-654528170038.europe-west1.run.app/webhook/github
```

Path is `/webhook/github` specifically (not just `/webhook`) — matches the route
specified in the project scope document, so Phase 2's handler code has a fixed
target to implement against. Cloud Run's URL itself is stable per revision/service
(not per deployment), so this endpoint doesn't change as the container image is
updated.

## Secret management

Two secrets in Secret Manager, both created as **empty containers by Terraform**
(`agent-hosting/secrets.tf`) with values added by hand afterward — values never enter
Terraform state or git history:

| Secret | Contents | Populated |
|---|---|---|
| `infra-agent-github-webhook-secret-dev` | 64-char hex string (`openssl rand -hex 32`), used as the HMAC key GitHub signs webhook payloads with | Yes, version 1 |
| `infra-agent-github-app-key-dev` | RSA private key (PEM), downloaded once from GitHub at App-creation time, used to sign JWTs for App authentication | Yes, version 1 |

A third secret, `infra-agent-model-api-key-dev`, exists as an empty container for
the Phase 3 AI review layer — not yet populated, not yet used.

Two service accounts have `roles/secretmanager.secretAccessor` on
`infra-agent-github-app-key-dev` — `sa-agent-review-dev` (Cloud Run) and
`sa-cb-plan-dev` (Cloud Build). Only `sa-cb-plan-dev` actually mints a JWT with
it today (see "How PR comments are posted" below); the Cloud Run agent's grant
is unused until Checks-status updates need it.

## Authentication flow

GitHub Apps authenticate in two steps, not with a single static token:

1. Sign a short-lived JWT (RS256, `iss` = App ID `4388945`, `exp` ≈ 9 minutes)
   using the private key from `infra-agent-github-app-key-dev`. This JWT
   authenticates as the **App itself**. `scripts/post_pr_comment.py` does this
   with `openssl dgst -sign` rather than a JWT library — one RSA signature
   doesn't justify a new Python dependency in the build image.
2. Exchange that JWT for a short-lived **installation access token** via
   `POST /app/installations/{installation_id}/access_tokens`. This token
   authenticates as the **App acting on a specific repo installation**, scoped
   to the permissions granted above, and is what's actually used to call the
   PR comment API.

Installation access tokens expire in ~1 hour and are not persisted — a fresh
one is minted per review run rather than cached.

## Webhook signature verification

Every inbound request's `X-Hub-Signature-256` header is an HMAC-SHA256 of the raw
request body, keyed with the value from `infra-agent-github-webhook-secret-dev`.
The agent must recompute this and reject any request where it doesn't match,
**before** parsing the payload. This is the actual security boundary for the
endpoint — Cloud Run's IAM invoker policy is `allUsers` (GitHub cannot present a
GCP identity token), so without signature verification the endpoint would accept
forged events from anyone.

## How PR comments are posted

The comment is posted from the last step of `cloudbuild/review.cloudbuild.yaml`
(`scripts/post_pr_comment.py`), not by the Cloud Run agent — a deliberate
deviation from the original design (agent reads artifacts after the build
finishes). The agent's webhook call returns before the build starts; without
Pub/Sub wired up, it has no way to know when the build is done. Posting from
inside the build itself sidesteps that: the `policy-checks` and `plan-summary`
steps write their output to local files (`findings.json`, `summary.md`), and
the final step reads those files directly and posts one comment combining
both, using the same JWT/installation-token flow described above (minted with
`sa-cb-plan-dev`'s access to `infra-agent-github-app-key-dev`, not the agent's).

The Cloud Run agent's role ends at triggering the build
(`app/cloudbuild_client.py`): it calls the Cloud Build API with the PR's exact
commit SHA, sourced through Cloud Build's own GitHub connection
(`agent-hosting/cloudbuild_connection.tf`, Developer Connect — a separate
GitHub integration from this App, installed only for fetching source, not for
posting comments). `_PR_NUMBER`/`_REPO_FULL_NAME` substitutions carry the PR
identity through to the comment step.

Builds not triggered by a PR (e.g. manual `gcloud builds submit` runs) leave
those substitutions empty; `post_pr_comment.py` treats that as "skip", not an
error. One comment per review run — no comment threading/editing logic for
the MVP.

## Optional GitHub Checks integration

Not implemented, not planned before the deadline. The scope document lists Checks
runs (`in_progress` → `completed` status) as an "improved version" feature on top
of the MVP's PR-comment-only review. Cut to protect the Phase 2 timeline; the App
was deliberately not granted the `checks:write` permission it would require, so
enabling this later means both a permission change on the App and new agent code,
not just new code.
