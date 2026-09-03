"""Self-checks for the webview host: the transport, not the UI.

No window is created -- the window is a stub that records the JavaScript it was asked to
run, which is the whole of what the host does to the page.
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.host import Host


class FakeWindow:
    """Records run_js calls; optionally refuses them the way a closed window does."""

    def __init__(self, broken=False):
        self.scripts = []
        self.broken = broken
        self.dialogs = []
        self.confirmed = True
        self.destroyed = False

    def run_js(self, script):
        if self.broken:
            raise RuntimeError('window is gone')
        self.scripts.append(script)

    def create_file_dialog(self, dialog_type, **kwargs):
        self.dialogs.append((dialog_type, kwargs))
        return ('C:\\chosen\\path',)

    def create_confirmation_dialog(self, title, message):
        return self.confirmed

    def destroy(self):
        self.destroyed = True


class FakeDispatcher:
    def __init__(self, reply):
        self.reply = reply
        self.seen = []

    def handle(self, envelope):
        self.seen.append(envelope)
        return self.reply


def events_in(scripts):
    """Every event payload the host actually sent, in order."""
    found = []
    for script in scripts:
        for raw in re.findall(r'window\.convai\.onEvent\((.*?)\);', script, re.S):
            found.append(json.loads(raw))
    return found


def drain(host, window, expected, timeout=5.0):
    """Wait for the pump to deliver `expected` events."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(events_in(window.scripts)) >= expected:
            return True
        time.sleep(0.02)
    return False


def make_host(reply=None):
    host = Host()
    host.window = FakeWindow()
    host.dispatcher = FakeDispatcher(reply if reply is not None else {'id': 'x', 'ok': True, 'data': {}})
    return host, host.window


def test_events_wait_for_the_page():
    """T-HOST-1: events emitted before the page answers are held, not dropped.

    A worker can finish before the page has run its bridge module; those events are the
    ones that say the run is over.
    """
    host, window = make_host()
    host.emit({'event': 'log', 'data': {'runId': 'r1', 'line': 'early'}})
    time.sleep(0.2)
    assert window.scripts == [], 'an event reached a page that was not ready'

    # The page calling in is what proves it can receive.
    host.dispatch({'id': '1', 'command': 'boot', 'params': {}})
    assert drain(host, window, 1), window.scripts
    assert events_in(window.scripts)[0]['data']['line'] == 'early'


def test_events_are_batched_in_order():
    """T-HOST-2: a burst of log lines becomes a few calls, not one call per line.

    Every run_js is a blocking round trip into the webview, and a UBT build logs
    thousands of lines.
    """
    host, window = make_host()
    host.dispatch({'id': '1', 'command': 'boot', 'params': {}})
    assert drain(host, window, 0)

    total = 500
    for index in range(total):
        host.emit({'event': 'log', 'data': {'runId': 'r1', 'line': f'line {index}'}})
    assert drain(host, window, total), f'only {len(events_in(window.scripts))} of {total} arrived'

    delivered = events_in(window.scripts)
    assert [event['data']['line'] for event in delivered] == [f'line {index}' for index in range(total)], \
        'the log arrived out of order'
    assert len(window.scripts) < total / 5, f'{len(window.scripts)} calls for {total} events is not batching'
    assert all(event['type'] == 'event' for event in delivered)


def test_close_guard():
    """T-HOST-3: closing warns while a run or a toolchain install is live."""
    host, window = make_host({'id': 'x', 'ok': True, 'data': {'runId': 'run-7'}})
    assert host.on_closing() is True, 'an idle tool must close without a prompt'

    host.dispatch({'id': '1', 'command': 'project.update', 'params': {}})
    window.confirmed = False
    assert host.on_closing() is False, 'a run in progress must be able to cancel the close'
    window.confirmed = True
    assert host.on_closing() is True

    host.emit({'event': 'runFinished', 'data': {'runId': 'run-7', 'ok': True}})
    assert host.on_closing() is True, 'the run ended; nothing left to interrupt'

    # A toolchain install carries no run id but still takes minutes and writes to disk.
    host.emit({'event': 'toolchain', 'data': {'state': 'installing'}})
    window.confirmed = False
    assert host.on_closing() is False
    host.emit({'event': 'toolchain', 'data': {'state': 'done'}})
    assert host.on_closing() is True


def test_dialogs_match_the_dispatcher():
    """T-HOST-4: the injected dialogs take what the dispatcher calls them with."""
    import inspect

    from bridge.dispatcher import Dispatcher

    host, window = make_host()
    parameters = inspect.signature(Dispatcher.__init__).parameters
    assert 'choose_folder' in parameters and 'save_file' in parameters and 'on_quit' in parameters

    assert host.choose_folder('Select the Unreal Engine 5.8 installation folder') == 'C:\\chosen\\path'
    assert host.save_file('Save technical log', 'CityGuide.log') == 'C:\\chosen\\path'
    kinds = [kwargs for _, kwargs in window.dialogs]
    assert kinds[1]['save_filename'] == 'CityGuide.log'
    # Without a filter the save dialog writes an extensionless file that opens in nothing.
    assert kinds[1].get('file_types'), 'the save dialog has no file types'

    host.close()
    assert window.destroyed, 'app.quit did not close the window'


def test_a_closed_window_is_not_an_error():
    """T-HOST-5: a worker still reporting into a window that has gone must not raise."""
    host = Host()
    host.window = FakeWindow(broken=True)
    host.dispatcher = FakeDispatcher({'id': 'x', 'ok': True, 'data': {}})
    host.dispatch({'id': '1', 'command': 'boot', 'params': {}})
    host.emit({'event': 'log', 'data': {'runId': 'r', 'line': 'after the window closed'}})
    time.sleep(0.3)
    assert host.window.scripts == []


def test_a_malformed_command_is_answered():
    """T-HOST-6: the page cannot crash the transport with a bad envelope."""
    host, _ = make_host()
    reply = host.dispatch('not an envelope')
    assert reply['ok'] is False and reply['error']['code'] == 'unknown', reply


test_events_wait_for_the_page()
test_events_are_batched_in_order()
test_close_guard()
test_dialogs_match_the_dispatcher()
test_a_closed_window_is_not_an_error()
test_a_malformed_command_is_answered()
print('ok')
