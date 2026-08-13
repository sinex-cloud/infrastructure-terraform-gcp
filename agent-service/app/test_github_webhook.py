"""Self-check for signature verification and payload filtering. Run: python -m app.test_github_webhook"""
import hashlib
import hmac

from app.github_webhook import extract_apply_event, extract_pr_event, verify_signature


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_verify_signature():
    secret = "test-secret"
    body = b'{"hello": "world"}'
    assert verify_signature(secret, body, _sign(secret, body))
    assert not verify_signature(secret, body, "sha256=deadbeef")
    assert not verify_signature(secret, body, None)
    assert not verify_signature(secret, body, "not-prefixed")


def test_extract_pr_event():
    payload = {
        "action": "opened",
        "number": 42,
        "repository": {"full_name": "sinex-cloud/infrastructure-terraform-gcp"},
        "pull_request": {"draft": False, "head": {"ref": "feature/x", "sha": "abc123"}},
    }
    assert extract_pr_event(payload) == {
        "repo": "sinex-cloud/infrastructure-terraform-gcp",
        "pr_number": 42,
        "branch": "feature/x",
        "commit_sha": "abc123",
        "action": "opened",
    }

    draft_payload = {**payload, "pull_request": {**payload["pull_request"], "draft": True}}
    assert extract_pr_event(draft_payload) is None

    other_repo_payload = {**payload, "repository": {"full_name": "someone-else/repo"}}
    assert extract_pr_event(other_repo_payload) is None

    unsupported_action_payload = {**payload, "action": "closed"}
    assert extract_pr_event(unsupported_action_payload) is None


def test_extract_apply_event():
    payload = {
        "action": "labeled",
        "label": {"name": "approved-for-apply"},
        "number": 42,
        "repository": {"full_name": "sinex-cloud/infrastructure-terraform-gcp"},
        "pull_request": {"draft": False, "head": {"ref": "feature/x", "sha": "abc123"}},
    }
    assert extract_apply_event(payload) == {
        "repo": "sinex-cloud/infrastructure-terraform-gcp",
        "pr_number": 42,
        "branch": "feature/x",
        "commit_sha": "abc123",
        "action": "labeled",
    }

    other_label_payload = {**payload, "label": {"name": "bug"}}
    assert extract_apply_event(other_label_payload) is None

    wrong_action_payload = {**payload, "action": "opened"}
    assert extract_apply_event(wrong_action_payload) is None

    draft_payload = {**payload, "pull_request": {**payload["pull_request"], "draft": True}}
    assert extract_apply_event(draft_payload) is None


if __name__ == "__main__":
    test_verify_signature()
    test_extract_pr_event()
    test_extract_apply_event()
    print("ok")
