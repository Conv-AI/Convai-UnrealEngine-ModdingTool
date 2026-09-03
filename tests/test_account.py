"""Self-checks for the Convai sign-in protocol: no network, no browser, no display.

The browser login is exercised end to end against the real local callback server, with
the browser hand-off and the two Convai endpoints stubbed out.
"""

import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import account
from core.account import AccountSession, AuthError, BrowserLogin


class FakeResponse:
    def __init__(self, status=200, text="", payload=None):
        self.status_code = status
        self.text = text if payload is None else json.dumps(payload)
        self._payload = payload

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def run_with_post(handler, action):
    """Swap requests.post for the duration of one call."""
    original = account.requests.post
    account.requests.post = handler
    try:
        return action()
    finally:
        account.requests.post = original


def test_decrypt():
    """T-AUTH-1: every response shape the decrypt endpoint is known to answer with."""
    # A body that is not JSON is itself the plaintext.
    assert run_with_post(lambda *a, **k: FakeResponse(text="  plain-key  "),
                         lambda: account._decrypt("blob")) == "plain-key"

    # JSON: the first non-empty field, in the documented order.
    assert run_with_post(lambda *a, **k: FakeResponse(payload={"decryptedData": "key-1"}),
                         lambda: account._decrypt("blob")) == "key-1"
    assert run_with_post(lambda *a, **k: FakeResponse(payload={"decryptedData": "", "data": "key-2"}),
                         lambda: account._decrypt("blob")) == "key-2"

    for payload, reason in (({"error": "bad blob"}, "an error field"),
                            ({"unexpected": "x"}, "no readable field")):
        try:
            run_with_post(lambda *a, **k: FakeResponse(payload=payload), lambda: account._decrypt("blob"))
            raise AssertionError(f"{reason} must fail the decrypt")
        except AuthError:
            pass

    # The request body carries the blob under "data", which is what the endpoint reads.
    captured = {}

    def capture(url, json=None, headers=None, timeout=None):
        captured.update(url=url, body=json)
        return FakeResponse(text="key")

    run_with_post(capture, lambda: account._decrypt("the-blob"))
    assert captured["url"] == account.DECRYPT_URL, captured
    assert captured["body"] == {"data": "the-blob"}, captured


def test_verify_key():
    """T-AUTH-2: a rejected key and an unreachable service are different messages."""
    captured = {}

    def ok(url, json=None, headers=None, timeout=None):
        captured.update(url=url, headers=headers)
        return FakeResponse(200)

    run_with_post(ok, lambda: account._verify_key("k"))
    assert captured["url"] == account.VALIDATE_URL
    assert captured["headers"]["CONVAI-API-KEY"] == "k", captured["headers"]

    for status in (400, 401, 403, 422):
        try:
            run_with_post(lambda *a, **k: FakeResponse(status), lambda: account._verify_key("k"))
            raise AssertionError(f"{status} must be reported as a bad key")
        except AuthError as exc:
            assert "couldn't verify" in str(exc).lower(), str(exc)

    for failure in (lambda *a, **k: FakeResponse(500),
                    lambda *a, **k: (_ for _ in ()).throw(account.requests.RequestException())):
        try:
            run_with_post(failure, lambda: account._verify_key("k"))
            raise AssertionError("a service failure must not read as a bad key")
        except AuthError as exc:
            assert "reach convai" in str(exc).lower(), str(exc)


def test_user_info():
    """T-AUTH-3: the name and email field aliases, including the nested shape."""
    assert account._read_user_info(json.dumps({"username": "Alex", "email": "a@b.c"})) == ("Alex", "a@b.c")
    assert account._read_user_info(json.dumps({"user": {"full_name": "Alex Chen", "mail": "a@b.c"}})) == ("Alex Chen", "a@b.c")
    assert account._read_user_info(json.dumps({"display_name": "Alex"})) == ("Alex", "")
    # A blob that is not user info at all must not sink a sign-in.
    assert account._read_user_info("not json") == ("", "")
    assert account._read_user_info(json.dumps(["x"])) == ("", "")


def test_session_round_trip():
    """T-AUTH-4: a session survives a restart and leaves nothing behind on sign-out."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "nested" / "session.json"
        session = AccountSession(path)
        assert not session.is_signed_in
        assert session.restore() is False, "no file is not a session"

        session.adopt("key-123", "Alex Chen", "alex@example.com")
        assert session.is_signed_in and session.display_name == "Alex Chen"

        restored = AccountSession(path)
        assert restored.restore() is True
        assert (restored.api_key, restored.display_name, restored.email) == ("key-123", "Alex Chen", "alex@example.com")

        # An account with no profile name still needs something to show in the app bar.
        AccountSession(path).adopt("key-456", "", "only@example.com")
        anonymous = AccountSession(path)
        anonymous.restore()
        assert anonymous.display_name == "only@example.com"

        anonymous.sign_out()
        assert not anonymous.is_signed_in and not path.exists()
        assert AccountSession(path).restore() is False


def test_browser_callback():
    """T-AUTH-5: the real local server accepts /control and refuses anything else.

    Everything outside the loopback hop is stubbed: no browser opens and neither Convai
    endpoint is called.
    """
    opened = []
    decrypted = []

    original_open = account.webbrowser.open
    original_decrypt = account._decrypt
    original_verify = account._verify_key

    def fake_open(url, new=0):
        opened.append(url)
        threading.Thread(target=callback, args=(url,), daemon=True).start()
        return True

    def callback(login_url):
        port = login_url.rsplit("port=", 1)[1]
        # A request to another path must not end the wait.
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/not-the-callback", timeout=5)
        except urllib.error.HTTPError as exc:
            assert exc.code == 404, exc.code
        urllib.request.urlopen(
            f"http://127.0.0.1:{port}/control?api_key=enc-key&user_info=enc-info", timeout=5).read()

    def fake_decrypt(blob):
        decrypted.append(blob)
        return "plain-key" if blob == "enc-key" else json.dumps({"username": "Alex", "email": "a@b.c"})

    account.webbrowser.open = fake_open
    account._decrypt = fake_decrypt
    account._verify_key = lambda key: None
    try:
        api_key, username, email = BrowserLogin().run()
    finally:
        account.webbrowser.open = original_open
        account._decrypt = original_decrypt
        account._verify_key = original_verify

    assert (api_key, username, email) == ("plain-key", "Alex", "a@b.c")
    assert opened and opened[0].startswith("https://login.convai.com/?ue=true&port="), opened
    assert int(opened[0].rsplit("port=", 1)[1]) in account.CALLBACK_PORTS, opened
    assert decrypted == ["enc-key", "enc-info"], decrypted


def test_browser_cancel():
    """T-AUTH-6: cancelling closes the socket and reports a cancellation, not a timeout."""
    login = BrowserLogin()
    original_open = account.webbrowser.open
    account.webbrowser.open = lambda url, new=0: threading.Timer(0.2, login.cancel).start()
    try:
        login.run()
        raise AssertionError("a cancelled sign-in must raise")
    except AuthError as exc:
        assert "cancelled" in str(exc).lower(), str(exc)
    finally:
        account.webbrowser.open = original_open

    # The port is free again: a second attempt can bind it.
    assert login._server is None


test_decrypt()
test_verify_key()
test_user_info()
test_session_round_trip()
test_browser_callback()
test_browser_cancel()
print("ok")
