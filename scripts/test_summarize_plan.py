from summarize_plan import summarize, render_markdown


def make_plan(env="dev", changes=None):
    return {
        "variables": {"env": {"value": env}},
        "resource_changes": changes or [],
    }


def rc(address, type_, actions, after=None):
    return {"address": address, "type": type_, "change": {"actions": actions, "after": after or {}}}


def test_groups_by_action():
    plan = make_plan(changes=[
        rc("a", "google_storage_bucket", ["create"]),
        rc("b", "google_cloud_run_v2_service", ["update"]),
        rc("c", "google_secret_manager_secret", ["delete"]),
        rc("d", "google_storage_bucket", ["delete", "create"]),
        rc("e", "google_storage_bucket", ["no-op"]),
    ])
    summary = summarize(plan)
    assert summary["changes"]["create"] == ["a"]
    assert summary["changes"]["update"] == ["b"]
    assert summary["changes"]["delete"] == ["c"]
    assert summary["changes"]["replace"] == ["d"]
    assert "e" not in sum(summary["changes"].values(), [])


def test_iam_changes_tracked():
    plan = make_plan(changes=[
        rc("x", "google_project_iam_member", ["create"], {"role": "roles/logging.logWriter"}),
        rc("y", "google_storage_bucket", ["create"]),
    ])
    summary = summarize(plan)
    assert summary["iam_changes"] == ["x"]


def test_risky_flags_broad_role_and_public_access():
    plan = make_plan(changes=[
        rc("owner", "google_project_iam_member", ["create"], {"role": "roles/owner"}),
        rc("public", "google_storage_bucket_iam_member", ["create"], {"member": "allUsers"}),
        rc("safe", "google_project_iam_member", ["create"], {"role": "roles/logging.logWriter"}),
    ])
    summary = summarize(plan)
    assert set(summary["risky"]) == {"owner", "public"}


def test_environment_read_from_plan_variables():
    assert summarize(make_plan(env="int"))["environment"] == "int"


def test_markdown_renders_sections():
    summary = summarize(make_plan(changes=[rc("a", "google_storage_bucket", ["create"])]))
    md = render_markdown(summary)
    assert "## Terraform Plan Summary" in md
    assert "**Environment:** dev" in md
    assert "1 to create" in md
    assert "- a" in md
    assert "### IAM Changes" in md and "- none" in md


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"{len(tests)} passed")
