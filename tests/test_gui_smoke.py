"""Self-checks for the GUI screens and the console-hiding guard.

Plain asserts, no network: run with `python tests/test_gui_smoke.py`. The screens are
built directly; only a display is required, and its absence is a skip.
"""
import ctypes
import json
import logging
import os
import sys
import tempfile
import tkinter as tk

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# The tool's logger writes emoji a cp1252 console cannot encode; quiet it so the
# self-check output is just the assertions.
logging.getLogger("ConvaiTool").disabled = True

from core.config_manager import RemoteConfig, config

config._remote_config = RemoteConfig(
    config={},
    version_data={'current-ue-version': '5.8', 'target-ue-version': '5.8'},
    uploader_config={},
)

import ConvaiModdingTool
import gui.app as gui_app
from core.exceptions import ProjectError
from core.input_manager import InputManager
from core.logger import logger


def make_project(root: str, name: str = 'MyScene_01', engine: str = '5.6') -> str:
    """A project the shelf can read: metadata plus a .uproject.

    The .uproject deliberately does not match the metadata name - renaming one by hand is
    allowed, and the shelf has to read the engine version off whichever file is there.
    """
    project_dir = os.path.join(root, name)
    essentials = os.path.join(project_dir, 'ConvaiEssentials')
    os.makedirs(essentials)
    with open(os.path.join(essentials, 'ModdingMetaData.txt'), 'w', encoding='utf-8') as handle:
        json.dump({'project_name': name, 'asset_type': 'Scene', 'api_key': 'abc',
                   'plugin_name': 'pl'}, handle)
    with open(os.path.join(project_dir, 'Renamed.uproject'), 'w', encoding='utf-8') as handle:
        json.dump({'EngineAssociation': engine}, handle)
    return project_dir


def test_hide_own_console():
    """T-GUI-3: only a console this process owns gets hidden.

    The pids matter, not their count: a double-clicked onefile exe is two attached
    processes (the bootloader and the Python child it spawns), the same count a
    terminal produces.
    """
    shown = []
    me, parent = os.getpid(), os.getppid()

    class Kernel32:
        def GetConsoleWindow(self):
            return 1234

        def GetConsoleProcessList(self, buffer, count):
            buffer[:len(self.pids)] = self.pids
            return len(self.pids)

    class User32:
        def ShowWindow(self, window, flag):
            shown.append((window, flag))

    class Windll:
        kernel32 = Kernel32()
        user32 = User32()

    class FakeCtypes:
        windll = Windll()
        c_uint32 = ctypes.c_uint32

    original_ctypes, original_argv = ConvaiModdingTool.ctypes, sys.argv
    frozen = getattr(sys, 'frozen', None)
    try:
        ConvaiModdingTool.ctypes = FakeCtypes

        Windll.kernel32.pids = [me]
        sys.argv = ['ConvaiModdingTool.exe', '--console']
        ConvaiModdingTool._hide_own_console()
        assert shown == [], "--console must keep the window"

        sys.argv = ['ConvaiModdingTool.exe']
        Windll.kernel32.pids = [me, parent]
        ConvaiModdingTool._hide_own_console()
        assert shown == [], "a terminal's console must stay visible"

        sys.frozen = True
        ConvaiModdingTool._hide_own_console()
        assert shown == [(1234, 0)], "a double-clicked onefile exe must hide its console"

        shown.clear()
        Windll.kernel32.pids = [me, parent, 999]
        ConvaiModdingTool._hide_own_console()
        assert shown == [], "a terminal running the exe must keep its window"

        del sys.frozen
        Windll.kernel32.pids = [me]
        ConvaiModdingTool._hide_own_console()
        assert shown == [(1234, 0)], "an owned console must be hidden"
    finally:
        ConvaiModdingTool.ctypes, sys.argv = original_ctypes, original_argv
        if frozen is None:
            sys.__dict__.pop('frozen', None)
        else:
            sys.frozen = frozen


