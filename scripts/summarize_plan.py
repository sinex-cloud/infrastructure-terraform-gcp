#!/usr/bin/env python3
"""Turn a `terraform show -json` plan into a short Markdown summary.

Groups resource changes by action (create/update/delete/replace), lists
IAM-related changes separately, and flags risky ones (broad roles, public
access) using the same rules as policy_checks.py.
"""
import json
import sys

from policy_checks import BROAD_PROJECT_ROLES, IAM_MEMBER_TYPES, PUBLIC_MEMBERS

ACTION_GROUPS = {
    ("create",): "create",
    ("update",): "update",
    ("delete",): "delete",
    ("delete", "create"): "replace",
    ("create", "delete"): "replace",
}


def classify(actions):
    return ACTION_GROUPS.get(tuple(actions))


def is_risky(rc):
    if rc["type"] not in IAM_MEMBER_TYPES:
        return False
    after = rc["change"].get("after") or {}
    return after.get("role") in BROAD_PROJECT_ROLES or after.get("member") in PUBLIC_MEMBERS


def summarize(plan):
    env = plan.get("variables", {}).get("env", {}).get("value", "unknown")
    groups = {"create": [], "update": [], "delete": [], "replace": []}
    iam_changes = []
    risky = []

    for rc in plan.get("resource_changes", []):
        group = classify(rc["change"]["actions"])
        if group is None:  # no-op
            continue
        groups[group].append(rc["address"])
        if rc["type"] in IAM_MEMBER_TYPES:
            iam_changes.append(rc["address"])
        if is_risky(rc):
            risky.append(rc["address"])

    return {"environment": env, "changes": groups, "iam_changes": iam_changes, "risky": risky}


def render_markdown(summary):
    changes = summary["changes"]
    counts = ", ".join(f"{len(v)} to {k}" for k, v in changes.items() if v) or "no changes"

    lines = [
        "## Terraform Plan Summary",
        "",
        f"**Environment:** {summary['environment']}",
        f"**Resources:** {counts}",
        "",
    ]

    for group, label in [("create", "Create"), ("update", "Update"), ("replace", "Replace"), ("delete", "Delete")]:
        if changes[group]:
            lines.append(f"### {label}")
            lines += [f"- {addr}" for addr in changes[group]]
            lines.append("")

    lines.append("### IAM Changes")
    lines += [f"- {addr}" for addr in summary["iam_changes"]] or ["- none"]
    lines.append("")

    lines.append("### Risky Changes")
    lines += [f"- {addr}" for addr in summary["risky"]] or ["- none"]

    return "\n".join(lines)


def main():
    raw = sys.stdin.read() if len(sys.argv) < 2 else open(sys.argv[1]).read()
    plan = json.loads(raw)
    print(render_markdown(summarize(plan)))


if __name__ == "__main__":
    main()
