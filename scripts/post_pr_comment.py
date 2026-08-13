#!/usr/bin/env python3
"""Post the policy-check + plan-summary results as a PR comment.

Final step of review.cloudbuild.yaml. Auth/posting logic lives in
github_app.py, shared with post_apply_comment.py.

Runs under cb_plan, which has secretAccessor on infra-agent-github-app-key-dev
(agent_iam.tf: cb_plan_reads_github_app_key).
"""
import json
import os

from github_app import post_comment


def render_comment(findings: dict, review_md: str) -> str:
    """Deterministic badge on top (source of truth), AI review explains below."""
    badge = "✅ passed" if findings.get("status") == "passed" else "❌ failed"
    return f"## Policy Checks: {badge}\n\n{review_md}"


def main():
    pr_number = os.environ.get("PR_NUMBER", "")
    repo = os.environ.get("REPO_FULL_NAME", "")
    if not pr_number or not repo:
        print("PR_NUMBER/REPO_FULL_NAME not set -- not a PR-triggered build, skipping comment.")
        return

    findings = json.loads(open("findings.json").read())
    review_md = open("review.md").read()
    comment = render_comment(findings, review_md)

    post_comment(repo, pr_number, comment)
    print(f"posted review comment to {repo}#{pr_number}")


if __name__ == "__main__":
    main()
