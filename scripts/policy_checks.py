#!/usr/bin/env python3
"""Deterministic policy checks against a `terraform show -json` plan.

Reads the plan JSON, walks resource_changes, and reports findings as
structured JSON. Also reads foundation.yaml directly (fixed relative path,
always present at the pipeline's working directory) for the two checks that
are about the config file itself rather than the plan. This script never
fails the build on its own -- it reports "status": "failed" when
high-severity findings exist, and the PR-comment step decides what to do
with that. Blocking is a human-in-the-loop decision at PR review, not a
hard gate here.
"""
import json
import re
import sys

import yaml

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

SNAKE_CASE = re.compile(r"^[a-z][a-z0-9_]*$")
KEBAB_CASE = re.compile(r"^[a-z][a-z0-9-]*$")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# matches variables.tf's own validation -- this project only ever runs dev/int.
VALID_ENVIRONMENTS = {"dev", "int"}

# (resource type, name field) pairs checked for case convention.
DATASET_NAME_FIELDS = {"google_bigquery_dataset": "dataset_id"}
KEBAB_NAME_FIELDS = {
    "google_storage_bucket": "name",
    "google_service_account": "account_id",
}

FOUNDATION_YAML_PATH = "foundation-config/foundation.yaml"


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


def check_direct_resources(changes):
    # main.tf only ever calls gcp-foundation-module (root + //agent-hosting),
    # so every resource address should sit under a "module." prefix. Anything
    # else is a raw resource added straight to this repo, bypassing the
    # approved modules.
    findings = []
    for rc in changes:
        if rc.get("mode") == "data":
            continue
        if not rc["address"].startswith("module."):
            findings.append({
                "severity": "high",
                "rule": "direct_resource_instead_of_module",
                "message": f"{rc['type']} declared directly instead of through an approved module.",
                "resource": rc["address"],
            })
    return findings


def check_naming_conventions(changes):
    findings = []
    for rc in changes:
        after = rc["change"].get("after") or {}
        checked_values = []

        dataset_field = DATASET_NAME_FIELDS.get(rc["type"])
        if dataset_field and after.get(dataset_field):
            value = after[dataset_field]
            checked_values.append(value)
            if not SNAKE_CASE.match(value):
                findings.append({
                    "severity": "medium",
                    "rule": "naming_convention",
                    "message": f"{dataset_field} '{value}' should be snake_case.",
                    "resource": rc["address"],
                })

        kebab_field = KEBAB_NAME_FIELDS.get(rc["type"])
        if kebab_field and after.get(kebab_field):
            value = after[kebab_field]
            checked_values.append(value)
            if not KEBAB_CASE.match(value):
                findings.append({
                    "severity": "medium",
                    "rule": "naming_convention",
                    "message": f"{kebab_field} '{value}' should be lowercase kebab-case.",
                    "resource": rc["address"],
                })

        # IAM member fields legitimately contain emails (user:someone@example.com) --
        # only scan actual resource-name-shaped values, never `member`.
        if rc["type"] not in IAM_MEMBER_TYPES and any(EMAIL_RE.search(v) for v in checked_values):
            findings.append({
                "severity": "high",
                "rule": "naming_convention",
                "message": f"Resource identifier on {rc['address']} looks like it contains an email address.",
                "resource": rc["address"],
            })

        labels = after.get("labels") or {}
        if "managed_by" in labels and labels["managed_by"] != "terraform":
            findings.append({
                "severity": "medium",
                "rule": "naming_convention",
                "message": f"managed_by label is '{labels['managed_by']}', must be 'terraform'.",
                "resource": rc["address"],
            })
        if "environment" in labels and labels["environment"] not in VALID_ENVIRONMENTS:
            findings.append({
                "severity": "medium",
                "rule": "naming_convention",
                "message": f"environment label '{labels['environment']}' is not one of {sorted(VALID_ENVIRONMENTS)}.",
                "resource": rc["address"],
            })
    return findings


def check_yaml_schema(yaml_data):
    # Real syntax errors are caught in main() before this ever runs (they'd
    # also fail terraform plan itself, before policy-checks even starts) --
    # this only catches structurally-wrong-but-parseable YAML.
    if yaml_data is None:
        return []
    findings = []
    expected_types = {
        "managed_datasets": dict,
        "buckets": dict,
        "additional_project_permissions": list,
    }
    for key, expected_type in expected_types.items():
        if key in yaml_data and not isinstance(yaml_data[key], expected_type):
            findings.append({
                "severity": "high",
                "rule": "invalid_yaml_schema",
                "message": f"'{key}' should be a {expected_type.__name__}, got {type(yaml_data[key]).__name__}.",
                "resource": FOUNDATION_YAML_PATH,
            })
    return findings


def check_missing_environment_configuration(yaml_data):
    if yaml_data is None:
        return []
    findings = []

    def check_entry(name, entry, label):
        envs = entry.get("environments") if isinstance(entry, dict) else None
        if not envs:
            findings.append({
                "severity": "medium",
                "rule": "missing_environment_configuration",
                "message": f"{label} '{name}' has no environments configured -- it will never deploy anywhere.",
                "resource": name,
            })
        elif not any(env in VALID_ENVIRONMENTS for env in envs):
            findings.append({
                "severity": "medium",
                "rule": "missing_environment_configuration",
                "message": f"{label} '{name}' environments {envs} don't include any of {sorted(VALID_ENVIRONMENTS)} -- it will never deploy.",
                "resource": name,
            })

    # Malformed types (wrong shape for a key) are check_yaml_schema's job to
    # report -- skip them here rather than crash on the same bad data.
    datasets = yaml_data.get("managed_datasets")
    if isinstance(datasets, dict):
        for name, dataset in datasets.items():
            check_entry(name, dataset, "Dataset")

    buckets = yaml_data.get("buckets")
    if isinstance(buckets, dict):
        for name, bucket in buckets.items():
            check_entry(name, bucket, "Bucket")

    permissions = yaml_data.get("additional_project_permissions")
    if isinstance(permissions, list):
        for i, permission in enumerate(permissions):
            label = permission.get("role", f"#{i}") if isinstance(permission, dict) else f"#{i}"
            check_entry(label, permission, "Project permission")

    return findings


def run_checks(plan, yaml_data=None):
    changes = list(iter_active_changes(plan))
    findings = (
        check_broad_iam_roles(changes)
        + check_public_access(changes)
        + check_required_labels(changes)
        + check_direct_resources(changes)
        + check_naming_conventions(changes)
        + check_yaml_schema(yaml_data)
        + check_missing_environment_configuration(yaml_data)
    )
    status = "failed" if any(f["severity"] == "high" for f in findings) else "passed"
    return {"status": status, "findings": findings}


def load_foundation_yaml(path=FOUNDATION_YAML_PATH):
    try:
        with open(path) as f:
            return yaml.safe_load(f), None
    except FileNotFoundError:
        return None, None
    except yaml.YAMLError as e:
        return None, str(e)


def main():
    raw = sys.stdin.read() if len(sys.argv) < 2 else open(sys.argv[1]).read()
    plan = json.loads(raw)
    yaml_data, yaml_error = load_foundation_yaml()
    result = run_checks(plan, yaml_data)
    if yaml_error:
        result["findings"].insert(0, {
            "severity": "high",
            "rule": "invalid_yaml",
            "message": f"foundation.yaml failed to parse: {yaml_error}",
            "resource": FOUNDATION_YAML_PATH,
        })
        result["status"] = "failed"
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
