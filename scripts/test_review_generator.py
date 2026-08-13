import json

from review_generator import build_messages


def test_build_messages_has_system_and_user_roles():
    messages = build_messages({"status": "passed", "findings": []}, {"environment": "dev"})
    assert [m["role"] for m in messages] == ["system", "user"]


def test_build_messages_system_prompt_is_the_prompt_file():
    messages = build_messages({"status": "passed", "findings": []}, {"environment": "dev"})
    assert "Risk level" in messages[0]["content"]


def test_build_messages_user_payload_round_trips_inputs():
    findings = {"status": "failed", "findings": [{"severity": "high", "rule": "no_broad_iam_role", "resource": "a.b", "message": "roles/owner is too broad."}]}
    plan_summary = {"environment": "dev", "changes": {"create": ["a.b"]}, "iam_changes": ["a.b"], "risky": ["a.b"]}
    messages = build_messages(findings, plan_summary)
    payload = json.loads(messages[1]["content"])
    assert payload["policy_findings"] == findings
    assert payload["plan_summary"] == plan_summary


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"{len(tests)} passed")
