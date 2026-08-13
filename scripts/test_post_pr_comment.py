import subprocess
import tempfile

from github_app import b64url, make_jwt, sign_rs256
from post_pr_comment import render_comment


def gen_test_key() -> bytes:
    return subprocess.run(
        ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048"],
        capture_output=True, check=True,
    ).stdout


def test_b64url_has_no_padding_or_unsafe_chars():
    encoded = b64url(b"\xff\xfe\xfd" * 10)
    assert "=" not in encoded and "+" not in encoded and "/" not in encoded


def test_sign_rs256_verifies_with_matching_public_key():
    key_pem = gen_test_key()
    signing_input = b"header.payload"
    signature = sign_rs256(signing_input, key_pem)

    with tempfile.NamedTemporaryFile(suffix=".pem") as key_file, \
         tempfile.NamedTemporaryFile(suffix=".sig") as sig_file:
        key_file.write(key_pem)
        key_file.flush()
        sig_file.write(signature)
        sig_file.flush()
        verify = subprocess.run(
            ["openssl", "dgst", "-sha256", "-verify", key_file.name, "-signature", sig_file.name],
            input=signing_input, capture_output=True,
        )
    assert verify.returncode == 0


def test_make_jwt_has_three_dot_separated_parts():
    jwt = make_jwt(gen_test_key())
    assert jwt.count(".") == 2


def test_render_comment_failed_status():
    comment = render_comment({"status": "failed"}, "**Risk level:** High")
    assert "❌ failed" in comment
    assert "**Risk level:** High" in comment


def test_render_comment_passed_status():
    comment = render_comment({"status": "passed"}, "**Risk level:** Low")
    assert "✅ passed" in comment
    assert "**Risk level:** Low" in comment


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"{len(tests)} passed")
