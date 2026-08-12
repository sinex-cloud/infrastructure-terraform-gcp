#!/usr/bin/env python3
"""Deterministic policy checks against a `terraform show -json` plan.

Reads the plan JSON, walks resource_changes, and reports findings as
structured JSON. This script never fails the build on its own -- it reports
"status": "failed" when high-severity findings exist, and the PR-comment
step decides what to do with that. Blocking is a human-in-the-loop decision
at PR review, not a hard gate here.

ponytail: naming-convention and "direct resource vs module" checks are not
implemented -- some root-level Terraform here is intentional, not a mistake,
so a generic direct-resource rule would just flag known-good files. Add
scoped rules if that changes.
"""
import json
import sys

REQUIRED_LABELS = {
    "platform",
    "owner",
    "application",
    "data_classification",
    "environment",
    "managed_by",
    "component",
}

BROAD_PROJECT_ROLES = {"roles/owner", "roles/editor"}
PUBLIC_MEMBERS = {"allUsers", "allAuthenticatedUsers"}

LABELLABLE_TYPES = {
    "google_storage_bucket",
    "google_bigquery_dataset",
    "google_artifact_registry_repository",
    "google_cloud_run_v2_service",
    "google_secret_manager_secret",
}

IAM_MEMBER_TYPES = {
    "google_project_iam_member",
    "google_project_iam_binding",
    "google_storage_bucket_iam_member",
    "google_bigquery_dataset_iam_member",
    "google_cloud_run_v2_service_iam_member",
    "google_secret_manager_secret_iam_member",
}

# public access on these is expected/documented, not a bug -- report at
# medium so it stays visible without tripping "failed" on its own.
PUBLIC_ACCESS_EXPECTED_TYPES = {"google_cloud_run_v2_service_iam_member"}


def iter_active_changes(plan):
    for rc in plan.get("resource_changes", []):
        actions = rc.get("change", {}).get("actions", [])
        if actions in (["delete"], ["no-op"]):
            continue
        yield rc


def check_broad_iam_roles(changes):
    findings = []
    for rc in changes:
        if rc["type"] not in IAM_MEMBER_TYPES:
            continue
        after = rc["change"].get("after") or {}
        role = after.get("role")
        if role in BROAD_PROJECT_ROLES:
            findings.append({
                "severity": "high",
                "rule": "no_broad_iam_role",
                "message": f"{role} is too broad for {rc['type']}.",
                "resource": rc["address"],
            })
    return findings


def check_public_access(changes):
    findings = []
    for rc in changes:
        if rc["type"] not in IAM_MEMBER_TYPES:
            continue
        after = rc["change"].get("after") or {}
        member = after.get("member")
        if member in PUBLIC_MEMBERS:
            severity = "medium" if rc["type"] in PUBLIC_ACCESS_EXPECTED_TYPES else "high"
            findings.append({
                "severity": severity,
                "rule": "public_access",
                "message": f"{member} granted on {rc['type']}.",
                "resource": rc["address"],
            })
    return findings


def check_required_labels(changes):
    findings = []
    for rc in changes:
        if rc["type"] not in LABELLABLE_TYPES:
            continue
        after = rc["change"].get("after") or {}
        labels = after.get("labels") or {}
        missing = sorted(REQUIRED_LABELS - labels.keys())
        if missing:
            findings.append({
                "severity": "medium",
                "rule": "missing_labels",
                "message": f"Missing required labels: {', '.join(missing)}.",
                "resource": rc["address"],
            })
    return findings


def run_checks(plan):
    changes = list(iter_active_changes(plan))
    findings = (
        check_broad_iam_roles(changes)
        + check_public_access(changes)
        + check_required_labels(changes)
    )
    status = "failed" if any(f["severity"] == "high" for f in findings) else "passed"
    return {"status": status, "findings": findings}


def main():
    raw = sys.stdin.read() if len(sys.argv) < 2 else open(sys.argv[1]).read()
    plan = json.loads(raw)
    result = run_checks(plan)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