def test_boot_never_loads_config_on_the_tk_thread():
    """T-GUI-7: building the App must not touch the remote config.

    The first read of `config` fetches it, retrying for minutes when GitHub is
    unreachable. On the Tk thread that is a taskbar entry with no window: the boot
    screen has to be painted before anything reaches for it.
    """
    original_load, original_remote = config.load, config._remote_config
    reads = []

    def explode():
        reads.append('load')
        raise AssertionError('config was read before the boot screen was painted')

    try:
        root = tk.Tk()
    except tk.TclError:
        return None
    root.withdraw()
    try:
        config.load = explode
        config._remote_config = None
        app = gui_app.App(root, '3.0.6', InputManager(REPO_ROOT),
                          {name: (lambda: None) for name in ('create', 'update', 'migrate')})
        app.show_boot()
        # Not root.update(): boot's own `after(50, ...)` is allowed to load the config,
        # on its worker. Only the synchronous build is under test.
        root.update_idletasks()
        assert not reads, reads
    finally:
        config.load, config._remote_config = original_load, original_remote
        # The boot screen leaves a progressbar tick and its own `after(50)` pending;
        # destroying the root under them makes Tcl complain about deleted commands.
        for after_id in root.tk.splitlist(root.tk.call('after', 'info')):
            root.tk.call('after', 'cancel', after_id)
        root.destroy()


def test_step_tracking():
    """T-GUI-12: the run screen's steps follow the lines the flows really log.

    The step titles are the one thing on that screen inferred from the log, so they are
    checked against the real `logger.step` sequence -- nested lines included, since those
    are what a loose matcher trips over.
    """
    from gui.screens.review import MIGRATE_STEPS, UPDATE_STEPS
    from gui.screens.run import _marks, _match, _titles

    flows = {
        'update': (UPDATE_STEPS, [
            'Loading project configuration...', 'Checking project engine version...',
            'Ensuring toolchain for UE 5.8...', 'Updating Convai dependencies...',
            'Removing 1 existing installation(s)...', 'Downloading latest dependencies...',
            'Configuring project assets...',
            'Patching plugin source for engine compatibility...', 'Building project...',
        ]),
        'migrate': (MIGRATE_STEPS, [
            'Getting target Unreal Engine version...', 'Updating selected project...',
            'Checking project engine version...', 'Ensuring toolchain for UE 5.6...',
            'Updating Convai dependencies...', 'Configuring project assets...',
            'Please select the target Unreal Engine 5.8 installation path...',
            'Creating copy of project for migration: MyScene_01_5.8',
            'Updating engine version to 5.8...', 'Setting project engine version to 5.8...',
            'Patching Target.cs files for target UE build compatibility...',
            'Patching plugin source for Unreal Engine 5.8 compatibility...',
            'Building migrated project with Unreal Engine 5.8...',
        ]),
    }

    for name, (steps, lines) in flows.items():
        marks, reached, current = _marks(steps), [], -1
        for line in lines:
            hit = _match(marks, current, line)
            if hit is not None:
                current = hit
                reached.append(hit)
        assert reached == list(range(len(steps))), (name, reached, _titles(steps))


def visible_texts(widget) -> set:
    """Every caption currently laid out under `widget`.

    Unmapped subtrees are skipped: screens keep alternatives built but unpacked (the
    shelf's empty state, a collapsed log), and reading those back would assert that
    something is on screen when it is not.
    """
    found = set()

    def walk(node):
        for child in node.winfo_children():
            if not child.winfo_manager():
                continue
            # tk.Entry answers ['text'] with its textvariable's name, not a caption.
            if not isinstance(child, tk.Entry):
                try:
                    found.add(str(child['text']))
                except tk.TclError:
                    pass
            walk(child)

    walk(widget)
    return {text for text in found if text}


def settle(root, app, timeout_ms: int = 4000) -> None:
    """Run a real main loop until the screen's background work is done.

    `update()` is not enough: a worker's `root.after(0, ...)` is only marshalled while
    the main thread is inside `mainloop`.
    """
    def poll():
        busy = app.running or not getattr(app.screen, 'scanned', True)
        root.after(20, poll) if busy else root.quit()

    root.after(20, poll)
    root.after(timeout_ms, root.quit)
    root.mainloop()
    root.update()


def test_shelf(root, app, project_dir):
    """T-GUI-1: the shelf lists what the scan found and explains each action."""
    app.show_shelf()
    settle(root, app)

    assert [p['name'] for p in app.projects] == ['MyScene_01'], app.projects
    assert app.projects[0]['ue'] == '5.6'
    shelf = app.screen
    assert shelf.selected is not None, 'the first project is selected by default'

    texts = visible_texts(app.shell.page)
    assert 'Projects' in texts and 'PROJECTS (1)' in texts, texts
    assert 'MyScene_01' in texts
    assert 'Update project' in texts and 'Migrate to UE 5.8' in texts, texts
    # Signed out, so the shelf says so rather than failing later.
    assert any('Sign in' in text for text in texts), texts
    assert 'No modding projects here yet' not in texts, 'the empty state showed with a project listed'

    # The search box filters, and a miss offers a way back rather than an empty panel.
    # Only the list is filtered: the inspector keeps the selection it already had.
    shelf.query.set('nothing-matches-this')
    root.update()
    assert 'Clear search' in visible_texts(app.shell.page)
    assert 'MyScene_01' not in visible_texts(shelf.rows_host)
    shelf.query.set('')
    root.update()
    assert 'MyScene_01' in visible_texts(shelf.rows_host)


