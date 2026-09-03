"""Self-checks for the GUI screens and the console-hiding guard.

Plain asserts, no network and no worker threads: run with `python tests/test_gui_smoke.py`.
The screens are built directly; only a display is required, and its absence is a skip.
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


def make_project(root: str) -> str:
    """A project the shelf can read: metadata plus a .uproject.

    The .uproject deliberately does not match the metadata name - renaming one by hand is
    allowed, and the shelf has to read the engine version off whichever file is there.
    """
    project_dir = os.path.join(root, 'MyScene_01')
    essentials = os.path.join(project_dir, 'ConvaiEssentials')
    os.makedirs(essentials)
    with open(os.path.join(essentials, 'ModdingMetaData.txt'), 'w', encoding='utf-8') as handle:
        json.dump({'project_name': 'P', 'asset_type': 'Scene', 'api_key': 'abc'}, handle)
    with open(os.path.join(project_dir, 'Renamed.uproject'), 'w', encoding='utf-8') as handle:
        json.dump({'EngineAssociation': '5.6'}, handle)
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


def screen_texts(app) -> set:
    """Every caption on the current screen; frames and other option-less widgets are skipped."""
    def walk(widget):
        for child in widget.winfo_children():
            try:
                yield str(child['text'])
            except tk.TclError:
                pass
            yield from walk(child)

    return set(walk(app.content))


def test_screens(root: tk.Tk, project_dir: str):
    """T-GUI-1: every screen builds with fake data and no threads."""
    flows = {name: lambda: None for name in ('create', 'update', 'migrate')}
    app = gui_app.App(root, ConvaiModdingTool.TOOL_VERSION, InputManager(os.path.dirname(project_dir)), flows)

    app.show_shelf()
    root.update()
    rows = app.tree.get_children()
    assert len(rows) == 1, rows
    assert tuple(app.tree.item(rows[0], 'values')) == ('MyScene_01', '5.6', 'Scene')
    assert str(app.update_btn['state']) == 'disabled', "nothing is selected yet"

    app.open_settings()
    root.update()
    settings = [child for child in root.winfo_children() if isinstance(child, tk.Toplevel)]
    assert len(settings) == 1, settings
    settings[0].destroy()

    app.show_new_project()
    root.update()
    assert 'MyScene_01' in app.reuse_combo['values']
    app._on_create()
    assert 'empty' in app.form_error['text'].lower(), app.form_error['text']

    app.show_blocked('Failed to load config after 5 attempts.')
    root.update()
    texts = screen_texts(app)
    assert 'Cannot start' in texts, texts
    assert 'Download' not in texts, "an unreachable GitHub is not fixed by downloading the tool"

    app.show_blocked('Your version is outdated. Please update to continue.', outdated=True)
    root.update()
    texts = screen_texts(app)
    assert 'Update required' in texts and 'Download' in texts, texts

    app._show(lambda parent: app._build_run(parent, 'Updating MyScene_01'))
    root.update()
    app._finish_run(True, notes='# notes\n\nThe convenience pack moved into the plugin.')
    root.update()
    assert str(app.back_btn['state']) == 'normal'
    assert app.run_status['text'] == 'Done'
    return app


def drive_run(root: tk.Tk, app, flow, folder: str):
    """Run one flow on the real worker and return once the screen has settled."""
    tool_logger = logger.logger
    handlers, disabled = tool_logger.handlers[:], tool_logger.disabled
    # Only the queue handler stays: the console one cannot encode the emoji prefix
    # when stdout is a pipe.
    tool_logger.handlers.clear()
    tool_logger.disabled = False
    def poll() -> None:
        if app.running:
            root.after(20, poll)
        else:
            root.quit()

    try:
        app.show_run('Creating X', flow, folder)
        # A real main loop, not update(): the worker's root.after() call is only
        # marshalled to the Tk thread while the main thread sits in mainloop.
        root.after(20, poll)
        root.after(5000, root.quit)
        root.mainloop()
    finally:
        tool_logger.handlers[:], tool_logger.disabled = handlers, disabled


def test_run_flow(root: tk.Tk, app, folder: str):
    """T-GUI-4: a real worker's log reaches the pane and the run ends on the folder button."""
    def flow() -> str:
        logger.info('worker line')
        return '# notes'

    drive_run(root, app, flow, folder)

    assert app.run_status['text'] == 'Done', app.run_status['text']
    assert 'worker line' in app.log_text.get('1.0', 'end'), 'the worker log never reached the pane'
    assert app.log_handler is None, 'the queue handler outlived the run'
    texts = screen_texts(app)
    assert 'Open folder' in texts and '# notes' in texts, texts


def test_failed_run(root: tk.Tk, app, folder: str):
    """T-GUI-6: a flow that refuses ends on Failed, and offers no folder to open.

    The flows used to report a refusal by logging and returning, which this screen reads
    as success: an unsupported engine finished on a green Done.
    """
    def flow() -> str:
        logger.info('worker line')
        raise ProjectError('Unreal Engine 5.4 does not meet the modding project requirements')

    drive_run(root, app, flow, folder)

    assert app.run_status['text'] == 'Failed: Unreal Engine 5.4 does not meet the modding project requirements', \
        app.run_status['text']
    assert app.log_handler is None, 'the queue handler outlived the run'
    texts = screen_texts(app)
    assert 'Open folder' not in texts, 'a failed run must not offer the folder it never filled'


def test_engine_dialog(app, folder: str):
    """T-GUI-5: a registry miss falls back to the folder dialog and rejects a wrong pick."""
    errors = []
    original_ask, original_error = gui_app.filedialog.askdirectory, gui_app.messagebox.showerror
    try:
        gui_app.filedialog.askdirectory = lambda **kwargs: ''
        gui_app.messagebox.showerror = lambda title, message: errors.append(message)
        assert app._resolve_engine('current') is None, 'a cancelled dialog is not a path'
        assert errors == [], errors

        gui_app.filedialog.askdirectory = lambda **kwargs: folder
        assert app._resolve_engine('current') is None, 'a folder without an engine is not a path'
        assert errors and 'Unreal Engine' in errors[0], errors
    finally:
        gui_app.filedialog.askdirectory, gui_app.messagebox.showerror = original_ask, original_error


# Read through __dict__: attribute access unwraps the staticmethod, and restoring the
# bare function would leave it bound to the instance.
original_find = InputManager.find_existing_projects
original_detect = InputManager.__dict__['detect_engine_path']
try:
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = make_project(tmp)
        InputManager.find_existing_projects = lambda self: [project_dir]
        InputManager.detect_engine_path = staticmethod(lambda version_type='current': None)

        test_hide_own_console()

        try:
            root = tk.Tk()
        except tk.TclError:
            print('skipped: no display')
            sys.exit(0)

        root.withdraw()
        try:
            app = test_screens(root, project_dir)
            test_run_flow(root, app, project_dir)
            test_failed_run(root, app, project_dir)
            test_engine_dialog(app, project_dir)
        finally:
            root.destroy()
finally:
    InputManager.find_existing_projects = original_find
    InputManager.detect_engine_path = original_detect

print('ok')
