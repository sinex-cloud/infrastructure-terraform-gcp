from cloudbuild_client import build_request_body


def make_pr_event(**overrides):
    event = {"repo": "sinex-cloud/infrastructure-terraform-gcp", "pr_number": 42,
              "branch": "feat/x", "commit_sha": "abc123", "action": "opened"}
    event.update(overrides)
    return event


def test_source_pins_exact_commit():
    body = build_request_body(make_pr_event())
    assert body["source"]["connectedRepository"]["revision"] == "abc123"


def test_substitutions_carry_pr_number_and_repo():
    body = build_request_body(make_pr_event(pr_number=7, repo="sinex-cloud/other"))
    assert body["substitutions"]["_PR_NUMBER"] == "7"
    assert body["substitutions"]["_REPO_FULL_NAME"] == "sinex-cloud/other"


def test_uses_review_pipeline_config():
    assert build_request_body(make_pr_event())["filename"] == "cloudbuild/review.cloudbuild.yaml"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"{len(tests)} passed")