def test_migrate_reason_is_visible(root, app, tmp):
    """T-GUI-8: an unavailable Migrate keeps its button and states why."""
    on_target = make_project(tmp, name='OnTarget_58', engine='5.8')
    InputManager.find_existing_projects = lambda self: [on_target]
    try:
        app.show_shelf()
        settle(root, app)
        texts = visible_texts(app.shell.page)
        assert 'Migrate to UE 5.8' in texts, texts
        assert any('already uses UE 5.8' in text for text in texts), texts
    finally:
        InputManager.find_existing_projects = lambda self: [os.path.join(tmp, 'MyScene_01')]


def test_new_project(root, app):
    """T-GUI-2: the form validates in place and never asks for the API key."""
    app.show_new_project()
    root.update()
    screen = app.screen
    texts = visible_texts(app.shell.page)
    assert 'New project' in texts and 'Project details' in texts, texts
    assert not any('API key' in text for text in texts), 'the key belongs to the account, not the form'

    screen.name_var.set('')
    screen._continue_details()
    root.update()
    assert 'empty' in screen.name_field.message['text'].lower(), screen.name_field.message['text']

    screen.name_var.set('9lives')
    screen._continue_details()
    root.update()
    assert 'digit' in screen.name_field.message['text'].lower(), screen.name_field.message['text']


def test_review_screens(root, app):
    """T-GUI-9: review states the target and holds the engine question before the run."""
    project = app.projects[0]

    app.show_review('update', project)
    root.update()
    texts = visible_texts(app.shell.page)
    assert f"Update {project['name']}" in texts, texts
    assert any('remain in place' in text for text in texts), texts

    app.show_review('migrate', project)
    root.update()
    texts = visible_texts(app.shell.page)
    assert f"Migrate {project['name']} to UE 5.8" in texts, texts
    assert any('will not be changed' in text.lower() for text in texts), texts
    # No engine is detected in this fixture, so the action has to say so and stay off.
    assert any('was not found' in text or 'Choose folder' in text for text in texts), texts


def test_settings(root, app):
    """T-GUI-10: settings opens as a dark modal with its three sections."""
    dialog = app.open_settings() or app.screen
    root.update()
    windows = [child for child in root.winfo_children() if isinstance(child, tk.Toplevel)]
    assert len(windows) == 1, windows
    texts = visible_texts(windows[0])
    assert 'Unreal Engine' in texts and 'Packaging' in texts and 'About' in texts, texts
    assert any('Close' == text for text in texts), texts
    windows[0].destroy()
    root.update()


def drive_run(root, app, title, flow, folder, steps):
    """Run one flow on the real worker and return once the screen has settled."""
    tool_logger = logger.logger
    handlers, disabled = tool_logger.handlers[:], tool_logger.disabled
    # Only the queue handler stays: the console one cannot encode the emoji prefix
    # when stdout is a pipe.
    tool_logger.handlers.clear()
    tool_logger.disabled = False
    try:
        app.show_run(title, flow, folder, steps=steps)
        settle(root, app, timeout_ms=6000)
    finally:
        tool_logger.handlers[:], tool_logger.disabled = handlers, disabled


def test_run_flow(root, app, folder):
    """T-GUI-4: a real worker's log reaches the pane and the run ends on the folder button."""
    def flow() -> str:
        logger.info('worker line')
        return '# notes'

    drive_run(root, app, 'Updating MyScene_01', flow, folder, ['Validating Unreal Engine'])

    screen = app.screen
    assert not app.running and app.shell.navigation_enabled, 'the chrome stayed locked after the run'
    assert 'worker line' in screen.log_text.get('1.0', 'end'), 'the worker log never reached the pane'
    assert screen.log_handler is None, 'the queue handler outlived the run'
    texts = visible_texts(app.shell.page)
    assert 'Open project folder' in texts and 'Back to projects' in texts, texts
    assert any('is ready' in text for text in texts), texts
    assert any('What changed' in text for text in texts), texts


