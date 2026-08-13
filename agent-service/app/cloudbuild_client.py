"""Triggers cloudbuild/review.cloudbuild.yaml for a PR via the Cloud Build API.

Source comes from the Cloud Build GitHub connection (Developer Connect,
gcp-foundation-module/agent-hosting/cloudbuild_connection.tf) rather than a
git-clone step or uploaded tarball -- Cloud Build fetches the exact commit
itself before running the pipeline.

The Cloud Build v1 `builds.create` endpoint has no `filename` field -- that
key only exists on `BuildTrigger` resources. A direct build (what this is)
must carry its steps inline, same as `gcloud builds submit --config=...`
does under the hood: it parses the YAML client-side and sends `steps`, not
a filename. So the pipeline config itself is fetched from the PR's exact
commit (repo is public) and parsed the same way, then forwarded inline.

Auth is the Cloud Run metadata server (this service's own identity,
sa-agent-review-dev), not a client library -- one stdlib HTTP call is enough
for a single token fetch, no need for google-auth as a dependency.

ponytail: hardcodes project/region/connection name, matching the rest of
this pipeline's dev-only hardcoding (review.cloudbuild.yaml itself is
dev-only). Parameterize once a second environment exists.
"""
import json
import logging
import urllib.error
import urllib.request

import yaml

logger = logging.getLogger(__name__)

METADATA_ROOT = "http://metadata.google.internal/computeMetadata/v1"
PROJECT = "data-platform-aab-dev"
REGION = "europe-west1"
CONNECTED_REPOSITORY = (
    f"projects/{PROJECT}/locations/{REGION}/connections/infra-review-dev"
    "/repositories/infrastructure-terraform-gcp"
)
REVIEW_PIPELINE_CONFIG_PATH = "cloudbuild/review.cloudbuild.yaml"
APPLY_PIPELINE_CONFIG_PATH = "cloudbuild/apply.cloudbuild.yaml"


def _metadata_get(path: str) -> str:
    req = urllib.request.Request(f"{METADATA_ROOT}/{path}", headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode()


def get_access_token() -> str:
    token_json = _metadata_get("instance/service-accounts/default/token")
    return json.loads(token_json)["access_token"]


def fetch_pipeline_config(pr_event: dict, config_path: str) -> dict:
    url = f"https://raw.githubusercontent.com/{pr_event['repo']}/{pr_event['commit_sha']}/{config_path}"
    with urllib.request.urlopen(url) as resp:
        return yaml.safe_load(resp.read())


def build_request_body(pr_event: dict, pipeline_config: dict, extra_substitutions: dict | None = None) -> dict:
    body = {
        "source": {
            "connectedRepository": {
                "repository": CONNECTED_REPOSITORY,
                "dir": ".",
                "revision": pr_event["commit_sha"],
            },
        },
        "steps": pipeline_config["steps"],
        "substitutions": {
            **pipeline_config.get("substitutions", {}),
            **(extra_substitutions or {}),
        },
    }
    for optional_field in ("serviceAccount", "options"):
        if optional_field in pipeline_config:
            body[optional_field] = pipeline_config[optional_field]
    return body


def _trigger_build(pr_event: dict, config_path: str, extra_substitutions: dict, log_label: str) -> None:
    pipeline_config = fetch_pipeline_config(pr_event, config_path)
    body = json.dumps(build_request_body(pr_event, pipeline_config, extra_substitutions)).encode()
    req = urllib.request.Request(
        f"https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}/builds",
        data=body, method="POST",
        headers={"Authorization": f"Bearer {get_access_token()}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        logger.error("Cloud Build API rejected the build: %s %s", e.code, e.read().decode())
        raise
    logger.info("triggered %s build for %s#%s: %s", log_label, pr_event["repo"], pr_event["pr_number"], result.get("metadata"))


def trigger_review_build(pr_event: dict) -> None:
    extra_substitutions = {"_PR_NUMBER": str(pr_event["pr_number"]), "_REPO_FULL_NAME": pr_event["repo"]}
    _trigger_build(pr_event, REVIEW_PIPELINE_CONFIG_PATH, extra_substitutions, "review")


def trigger_apply_build(pr_event: dict) -> None:
    extra_substitutions = {"_PR_NUMBER": str(pr_event["pr_number"]), "_REPO_FULL_NAME": pr_event["repo"]}
    _trigger_build(pr_event, APPLY_PIPELINE_CONFIG_PATH, extra_substitutions, "apply")
