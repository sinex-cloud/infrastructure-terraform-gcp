import os

from fastapi import FastAPI, HTTPException, Request

from app.cloudbuild_client import trigger_review_build
from app.github_webhook import extract_pr_event, verify_signature

app = FastAPI()

WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")


@app.post("/webhook/github")
async def github_webhook(request: Request) -> dict:
    raw_body = await request.body()
    if not verify_signature(WEBHOOK_SECRET, raw_body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=401, detail="invalid signature")

    if request.headers.get("X-GitHub-Event") != "pull_request":
        return {"status": "ignored"}  # e.g. GitHub's own "ping" event, or an event we didn't subscribe to

    pr_event = extract_pr_event(await request.json())
    if pr_event is None:
        return {"status": "ignored"}  # unsupported action, draft PR, or a repo not on the allow-list

    trigger_review_build(pr_event)
    return {"status": "accepted", **pr_event}
