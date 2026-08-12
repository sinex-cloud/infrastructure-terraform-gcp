from policy_checks import run_checks


def test_broad_role_flagged():
    plan = {"resource_changes": [{
        "address": "google_project_iam_member.bad",
        "type": "google_project_iam_member",
        "change": {"actions": ["create"], "after": {"role": "roles/owner"}},
    }]}
    result = run_checks(plan)
    assert result["status"] == "failed"
    assert result["findings"][0]["rule"] == "no_broad_iam_role"


def test_public_cloud_run_invoker_is_medium_not_failing():
    plan = {"resource_changes": [{
        "address": "google_cloud_run_v2_service_iam_member.public_invoker",
        "type": "google_cloud_run_v2_service_iam_member",
        "change": {"actions": ["create"], "after": {"member": "allUsers"}},
    }]}
    result = run_checks(plan)
    assert result["status"] == "passed"
    assert result["findings"][0]["severity"] == "medium"


def test_public_bucket_access_is_high():
    plan = {"resource_changes": [{
        "address": "google_storage_bucket_iam_member.oops",
        "type": "google_storage_bucket_iam_member",
        "change": {"actions": ["create"], "after": {"member": "allUsers"}},
    }]}
    result = run_checks(plan)
    assert result["status"] == "failed"


def test_missing_labels_flagged():
    plan = {"resource_changes": [{
        "address": "google_storage_bucket.example",
        "type": "google_storage_bucket",
        "change": {"actions": ["create"], "after": {"labels": {"platform": "data-platform"}}},
    }]}
    result = run_checks(plan)
    assert result["status"] == "passed"  # missing labels is medium, not blocking
    assert result["findings"][0]["rule"] == "missing_labels"
    assert "owner" in result["findings"][0]["message"]


def test_deletes_and_noops_ignored():
    plan = {"resource_changes": [{
        "address": "google_project_iam_member.gone",
        "type": "google_project_iam_member",
        "change": {"actions": ["delete"], "after": None, "before": {"role": "roles/owner"}},
    }]}
    result = run_checks(plan)
    assert result == {"status": "passed", "findings": []}


def test_clean_plan_passes():
    plan = {"resource_changes": []}
    assert run_checks(plan) == {"status": "passed", "findings": []}


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"{len(tests)} passed")
