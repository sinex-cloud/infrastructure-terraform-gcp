"""Triggers cloudbuild/review.cloudbuild.yaml for a PR via the Cloud Build API.

Source comes from the Cloud Build GitHub connection (Developer Connect,
gcp-foundation-module/agent-hosting/cloudbuild_connection.tf) rather than a
git-clone step or uploaded tarball -- Cloud Build fetches the exact commit
itself before running the pipeline.

Auth is the Cloud Run metadata server (this service's own identity,
sa-agent-review-dev), not a client library -- one stdlib HTTP call is enough
for a single token fetch, no need for google-auth as a dependency.

ponytail: hardcodes project/region/connection name, matching the rest of
this pipeline's dev-only hardcoding (review.cloudbuild.yaml itself is
dev-only). Parameterize once a second environment exists.
"""
import json
import logging
import urllib.request

logger = logging.getLogger(__name__)

METADATA_ROOT = "http://metadata.google.internal/computeMetadata/v1"
PROJECT = "data-platform-aab-dev"
REGION = "europe-west1"
CONNECTED_REPOSITORY = (
    f"projects/{PROJECT}/locations/{REGION}/connections/infra-review-dev"
    "/repositories/infrastructure-terraform-gcp"
)


def _metadata_get(path: str) -> str:
    req = urllib.request.Request(f"{METADATA_ROOT}/{path}", headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode()


def get_access_token() -> str:
    token_json = _metadata_get("instance/service-accounts/default/token")
    return json.loads(token_json)["access_token"]


def build_request_body(pr_event: dict) -> dict:
    return {
        "source": {
            "connectedRepository": {
                "repository": CONNECTED_REPOSITORY,
                "dir": ".",
                "revision": pr_event["commit_sha"],
            },
        },
        "filename": "cloudbuild/review.cloudbuild.yaml",
        "substitutions": {
            "_PR_NUMBER": str(pr_event["pr_number"]),
            "_REPO_FULL_NAME": pr_event["repo"],
        },
    }


def trigger_review_build(pr_event: dict) -> None:
    body = json.dumps(build_request_body(pr_event)).encode()
    req = urllib.request.Request(
        f"https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}/builds",
        data=body, method="POST",
        headers={"Authorization": f"Bearer {get_access_token()}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
    logger.info("triggered review build for %s#%s: %s", pr_event["repo"], pr_event["pr_number"], result.get("metadata"))
