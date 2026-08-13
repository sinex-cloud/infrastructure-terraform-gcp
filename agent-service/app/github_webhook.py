"""Webhook signature verification and payload filtering for GitHub pull_request events."""
import hashlib
import hmac
import os

SUPPORTED_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review"}
APPROVAL_LABEL = "approved-for-apply"
ALLOWED_REPOS = {
    r.strip()
    for r in os.environ.get("ALLOWED_REPOS", "sinex-cloud/infrastructure-terraform-gcp").split(",")
    if r.strip()
}


def verify_signature(secret: str, raw_body: bytes, signature_header: str | None) -> bool:
    """Recompute the HMAC-SHA256 signature GitHub sends and compare in constant time."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    got = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, got)


def _pr_metadata(payload: dict) -> dict | None:
    """Shared PR metadata extraction: draft/repo-allowlist filtering, common to review and apply events."""
    pr = payload.get("pull_request", {})
    if pr.get("draft"):
        return None
    repo_full_name = payload.get("repository", {}).get("full_name")
    if repo_full_name not in ALLOWED_REPOS:
        return None
    return {
        "repo": repo_full_name,
        "pr_number": payload.get("number"),
        "branch": pr.get("head", {}).get("ref"),
        "commit_sha": pr.get("head", {}).get("sha"),
        "action": payload.get("action"),
    }


def extract_pr_event(payload: dict) -> dict | None:
    """Return PR metadata if this payload is a supported, actionable pull_request event; else None."""
    if payload.get("action") not in SUPPORTED_ACTIONS:
        return None
    return _pr_metadata(payload)


def extract_apply_event(payload: dict) -> dict | None:
    """Return PR metadata if this payload is the approval label being added; else None."""
    if payload.get("action") != "labeled":
        return None
    if payload.get("label", {}).get("name") != APPROVAL_LABEL:
        return None
    return _pr_metadata(payload)
