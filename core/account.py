"""Convai sign-in: the session and the browser login.

The protocol is the one the Convai UE editor plugin uses, so a user who has signed in
there recognises this flow:

    1. bind a local HTTP server on the first free port of 8080..8083
    2. open https://login.convai.com/?ue=true&port=<port> in the browser
    3. the web app calls back GET /control?api_key=<blob>&user_info=<blob>
    4. POST each blob to https://login.convai.com/api/decrypt to get the plaintext
    5. verify the key with POST https://api.convai.com/user/user-api-usage

Google itself is never contacted by this tool: login.convai.com runs the consent screen
and hands back an already-encrypted Convai key.

Two deliberate differences from the plugin: the listener binds 127.0.0.1 rather than
every interface, and the wait has a real timeout. The callback carries no state or
nonce -- the login page correlates only by port -- so keeping the socket off the LAN and
short-lived is the whole of the defence available here.

Nothing here touches a UI toolkit: the browser wait blocks, so a caller runs it on a
worker and reports back however it likes.
"""

from __future__ import annotations

import http.server
import json
import os
import threading
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Callable, Optional

import requests


LOGIN_URL = "https://login.convai.com/?ue=true&port={port}"
DECRYPT_URL = "https://login.convai.com/api/decrypt"
VALIDATE_URL = "https://api.convai.com/user/user-api-usage"
DASHBOARD_URL = "https://convai.com/"

# The login page redirects to whichever of these it was told about, so the set is fixed
# on the server side and cannot be widened here.
CALLBACK_PORTS = (8080, 8081, 8082, 8083)
CALLBACK_PATH = "/control"
CALLBACK_TIMEOUT = 300.0
REQUEST_TIMEOUT = 30.0

# The plugin's decrypt endpoint answers in one of several shapes; this is its order of
# preference, kept identical so both tools read the same response the same way.
_DECRYPTED_FIELDS = ("decryptedData", "decrypted_data", "data", "decrypted", "result", "api_key", "apiKey", "key")
_USERNAME_FIELDS = ("username", "user_name", "display_name", "name", "full_name")
_EMAIL_FIELDS = ("email", "user_email", "mail")

SESSION_PATH = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ConvaiModdingTool" / "session.json"

_SUCCESS_PAGE = b"""<!doctype html><html><head><meta charset="utf-8">
<title>Signed in</title></head>
<body style="background:#07100A;color:#EEF7F0;font:16px 'Segoe UI',sans-serif;text-align:center;padding:80px">
<h2 style="color:#35D878">You're signed in</h2>
<p>Return to the Convai Modding Tool to continue.</p></body></html>"""

_FAILURE_PAGE = b"""<!doctype html><html><head><meta charset="utf-8">
<title>Sign-in failed</title></head>
<body style="background:#07100A;color:#EEF7F0;font:16px 'Segoe UI',sans-serif;text-align:center;padding:80px">
<h2 style="color:#F0BD45">Sign-in did not complete</h2>
<p>Return to the Convai Modding Tool and try again.</p></body></html>"""


class AuthError(Exception):
    """A sign-in that failed for a reason worth showing the user."""

    def __init__(self, message: str, recoverable: bool = True):
        super().__init__(message)
        self.recoverable = recoverable


def _decrypt(blob: str) -> str:
    """Exchange one callback blob for its plaintext."""
    response = requests.post(
        DECRYPT_URL, json={"data": blob},
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=REQUEST_TIMEOUT)
    if not response.ok:
        raise AuthError("Couldn't reach Convai. Try again.")

    body = response.text.strip()
    # A non-JSON body is itself the plaintext; only a JSON one is unwrapped.
    if not body.startswith("{"):
        return body

    payload = response.json()
    if payload.get("error"):
        raise AuthError("Convai could not complete the sign-in. Try again.")
    for field in _DECRYPTED_FIELDS:
        value = payload.get(field)
        if value:
            return value if isinstance(value, str) else json.dumps(value)
    raise AuthError("Convai returned a sign-in response this tool could not read.")