def test_failed_run(root, app, folder):
    """T-GUI-6: a flow that refuses ends on a failure, and offers no folder to open.

    The flows used to report a refusal by logging and returning, which the run screen
    reads as success: an unsupported engine finished on a green Done.
    """
    def flow() -> str:
        logger.info('worker line')
        raise ProjectError('Unreal Engine 5.4 does not meet the modding project requirements')

    drive_run(root, app, 'Updating MyScene_01', flow, folder, ['Validating Unreal Engine'])

    texts = visible_texts(app.shell.page)
    assert app.screen.log_handler is None, 'the queue handler outlived the run'
    assert 'Open project folder' not in texts, 'a failed run must not offer the folder it never filled'
    assert any('Unreal Engine 5.4 does not meet' in text for text in texts), texts
    assert 'Back to projects' in texts, texts


def test_blocked_screens(root, app):
    """T-GUI-5: an unreachable config and an outdated build are different screens."""
    app.show_blocked('Failed to load config after 5 attempts.')
    root.update()
    texts = visible_texts(app.shell.page)
    assert "We couldn't start the tool" in texts, texts
    assert 'Download latest version' not in texts, "an unreachable GitHub is not fixed by downloading the tool"
    assert not app.shell.navigation_enabled, 'a blocked start must not offer the shelf'

    app.show_blocked('outdated', outdated=True, installed='3.0.6', required='3.1.0')
    root.update()
    texts = visible_texts(app.shell.page)
    assert 'A newer version is required' in texts and 'Download latest version' in texts, texts
    assert 'v3.0.6' in texts and 'v3.1.0' in texts, texts


def wait_until(root, predicate, timeout_ms: int = 3000) -> bool:
    """Pump a real main loop until `predicate` holds. Returns whether it did.

    The modal's worker reports back through `root.after`, which only runs inside
    `mainloop` -- and unlike a run, nothing on the App marks it as busy.
    """
    done = []

    def poll():
        if predicate():
            done.append(True)
            root.quit()
        else:
            root.after(20, poll)

    root.after(0, poll)
    root.after(timeout_ms, root.quit)
    root.mainloop()
    root.update()
    return bool(done)


def test_engine_choice_survives_a_run(root, app, tmp):
    """T-GUI-15: a chosen engine outlives InputManager.reset(), and a dead path is not
    reported as ready.

    `reset()` clears the per-run answers before every create and every review confirm,
    and it clears the target engine among them -- so a choice made in Settings cannot
    live there. A remembered path also has to be re-checked: an installation can be
    removed between runs, and the shelf decides from this whether Migrate is offered.
    """
    engine = os.path.join(tmp, 'UE_5.8')
    os.makedirs(engine, exist_ok=True)
    original_valid = gui_app.App.is_valid_engine
    try:
        gui_app.App.is_valid_engine = staticmethod(lambda path, version_type: bool(path) and os.path.isdir(path))

        app.set_engine_path('target', engine)
        assert app.engine_path('target') == engine

        app.input_manager.reset()
        assert app.engine_path('target') == engine, 'the Settings choice did not survive a run'

        # The folder goes away; nothing detected in this fixture, so it must read missing.
        os.rmdir(engine)
        assert app.engine_path('target') is None, 'a deleted installation still read as ready'
    finally:
        gui_app.App.is_valid_engine = original_valid
        app.engine_overrides.clear()
        app.input_manager.reset()


def test_no_horizontal_overflow(root, app):
    """T-GUI-14: no screen is wider than the window at 920x640 or 1120x760.

    The page host scrolls vertically only, so content wider than the canvas is simply
    unreachable. Layout is not real until Tk has mapped the window, so this one parks it
    off-screen rather than measuring a withdrawn root.
    """
    project = app.projects[0] if app.projects else None
    overflows = []
    root.deiconify()
    try:
        for width, height in ((920, 640), (1120, 760)):
            for label, show in (('shelf', app.show_shelf),
                                ('new project', app.show_new_project),
                                ('blocked', lambda: app.show_blocked('A start-up check failed.')),
                                ('review update', lambda: project and app.show_review('update', project)),
                                ('review migrate', lambda: project and app.show_review('migrate', project))):
                root.geometry(f'{width}x{height}+3000+3000')
                root.update()
                show()
                settle(root, app, timeout_ms=2000)
                spare = app.shell.canvas.winfo_width() - app.shell.page.winfo_reqwidth()
                if spare < 0:
                    overflows.append((label, width, -spare))
    finally:
        root.withdraw()
    assert not overflows, overflows


