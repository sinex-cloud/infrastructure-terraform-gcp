#!/usr/bin/env python3
"""Post the policy-check + plan-summary results as a PR comment.

Final step of review.cloudbuild.yaml. Authenticates as the GitHub App
(mints a short-lived RS256 JWT, exchanges it for an installation token --
see docs/github_app_design.md) and posts one comment per review run.

Runs under cb_plan, which has secretAccessor on infra-agent-github-app-key-dev
(agent_iam.tf: cb_plan_reads_github_app_key). Needs `gcloud` and `openssl` on
PATH, which the cloud-sdk builder image this step runs in provides -- no pip
install needed.

ponytail: hardcodes env=dev and the App ID, matching the rest of this
pipeline (backend-config/var-file are already dev-only). Parameterize both
once a second environment's pipeline exists.
"""
import base64
import json
import os
import subprocess
import tempfile
import time
import urllib.request

GITHUB_APP_ID = "4388945"
ENV = "dev"
API_ROOT = "https://api.github.com"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def fetch_private_key() -> bytes:
    secret = f"infra-agent-github-app-key-{ENV}"
    out = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest", f"--secret={secret}"],
        check=True, capture_output=True,
    )
    return out.stdout


def sign_rs256(signing_input: bytes, private_key_pem: bytes) -> bytes:
    """RS256-sign with openssl -- avoids pulling in `cryptography`/PyJWT for one call."""
    with tempfile.NamedTemporaryFile(suffix=".pem") as key_file:
        key_file.write(private_key_pem)
        key_file.flush()
        out = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", key_file.name],
            input=signing_input, capture_output=True, check=True,
        )
    return out.stdout


def make_jwt(private_key_pem: bytes) -> str:
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {"iat": now - 60, "exp": now + 540, "iss": GITHUB_APP_ID}
    signing_input = f"{b64url(json.dumps(header).encode())}.{b64url(json.dumps(payload).encode())}".encode()
    signature = sign_rs256(signing_input, private_key_pem)
    return f"{signing_input.decode()}.{b64url(signature)}"


def github_api(url: str, token: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}" if token.count(".") == 2 else f"token {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


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

    private_key = fetch_private_key()
    jwt = make_jwt(private_key)
    installation = github_api(f"{API_ROOT}/repos/{repo}/installation", jwt)
    token_resp = github_api(f"{API_ROOT}/app/installations/{installation['id']}/access_tokens", jwt, method="POST")
    github_api(
        f"{API_ROOT}/repos/{repo}/issues/{pr_number}/comments",
        token_resp["token"], method="POST", body={"body": comment},
    )
    print(f"posted review comment to {repo}#{pr_number}")


if __name__ == "__main__":
    main()