def _verify_key(api_key: str) -> None:
    """Raise unless Convai accepts the key. Distinguishes a bad key from an outage."""
    try:
        response = requests.post(
            VALIDATE_URL, json={},
            headers={"CONVAI-API-KEY": api_key, "Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        raise AuthError("Couldn't reach Convai. Try again.")

    if response.status_code in (401, 403, 422) or response.status_code == 400:
        raise AuthError("We couldn't verify that API key. Check it and try again.")
    if not response.ok:
        raise AuthError("Couldn't reach Convai. Try again.")


def _read_user_info(raw: str) -> tuple[str, str]:
    """(username, email) out of the decrypted user-info blob; both may be empty."""
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return "", ""
    if isinstance(payload, dict) and isinstance(payload.get("user"), dict):
        payload = payload["user"]
    if not isinstance(payload, dict):
        return "", ""
    username = next((str(payload[f]) for f in _USERNAME_FIELDS if payload.get(f)), "")
    email = next((str(payload[f]) for f in _EMAIL_FIELDS if payload.get(f)), "")
    return username, email


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Answers exactly one route; anything else is a 404."""

    result: dict = {}
    done: Optional[threading.Event] = None

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's spelling
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != CALLBACK_PATH:
            self.send_error(404)
            return

        query = urllib.parse.parse_qs(parsed.query)
        api_key = (query.get("api_key") or [""])[0]
        page = _SUCCESS_PAGE if api_key else _FAILURE_PAGE

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

        if api_key:
            type(self).result.update(api_key=api_key, user_info=(query.get("user_info") or [""])[0])
            if type(self).done is not None:
                type(self).done.set()

    def log_message(self, *args) -> None:
        """The tool has its own logger; the default writes to stderr."""


class BrowserLogin:
    """One browser sign-in attempt, cancellable from the UI thread."""

    def __init__(self):
        self._server: Optional[http.server.HTTPServer] = None
        self._cancelled = threading.Event()
        self._done = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()
        self._done.set()

    def run(self) -> tuple[str, str, str]:
        """Blocking: returns (api_key, username, email). Call it on a worker."""
        handler = type("_Handler", (_CallbackHandler,), {"result": {}, "done": self._done})
        server = None
        for port in CALLBACK_PORTS:
            try:
                server = http.server.HTTPServer(("127.0.0.1", port), handler)
                break
            except OSError:
                continue
        if server is None:
            raise AuthError(
                "Ports 8080-8083 are all in use, so the browser cannot return the sign-in. "
                "Close whatever is using them and try again.")

        self._server = server
        server.timeout = 0.5
        try:
            webbrowser.open(LOGIN_URL.format(port=server.server_port), new=2)

            waited = 0.0
            while not self._done.is_set() and waited < CALLBACK_TIMEOUT:
                server.handle_request()  # returns after `timeout` even with no request
                waited += server.timeout
        finally:
            server.server_close()
            self._server = None

        if self._cancelled.is_set():
            raise AuthError("Sign-in cancelled.")
        if not handler.result.get("api_key"):
            raise AuthError("The browser sign-in timed out. Try again.")

        api_key = _decrypt(handler.result["api_key"])
        username, email = "", ""
        if handler.result.get("user_info"):
            # Losing the display name is not worth failing a sign-in that otherwise
            # produced a working key.
            try:
                username, email = _read_user_info(_decrypt(handler.result["user_info"]))
            except AuthError:
                pass

        _verify_key(api_key)
        return api_key, username, email


class AccountSession:
    """The signed-in account, and the only thing that persists it.

    Token and cache mechanics stay in here: no screen ever sees an expiry, a raw
    response or the file path.
    """

    def __init__(self, path: Path = SESSION_PATH):
        self.path = path
        self.api_key: Optional[str] = None
        self.display_name: Optional[str] = None
        self.email: str = ""

    @property
    def is_signed_in(self) -> bool:
        return bool(self.api_key)

    def restore(self) -> bool:
        """Reload a stored session. Never touches the network, so boot cannot hang."""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not data.get("api_key"):
            return False
        self.api_key = data["api_key"]
        self.display_name = data.get("username") or data.get("email") or "Convai account"
        self.email = data.get("email", "")
        return True

    def adopt(self, api_key: str, username: str = "", email: str = "") -> None:
        self.api_key = api_key
        self.display_name = username or email or "Convai account"
        self.email = email
        self._save()

    def sign_out(self) -> None:
        self.api_key = None
        self.display_name = None
        self.email = ""
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({
                "api_key": self.api_key,
                "username": self.display_name,
                "email": self.email,
            }), encoding="utf-8")
        except OSError:
            # A session that cannot be cached still works for this run.
            pass
