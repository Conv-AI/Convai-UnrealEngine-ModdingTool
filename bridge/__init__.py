"""The command bridge: the seam between the UI and the tool.

`protocol` is the wire format and the pure logic behind it; `dispatcher` is the router
over core/. Nothing in here knows what window, if any, is on the other end.
"""

from bridge.dispatcher import BridgeError, Dispatcher
from bridge.protocol import error, event, parse_command, reply

__all__ = ["BridgeError", "Dispatcher", "error", "event", "parse_command", "reply"]
