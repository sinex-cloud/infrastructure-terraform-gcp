#!/usr/bin/env python3
"""Post the terraform apply result as a PR comment.

Final step of apply.cloudbuild.yaml. The terraform-apply step never fails
the build directly -- it writes its exit code to apply_status.txt and its
output to apply_output.txt, so this step always runs regardless of apply
outcome. A later gate step re-reads apply_status.txt and fails the build
after this comment has already posted.

Runs under cb_apply, which needs the same github-app-key secretAccessor
grant as cb_plan (agent_iam.tf).
"""
import os

from github_app import post_comment

MAX_OUTPUT_CHARS = 5000


def render_comment(exit_code: int, output: str) -> str:
    badge = "✅ succeeded" if exit_code == 0 else "❌ failed"
    if len(output) > MAX_OUTPUT_CHARS:
        output = f"... (truncated, showing last {MAX_OUTPUT_CHARS} chars)\n" + output[-MAX_OUTPUT_CHARS:]
    return f"## Terraform Apply: {badge}\n\n```\n{output}\n```"


def main():
    pr_number = os.environ.get("PR_NUMBER", "")
    repo = os.environ.get("REPO_FULL_NAME", "")
    if not pr_number or not repo:
        print("PR_NUMBER/REPO_FULL_NAME not set -- not a PR-triggered build, skipping comment.")
        return

    exit_code = int(open("apply_status.txt").read().strip())
    output = open("apply_output.txt").read()
    comment = render_comment(exit_code, output)

    post_comment(repo, pr_number, comment)
    print(f"posted apply comment to {repo}#{pr_number}")


if __name__ == "__main__":
    main()
