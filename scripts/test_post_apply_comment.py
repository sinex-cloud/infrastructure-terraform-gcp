from post_apply_comment import render_comment


def test_render_comment_success():
    comment = render_comment(0, "Apply complete! Resources: 1 added.")
    assert "✅ succeeded" in comment
    assert "Apply complete! Resources: 1 added." in comment


def test_render_comment_failure():
    comment = render_comment(1, "Error: something broke")
    assert "❌ failed" in comment
    assert "Error: something broke" in comment


def test_render_comment_truncates_long_output():
    output = "x" * 10000
    comment = render_comment(0, output)
    assert "truncated" in comment
    assert len(comment) < 6000


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"{len(tests)} passed")
