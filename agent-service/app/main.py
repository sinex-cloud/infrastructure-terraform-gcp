import os

from fastapi import FastAPI, HTTPException, Request

from app.cloudbuild_client import trigger_apply_build, trigger_review_build
from app.github_webhook import extract_apply_event, extract_pr_event, verify_signature

app = FastAPI()

WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")


@app.post("/webhook/github")
async def github_webhook(request: Request) -> dict:
    raw_body = await request.body()
    if not verify_signature(WEBHOOK_SECRET, raw_body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=401, detail="invalid signature")

    if request.headers.get("X-GitHub-Event") != "pull_request":
        return {"status": "ignored"}  # e.g. GitHub's own "ping" event, or an event we didn't subscribe to

    payload = await request.json()

    pr_event = extract_pr_event(payload)
    if pr_event is not None:
        trigger_review_build(pr_event)
        return {"status": "accepted", **pr_event}

    apply_event = extract_apply_event(payload)
    if apply_event is not None:
        trigger_apply_build(apply_event)
        return {"status": "accepted", **apply_event}

    return {"status": "ignored"}  # unsupported action, draft PR, wrong label, or a repo not on the allow-list