def test_sign_in_modal(root, app):
    """T-GUI-13: the key path reports a bad key and an outage differently, and only a
    verified key signs the user in."""
    from gui import account as account_module
    from gui.account import AuthError, SignInModal

    succeeded = []
    modal = SignInModal(app, on_success=lambda: succeeded.append(True))
    modal.open()
    root.update()
    try:
        texts = visible_texts(modal.window)
        assert 'Continue with Google' in texts and 'Use an API key instead' in texts, texts
        assert 'Not now' in texts, texts

        modal._show_api_key()
        root.update()
        # An empty field is caught before any request goes out.
        modal._submit_key()
        root.update()
        assert 'Enter your Convai API key' in modal.key_field.message['text']
        assert not succeeded

        original_verify = account_module._verify_key
        try:
            for message, expected in (("We couldn't verify that API key. Check it and try again.", 'verify'),
                                      ('Couldn\'t reach Convai. Try again.', 'reach')):
                account_module._verify_key = lambda key, text=message: (_ for _ in ()).throw(AuthError(text))
                modal.key_field.variable.set('a-key')
                modal._submit_key()
                assert wait_until(root, lambda: expected in modal.key_field.message['text'].lower()),                     modal.key_field.message['text']
                assert str(modal.key_field.entry['state']) == 'normal', 'the field stayed disabled after a failure'
                assert not succeeded, 'a rejected key must not sign anyone in'
                assert not app.account.is_signed_in

            account_module._verify_key = lambda key: None
            modal.key_field.variable.set('good-key')
            modal._submit_key()
            assert wait_until(root, lambda: modal.window is None), 'the sign-in never completed'
        finally:
            account_module._verify_key = original_verify

        assert succeeded == [True], 'a verified key did not complete the sign-in'
        assert app.account.api_key == 'good-key'
        assert modal.window is None, 'the modal stayed open after signing in'
    finally:
        if modal.window is not None:
            modal.dismiss()
        app.account.sign_out()
        app.refresh_account()
        root.update()


def test_account_states(root, app):
    """T-GUI-11: the app bar and the shelf follow the session, and never show the key."""
    app.account.adopt('secret-key-value', 'Alex Chen', 'alex@example.com')
    try:
        app.refresh_account()
        app.show_shelf()
        settle(root, app)
        assert 'Alex' in app.shell.account_btn['text'], app.shell.account_btn['text']

        texts = visible_texts(app.shell.page) | {app.shell.account_btn['text']}
        assert not any('secret-key-value' in text for text in texts), 'the API key reached the screen'
        assert 'Sign in to create or manage Convai projects.' not in texts, texts
    finally:
        app.account.sign_out()
        app.refresh_account()


original_find = InputManager.find_existing_projects
original_detect = InputManager.__dict__['detect_engine_path']
try:
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = make_project(tmp)
        InputManager.find_existing_projects = lambda self: [project_dir]
        InputManager.detect_engine_path = staticmethod(lambda version_type='current': None)

        test_hide_own_console()
        test_step_tracking()
        test_boot_never_loads_config_on_the_tk_thread()

        try:
            root = tk.Tk()
        except tk.TclError:
            print('skipped: no display')
            sys.exit(0)

        root.withdraw()
        try:
            flows = {name: (lambda: None) for name in ('create', 'update', 'migrate')}
            session = os.path.join(tmp, 'session.json')
            app = gui_app.App(root, ConvaiModdingTool.TOOL_VERSION, InputManager(tmp), flows)
            # A self-check must not read or write the developer's real session file.
            app.account.path = __import__('pathlib').Path(session)

            test_shelf(root, app, project_dir)
            test_migrate_reason_is_visible(root, app, tmp)
            test_new_project(root, app)
            test_review_screens(root, app)
            test_settings(root, app)
            test_run_flow(root, app, project_dir)
            test_failed_run(root, app, project_dir)
            test_blocked_screens(root, app)
            test_sign_in_modal(root, app)
            test_account_states(root, app)
            test_engine_choice_survives_a_run(root, app, tmp)
            test_no_horizontal_overflow(root, app)
        finally:
            root.destroy()
finally:
    InputManager.find_existing_projects = original_find
    InputManager.detect_engine_path = original_detect

print('ok')
