#!/usr/bin/env python3
"""Generate an AI-assisted PR review from the plan summary and policy findings.

Runs after terraform-plan-json and policy-checks in review.cloudbuild.yaml.
Recomputes the structured plan summary from plan.json (summarize_plan.summarize)
rather than re-parsing summary.md, since that's already structured data.

Calls an OpenAI-compatible /chat/completions endpoint -- covers OpenAI, Groq,
Together, Mistral, DeepSeek, OpenRouter, etc. with no code change, just
MODEL_API_URL/MODEL_NAME. Swapping to a provider with a different response
shape only touches call_model().

ponytail: hardcodes env=dev, same as post_pr_comment.py and the rest of this
pipeline. Parameterize once a second environment's pipeline exists.
"""
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from summarize_plan import summarize

ENV = "dev"
PROMPT_PATH = Path(__file__).parent / "pr_review_prompt.md"


def fetch_api_key() -> str:
    secret = f"infra-agent-model-api-key-{ENV}"
    out = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest", f"--secret={secret}"],
        check=True, capture_output=True,
    )
    return out.stdout.decode().strip()


def build_messages(policy_findings: dict, plan_summary: dict) -> list[dict]:
    system_prompt = PROMPT_PATH.read_text()
    user_payload = json.dumps({"policy_findings": policy_findings, "plan_summary": plan_summary})
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_payload},
    ]


def call_model(messages: list[dict]) -> str:
    api_url = os.environ["MODEL_API_URL"].rstrip("/")
    model = os.environ["MODEL_NAME"]
    body = json.dumps({"model": model, "messages": messages, "temperature": 0.2}).encode()
    req = urllib.request.Request(f"{api_url}/chat/completions", data=body, headers={
        "Authorization": f"Bearer {fetch_api_key()}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
    return result["choices"][0]["message"]["content"]


def main():
    if len(sys.argv) < 3:
        print("usage: review_generator.py <plan.json> <findings.json>", file=sys.stderr)
        sys.exit(1)

    if not os.environ.get("MODEL_API_URL") or not os.environ.get("MODEL_NAME"):
        print("_AI review skipped: MODEL_API_URL/MODEL_NAME not configured._")
        return

    plan = json.loads(open(sys.argv[1]).read())
    findings = json.loads(open(sys.argv[2]).read())
    messages = build_messages(findings, summarize(plan))
    print(call_model(messages))


if __name__ == "__main__":
    main()
