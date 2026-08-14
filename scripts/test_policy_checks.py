from policy_checks import run_checks


def test_broad_role_flagged():
    plan = {"resource_changes": [{
        "address": "module.data_platform.google_project_iam_member.bad",
        "type": "google_project_iam_member",
        "change": {"actions": ["create"], "after": {"role": "roles/owner"}},
    }]}
    result = run_checks(plan)
    assert result["status"] == "failed"
    assert result["findings"][0]["rule"] == "no_broad_iam_role"


def test_public_cloud_run_invoker_is_medium_not_failing():
    plan = {"resource_changes": [{
        "address": "module.agent_hosting.google_cloud_run_v2_service_iam_member.public_invoker",
        "type": "google_cloud_run_v2_service_iam_member",
        "change": {"actions": ["create"], "after": {"member": "allUsers"}},
    }]}
    result = run_checks(plan)
    assert result["status"] == "passed"
    assert result["findings"][0]["severity"] == "medium"


def test_public_bucket_access_is_high():
    plan = {"resource_changes": [{
        "address": "module.data_platform.google_storage_bucket_iam_member.oops",
        "type": "google_storage_bucket_iam_member",
        "change": {"actions": ["create"], "after": {"member": "allUsers"}},
    }]}
    result = run_checks(plan)
    assert result["status"] == "failed"


def test_missing_labels_flagged():
    plan = {"resource_changes": [{
        "address": "module.data_platform.google_storage_bucket.example",
        "type": "google_storage_bucket",
        "change": {"actions": ["create"], "after": {"labels": {"platform": "data-platform"}}},
    }]}
    result = run_checks(plan)
    assert result["status"] == "passed"  # missing labels is medium, not blocking
    assert result["findings"][0]["rule"] == "missing_labels"
    assert "owner" in result["findings"][0]["message"]


def test_deletes_and_noops_ignored():
    plan = {"resource_changes": [{
        "address": "module.data_platform.google_project_iam_member.gone",
        "type": "google_project_iam_member",
        "change": {"actions": ["delete"], "after": None, "before": {"role": "roles/owner"}},
    }]}
    result = run_checks(plan)
    assert result == {"status": "passed", "findings": []}


def test_clean_plan_passes():
    plan = {"resource_changes": []}
    assert run_checks(plan) == {"status": "passed", "findings": []}


def test_direct_resource_flagged():
    plan = {"resource_changes": [{
        "address": "google_storage_bucket.oops",
        "type": "google_storage_bucket",
        "change": {"actions": ["create"], "after": {"name": "oops"}},
    }]}
    result = run_checks(plan)
    assert result["status"] == "failed"
    assert any(f["rule"] == "direct_resource_instead_of_module" for f in result["findings"])


def test_module_scoped_resource_not_flagged():
    plan = {"resource_changes": [{
        "address": "module.data_platform.google_storage_bucket.buckets[\"raw-data\"]",
        "type": "google_storage_bucket",
        "change": {"actions": ["create"], "after": {"name": "raw-data"}},
    }]}
    result = run_checks(plan)
    assert not any(f["rule"] == "direct_resource_instead_of_module" for f in result["findings"])


def test_data_source_not_flagged_as_direct_resource():
    plan = {"resource_changes": [{
        "address": "data.google_project.current",
        "type": "google_project",
        "mode": "data",
        "change": {"actions": ["read"], "after": {}},
    }]}
    assert run_checks(plan) == {"status": "passed", "findings": []}


def test_dataset_name_not_snake_case_flagged():
    plan = {"resource_changes": [{
        "address": "module.data_platform.google_bigquery_dataset.managed_datasets[\"x\"]",
        "type": "google_bigquery_dataset",
        "change": {"actions": ["create"], "after": {"dataset_id": "BadName"}},
    }]}
    result = run_checks(plan)
    assert result["status"] == "passed"  # naming convention is medium, not blocking
    assert any(f["rule"] == "naming_convention" for f in result["findings"])


def test_email_in_resource_name_is_high():
    plan = {"resource_changes": [{
        "address": "module.data_platform.google_storage_bucket.buckets[\"leak\"]",
        "type": "google_storage_bucket",
        "change": {"actions": ["create"], "after": {"name": "someone@example.com-bucket"}},
    }]}
    result = run_checks(plan)
    assert result["status"] == "failed"
    assert any(f["rule"] == "naming_convention" and "email" in f["message"] for f in result["findings"])


def test_email_in_iam_member_not_flagged():
    plan = {"resource_changes": [{
        "address": "module.data_platform.google_project_iam_member.project[\"x\"]",
        "type": "google_project_iam_member",
        "change": {"actions": ["create"], "after": {"role": "roles/viewer", "member": "user:someone@example.com"}},
    }]}
    assert run_checks(plan) == {"status": "passed", "findings": []}


def test_yaml_schema_type_mismatch_flagged():
    plan = {"resource_changes": []}
    yaml_data = {"buckets": ["not", "a", "dict"]}
    result = run_checks(plan, yaml_data)
    assert result["status"] == "failed"
    assert result["findings"][0]["rule"] == "invalid_yaml_schema"


def test_dataset_with_empty_environments_flagged():
    plan = {"resource_changes": []}
    yaml_data = {"managed_datasets": {"orphan": {"location": "europe-west1", "environments": []}}}
    result = run_checks(plan, yaml_data)
    assert result["status"] == "passed"  # missing env config is medium, not blocking
    assert result["findings"][0]["rule"] == "missing_environment_configuration"


def test_bucket_with_unsupported_environment_flagged():
    plan = {"resource_changes": []}
    yaml_data = {"buckets": {"raw-data": {"location": "europe-west1", "environments": ["prod"]}}}
    result = run_checks(plan, yaml_data)
    assert result["findings"][0]["resource"] == "raw-data"


def test_no_yaml_data_skips_yaml_checks():
    plan = {"resource_changes": []}
    assert run_checks(plan, None) == {"status": "passed", "findings": []}


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"{len(tests)} passed")
