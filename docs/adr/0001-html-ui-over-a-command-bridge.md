# 1. HTML UI over a command bridge

**Status:** accepted, 2026-09-03

## Context

The first GUI was Tkinter. It reached feature parity and passed its checks, but it could not
reach the look in [ui-design.md](../ui-design.md): Tk has no real rounded corners, no hover
transitions, no grid/flex layout, and its text rendering is a decade behind. Every visual detail
was hand-drawn on canvases and frames.

The same design already existed as an HTML mock, and a spike showed it running unchanged in a
native WebView2 window under pywebview in about thirty lines.

The open question was not *HTML or Tk* but *how the UI reaches the logic*. The Assembly Studio
plugin answers a similar question with a WebSocket bridge, because there the UI is a browser or a
pixel-streamed client in a different process from the UE subsystem — it has no other route in.

## Decision

Adopt the HTML UI, and adopt Assembly Studio's **seam** — a frozen command/event contract with a
transport-agnostic dispatcher — but not its **socket**.

```
gui/webui/          send(cmd) / onEvent()      the UI: HTML, CSS, vanilla JS
    │                        ▲                 knows no Python
    ▼                        │
gui/host.py         window.pywebview.api       the transport adapter
    │                        ▲                 the only file that knows a webview exists
    ▼                        │
bridge/dispatcher.py    reply / emit           commands -> core/, runs on worker threads
bridge/protocol.py                             pure envelopes, step markers, view shapes
    │
    ▼
core/                                          unchanged
```

The transport is an in-process call, because the WebView is hosted by the same Python process
that owns the logic. A local WebSocket would add a port to bind (sign-in already competes for
8080–8083), a Windows Firewall prompt on a signed exe, a reconnect path, and a localhost socket
any process on the machine could use to drive a tool that deletes plugin folders and starts
builds — with no isolation gained, because there is no process boundary to cross.

## Consequences

- A second UI (a UE editor panel, a web dashboard) costs one transport adapter behind the same
  dispatcher. No UI or logic changes.
- `bridge/protocol.py` is pure, so the wire format is unit-testable without a window — the reason
  Assembly Studio split `ConvaiWebBridgeProtocol` out of its subsystem.
- The exe grows by roughly 10–15 MB (pythonnet), and the UI now depends on the WebView2 runtime.
  It ships with Windows 10 and 11, but a machine without it gets no window at all.
- The UI can be opened as a plain file in a browser: `app.js` falls back to a demo transport when
  `window.pywebview` is absent, so design work needs no Python.
- Tkinter, `gui/theme.py`, `gui/components.py`, `gui/shell.py` and `gui/screens/` are deleted once
  the HTML UI reaches parity. Two UIs are not maintained side by side.
