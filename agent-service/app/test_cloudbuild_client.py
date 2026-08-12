from cloudbuild_client import build_request_body


def make_pr_event(**overrides):
    event = {"repo": "sinex-cloud/infrastructure-terraform-gcp", "pr_number": 42,
              "branch": "feat/x", "commit_sha": "abc123", "action": "opened"}
    event.update(overrides)
    return event


def make_pipeline_config(**overrides):
    config = {
        "steps": [{"id": "terraform-fmt", "name": "hashicorp/terraform:1.15.8", "args": ["fmt", "-check"]}],
        "serviceAccount": "projects/$PROJECT_ID/serviceAccounts/sa-cb-plan-dev@$PROJECT_ID.iam.gserviceaccount.com",
        "substitutions": {"_PR_NUMBER": "", "_REPO_FULL_NAME": "sinex-cloud/infrastructure-terraform-gcp"},
        "options": {"logging": "CLOUD_LOGGING_ONLY"},
    }
    config.update(overrides)
    return config


def test_source_pins_exact_commit():
    body = build_request_body(make_pr_event(), make_pipeline_config())
    assert body["source"]["connectedRepository"]["revision"] == "abc123"


def test_substitutions_carry_pr_number_and_repo():
    body = build_request_body(make_pr_event(pr_number=7, repo="sinex-cloud/other"), make_pipeline_config())
    assert body["substitutions"]["_PR_NUMBER"] == "7"
    assert body["substitutions"]["_REPO_FULL_NAME"] == "sinex-cloud/other"


def test_steps_forwarded_inline_not_filename():
    body = build_request_body(make_pr_event(), make_pipeline_config())
    assert "filename" not in body
    assert body["steps"][0]["id"] == "terraform-fmt"


def test_service_account_and_options_forwarded():
    body = build_request_body(make_pr_event(), make_pipeline_config())
    assert body["serviceAccount"] == make_pipeline_config()["serviceAccount"]
    assert body["options"] == {"logging": "CLOUD_LOGGING_ONLY"}


def test_optional_fields_omitted_when_absent():
    config = make_pipeline_config()
    del config["serviceAccount"]
    del config["options"]
    body = build_request_body(make_pr_event(), config)
    assert "serviceAccount" not in body
    assert "options" not in body


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"{len(tests)} passed")
