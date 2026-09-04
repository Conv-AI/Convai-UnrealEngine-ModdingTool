"""Self-checks for the V4 migration path: notes, INI repoint, prompt-free input, build.

Plain asserts, no network: run with `python tests/test_migration.py`.
"""
import builtins
import io
import json
import logging
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from core.config_manager import RemoteConfig, config

# Seed the config the way the GUI's boot worker would, but from the file this repo ships
# so the names under test are the real ones and nothing touches the network.
with open(os.path.join(REPO_ROOT, 'resources', 'modding_tool_config.json'), encoding='utf-8') as handle:
    config._remote_config = RemoteConfig(
        config=json.load(handle),
        version_data={'current-ue-version': '5.8', 'target-ue-version': '5.8'},
        uploader_config={},
    )

# The tool's logger writes emoji that a cp1252 console cannot encode; drop its handler so
# the self-check output is just the assertions.
logging.getLogger("ConvaiTool").handlers = [logging.NullHandler()]

import ConvaiModdingTool
from core.download_utils import DownloadManager
from core.exceptions import BuildError, DownloadError, ProjectError
from core.file_utility_manager import FileUtilityManager
from core.input_manager import InputManager
from core.logger import logger
from core.migration import MIGRATION_NOTES_FILENAME, build_migration_notes, write_migration_notes
from core.unreal_engine_manager import UnrealEngineManager


class ReachedNetwork(BaseException):
    """Not an Exception: the flows wrap their steps in `except Exception`."""


def _no_downloads(*args, **kwargs):
    raise ReachedNetwork("a guard that should have refused let the flow reach a download")


NEW_VERSION = '4.0.0-beta.29.1'


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def test_migration_notes_gating():
    """T-MIG-1: notes only when the update actually broke something."""
    assert build_migration_notes(None, NEW_VERSION, False) is None
    assert build_migration_notes('4.0.0-beta.28', NEW_VERSION, False) is None

    notes = build_migration_notes('3.6.9', NEW_VERSION, False)
    for fragment in ('3.6.9', NEW_VERSION, '/ConvAI/ConvaiConveniencePack',
                     '/Game/ConvaiConveniencePack', 'source'):
        assert fragment in notes, fragment

    fresh = build_migration_notes(None, NEW_VERSION, True)
    assert fresh and 'Content/ConvaiConveniencePack' in fresh

    assert build_migration_notes('unknown', NEW_VERSION, False)


def test_write_migration_notes():
    """T-MIG-2: the notes land in the project root."""
    with tempfile.TemporaryDirectory() as tmp:
        path = write_migration_notes(tmp, 'hello notes')
        assert path == os.path.join(tmp, MIGRATION_NOTES_FILENAME)
        with open(path, encoding='utf-8') as handle:
            assert handle.read() == 'hello notes'


def test_engine_ini_repoint():
    """T-MIG-3: an existing project's game mode is moved onto the plugin mount."""
    with tempfile.TemporaryDirectory() as tmp:
        config_dir = os.path.join(tmp, 'Config')
        os.makedirs(config_dir)
        with open(os.path.join(config_dir, 'DefaultEngine.ini'), 'w', encoding='utf-8') as handle:
            handle.write('[/Script/EngineSettings.GameMapsSettings]\n'
                         'GlobalDefaultGameMode=/Game/ConvaiConveniencePack/Sample/BP_SampleGameMode.BP_SampleGameMode_C\n'
                         'EditorStartupMap=/Game/X\n')

        UnrealEngineManager._update_engine_ini(tmp, 'KEY')

        with open(os.path.join(config_dir, 'DefaultEngine.ini'), encoding='utf-8') as handle:
            content = handle.read()

        game_modes = [line for line in content.splitlines() if line.startswith('GlobalDefaultGameMode=')]
        assert game_modes == [
            'GlobalDefaultGameMode=/ConvAI/ConvaiConveniencePack/Sample/BP_SampleGameMode.BP_SampleGameMode_C'
        ], game_modes
        assert 'EditorStartupMap=/Game/X' in content
        assert 'API_Key=KEY' in content
        assert '[/Script/LinuxTargetPlatform.LinuxTargetSettings]' not in content


def test_input_manager_never_prompts():
    """T-MIG-4: the getters are caches, not prompts."""
    with open(os.path.join(REPO_ROOT, 'core', 'input_manager.py'), encoding='utf-8') as handle:
        assert 'msvcrt' not in handle.read()

    original_input = builtins.input
    builtins.input = lambda *a, **k: (_ for _ in ()).throw(AssertionError("input called"))
    try:
        with tempfile.TemporaryDirectory() as tmp:
            manager = InputManager(tmp)
            for getter in (manager.get_project_name, manager.get_api_key,
                           manager.get_asset_type, manager.choose_project_dir):
                try:
                    getter()
                except ProjectError:
                    pass
                else:
                    raise AssertionError(f"{getter.__name__} did not raise when unset")

            manager.project_name = 'MyScene'
            manager.convai_api_key = 'abc123'
            manager.asset_type, manager.is_metahuman = 'Avatar', False
            manager.project_dir = tmp
            assert manager.get_project_name() == 'MyScene'
            assert manager.get_api_key() == 'abc123'
            assert manager.get_asset_type() == ('Avatar', False)
            assert manager.choose_project_dir() == tmp

            manager.reset()
            assert manager.project_name is None and manager.project_dir is None

            os.makedirs(os.path.join(tmp, 'Taken'))
            assert InputManager.validate_project_name('', tmp)
            assert InputManager.validate_project_name('a' * 21, tmp)
            assert InputManager.validate_project_name('1abc', tmp)
            assert InputManager.validate_project_name('a b', tmp)
            assert InputManager.validate_project_name('Taken', tmp)
            assert InputManager.validate_project_name('My_Scene1', tmp) is None

            project = os.path.join(tmp, 'proj')
            nested = os.path.join(project, 'Content', 'nested')
            os.makedirs(os.path.join(project, 'ConvaiEssentials'))
            os.makedirs(os.path.join(nested, 'ConvaiEssentials'))
            open(os.path.join(project, 'x.uproject'), 'w').close()
            open(os.path.join(nested, 'y.uproject'), 'w').close()
            found = InputManager(tmp).find_existing_projects()
            assert found == [project], found
    finally:
        builtins.input = original_input


def _write_uplugin(project_dir: str, version: str):
    plugin_dir = os.path.join(project_dir, 'Plugins', 'ConvAI')
    os.makedirs(plugin_dir, exist_ok=True)
    with open(os.path.join(plugin_dir, 'ConvAI.uplugin'), 'w', encoding='utf-8') as handle:
        json.dump({'VersionName': version}, handle)


def test_update_modding_dependencies_report():
    """T-MIG-5: the old plugin and the project-level pack are replaced and reported."""
    original = DownloadManager.__dict__['download_modding_dependencies']
    DownloadManager.download_modding_dependencies = staticmethod(
        lambda project_dir, engine_version=None: _write_uplugin(project_dir, NEW_VERSION))
    try:
        with tempfile.TemporaryDirectory() as tmp:
            _write_uplugin(tmp, '3.6.9')
            pack = os.path.join(tmp, 'Content', 'ConvaiConveniencePack')
            os.makedirs(pack)
            open(os.path.join(pack, 'a.uasset'), 'w').close()

            manager = UnrealEngineManager(tmp, 'P', tmp)
            report = manager.update_modding_dependencies()
            notes = report.pop('notes')
            assert report == {'old_plugin_version': '3.6.9',
                              'new_plugin_version': NEW_VERSION,
                              'pack_removed': True}, report
            assert not os.path.exists(pack)
            assert build_migration_notes(**report)

            # The pre-delete write says 'unknown'; the download has to replace it, and the
            # report has to carry that second text rather than leave the flow to re-render it
            with open(os.path.join(tmp, MIGRATION_NOTES_FILENAME), encoding='utf-8') as handle:
                written = handle.read()
            assert NEW_VERSION in written and 'unknown' not in written, written
            assert notes == written

            second = manager.update_modding_dependencies()
            assert second.pop('notes') is None, second
            assert second == {'old_plugin_version': NEW_VERSION,
                              'new_plugin_version': NEW_VERSION,
                              'pack_removed': False}, second
            assert build_migration_notes(**second) is None
    finally:
        DownloadManager.download_modding_dependencies = original


def test_notes_survive_a_failed_download():
    """The deletes happen before the download, so a first run that dies mid-download must
    still leave the notes: on the retry the old plugin is gone and nothing can rebuild them."""
    original = DownloadManager.__dict__['download_modding_dependencies']
    try:
        with tempfile.TemporaryDirectory() as tmp:
            _write_uplugin(tmp, '3.6.9')
            manager = UnrealEngineManager(tmp, 'P', tmp)
            notes_path = os.path.join(tmp, MIGRATION_NOTES_FILENAME)

            def die(project_dir, engine_version=None):
                raise DownloadError('network hiccup')

            DownloadManager.download_modding_dependencies = staticmethod(die)
            try:
                manager.update_modding_dependencies()
            except DownloadError:
                pass
            else:
                raise AssertionError("a failed download must not be swallowed")

            assert not os.path.exists(os.path.join(tmp, 'Plugins', 'ConvAI'))
            with open(notes_path, encoding='utf-8') as handle:
                assert '3.6.9' in handle.read()

            DownloadManager.download_modding_dependencies = staticmethod(
                lambda project_dir, engine_version=None: _write_uplugin(project_dir, NEW_VERSION))
            retry = manager.update_modding_dependencies()
            assert retry['old_plugin_version'] is None, retry
            assert retry['notes'] is None, retry
            assert os.path.exists(notes_path)
    finally:
        DownloadManager.download_modding_dependencies = original


def test_update_existing_project_propagates():
    """A download failure has to reach the GUI worker, not come back as a None report."""
    original = DownloadManager.__dict__['download_modding_dependencies']

    def die(project_dir, engine_version=None):
        raise DownloadError('no release for this engine')

    DownloadManager.download_modding_dependencies = staticmethod(die)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            manager = UnrealEngineManager(tmp, 'P', tmp)
            try:
                manager.update_existing_project('Avatar', False, 'Plug', 'KEY')
            except DownloadError:
                pass
            else:
                raise AssertionError("update_existing_project swallowed the download failure")
    finally:
        DownloadManager.download_modding_dependencies = original


def test_plugin_availability_checked_before_toolchain():
    """No release for this engine short-circuits before the 400MB toolchain download."""
    originals = (DownloadManager.__dict__['check_convai_plugin_available'],
                 DownloadManager.__dict__['ensure_toolchain_for_version'])
    toolchain_calls = []
    DownloadManager.check_convai_plugin_available = staticmethod(lambda engine_version: False)
    DownloadManager.ensure_toolchain_for_version = staticmethod(
        lambda version: toolchain_calls.append(version) or True)
    try:
        manager = UnrealEngineManager('C:/UE_5.8')
        manager.engine_version = config.get_current_unreal_engine_version()
        assert manager.can_create_modding_project() is False
        assert toolchain_calls == [], toolchain_calls
    finally:
        DownloadManager.check_convai_plugin_available, DownloadManager.ensure_toolchain_for_version = (
            staticmethod(originals[0]), staticmethod(originals[1]))


def _fake_engine(root: str, version: str) -> str:
    """Enough of an engine tree for _extract_engine_version to read a version off it."""
    engine_dir = os.path.join(root, 'UE')
    resources = os.path.join(engine_dir, 'Engine', 'Source', 'Runtime', 'Launch', 'Resources')
    os.makedirs(resources)
    major, minor = version.split('.')
    with open(os.path.join(resources, 'Version.h'), 'w', encoding='utf-8') as handle:
        handle.write(f"#define ENGINE_MAJOR_VERSION {major}\n"
                     f"#define ENGINE_MINOR_VERSION {minor}\n")
    return engine_dir


def _fake_project(root: str, engine_association: str) -> str:
    """A project the flows can load: metadata, a .uproject, and a 3.x plugin to lose."""
    project_dir = os.path.join(root, 'P')
    essentials = os.path.join(project_dir, config.get_essentials_dir_name())
    os.makedirs(essentials)
    with open(os.path.join(essentials, config.get_metadata_file_name()), 'w', encoding='utf-8') as handle:
        json.dump({'project_name': 'P', 'asset_type': 'Avatar', 'is_metahuman': False,
                   'plugin_name': 'Plug', 'api_key': 'KEY'}, handle)
    with open(os.path.join(project_dir, 'P.uproject'), 'w', encoding='utf-8') as handle:
        json.dump({'EngineAssociation': engine_association}, handle)
    _write_uplugin(project_dir, '3.6.9')
    return project_dir


def test_metadata_resolves_the_chunk_before_the_flat_file():
    """The Pak Manager moves ModdingMetaData.txt into ChunkId_<N>/ and reads per-chunk first.

    Reading only the flat path returns {} on any project whose panel has been opened once,
    and Update discovers that after it has already deleted the SDK plugins.
    """
    stem = os.path.splitext(config.get_metadata_file_name())[0]

    with tempfile.TemporaryDirectory() as tmp:
        essentials = os.path.join(tmp, config.get_essentials_dir_name())
        os.makedirs(essentials)
        assert FileUtilityManager.get_metadata(tmp) == {}

        flat = os.path.join(essentials, config.get_metadata_file_name())
        with open(flat, 'w', encoding='utf-8') as handle:
            json.dump({'plugin_name': 'flat'}, handle)
        assert FileUtilityManager.get_metadata(tmp)['plugin_name'] == 'flat'

        # 7, not 10: a ChunkId_10 fixture passes against a hardcoded read and proves nothing.
        chunk = os.path.join(essentials, 'ChunkId_7')
        os.makedirs(chunk)
        legacy = os.path.join(chunk, f'{stem}_7.txt')
        with open(legacy, 'w', encoding='utf-8') as handle:
            json.dump({'plugin_name': 'chunk-txt'}, handle)
        assert FileUtilityManager.get_metadata(tmp)['plugin_name'] == 'chunk-txt'

        with open(os.path.join(chunk, f'{stem}_7.json'), 'w', encoding='utf-8') as handle:
            json.dump({'plugin_name': 'chunk-json'}, handle)
        assert FileUtilityManager.get_metadata(tmp)['plugin_name'] == 'chunk-json'

        # An existing chunk is written in place - never a second one beside it.
        FileUtilityManager.save_metadata(tmp, {'api_key': 'KEY'})
        assert sorted(os.listdir(essentials)) == ['ChunkId_7', config.get_metadata_file_name()]
        assert FileUtilityManager.get_metadata(tmp)['api_key'] == 'KEY'
        assert FileUtilityManager.get_metadata(tmp)['plugin_name'] == 'chunk-json'


def test_new_project_metadata_lands_in_chunk_10():
    """A project with no Chunk gets ChunkId_10 - the id the Pak Manager mints for the first one.

    No flat file: the plugin resolves ChunkId_<N> from the Primary Asset Label, which this
    tool does not author, so a fresh project needs that label added before Create chunk works.
    """
    stem = os.path.splitext(config.get_metadata_file_name())[0]

    with tempfile.TemporaryDirectory() as tmp:
        FileUtilityManager.save_metadata(tmp, {'plugin_name': 'Plug'})

        essentials = os.path.join(tmp, config.get_essentials_dir_name())
        assert os.listdir(essentials) == ['ChunkId_10']
        assert os.listdir(os.path.join(essentials, 'ChunkId_10')) == [f'{stem}_10.json']
        assert FileUtilityManager.get_metadata(tmp)['plugin_name'] == 'Plug'


def test_metadata_survives_a_glob_wildcard_in_the_project_path():
    """A project directory may contain [ or ], which glob reads as a character class."""
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = os.path.join(tmp, 'pr[o]j')
        FileUtilityManager.save_metadata(project_dir, {'plugin_name': 'Plug'})
        assert FileUtilityManager.get_metadata(project_dir)['plugin_name'] == 'Plug'

def test_migrate_refuses_without_a_plugin_release():
    """Migrate updates the user's only copy in place, and that update deletes Plugins/ConvAI
    before it downloads. With no release for the engine it must stop before the delete."""
    checked = []
    current = config.get_current_unreal_engine_version()
    original_check = DownloadManager.__dict__['check_convai_plugin_available']
    original_ubt = FileUtilityManager.__dict__['validate_ubt_configuration']
    original_deps = DownloadManager.__dict__['download_modding_dependencies']
    DownloadManager.check_convai_plugin_available = staticmethod(
        lambda engine_version: checked.append(engine_version) or False)
    FileUtilityManager.validate_ubt_configuration = staticmethod(lambda: True)
    # Without this the refusal still fails the test, but only after three live downloads.
    DownloadManager.download_modding_dependencies = staticmethod(_no_downloads)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            # The engine on disk is the current one - the GUI validates it against config
            # before caching it - while the project being migrated is what is left on 5.4
            project_dir = _fake_project(tmp, '5.4')
            ConvaiModdingTool.input_manager.project_dir = project_dir
            ConvaiModdingTool.input_manager.unreal_engine_path = _fake_engine(tmp, current)
            try:
                # A plain return reads as success on the run screen, so the refusal raises.
                refusal = None
                try:
                    ConvaiModdingTool.MigrateModdingProject()
                except ProjectError as error:
                    refusal = str(error)
                assert refusal and current in refusal, refusal
            finally:
                ConvaiModdingTool.input_manager.reset()
                ConvaiModdingTool.input_manager.unreal_engine_path = None

            assert checked == [current], checked
            assert os.path.exists(os.path.join(project_dir, 'Plugins', 'ConvAI', 'ConvAI.uplugin'))
            assert not os.path.exists(os.path.join(project_dir, MIGRATION_NOTES_FILENAME))
    finally:
        DownloadManager.check_convai_plugin_available = original_check
        DownloadManager.download_modding_dependencies = original_deps
        FileUtilityManager.validate_ubt_configuration = original_ubt


def test_update_refuses_when_prerequisites_fail():
    """The same lie on the update flow: a prerequisite check that fails - no release for
    this engine, network down - has to raise, because the worker reads None as a win."""
    current = config.get_current_unreal_engine_version()
    original_can = UnrealEngineManager.can_create_modding_project
    original_ubt = FileUtilityManager.__dict__['validate_ubt_configuration']
    original_deps = DownloadManager.__dict__['download_modding_dependencies']
    UnrealEngineManager.can_create_modding_project = lambda self: False
    FileUtilityManager.validate_ubt_configuration = staticmethod(lambda: True)
    # Without this the refusal still fails the test, but only after three live downloads.
    DownloadManager.download_modding_dependencies = staticmethod(_no_downloads)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = _fake_project(tmp, current)
            ConvaiModdingTool.input_manager.project_dir = project_dir
            ConvaiModdingTool.input_manager.unreal_engine_path = _fake_engine(tmp, current)
            try:
                ConvaiModdingTool.UpdateModdingProject()
            except ProjectError:
                pass
            else:
                raise AssertionError("a refused update must not come back as success")
            finally:
                ConvaiModdingTool.input_manager.reset()
                ConvaiModdingTool.input_manager.unreal_engine_path = None

            assert os.path.exists(os.path.join(project_dir, 'Plugins', 'ConvAI', 'ConvAI.uplugin'))
    finally:
        UnrealEngineManager.can_create_modding_project = original_can
        DownloadManager.download_modding_dependencies = original_deps
        FileUtilityManager.validate_ubt_configuration = original_ubt


def test_configure_assets_without_pak_manager():
    """The dropped AssetUploader copy took two early returns with it: on main, a missing
    PakManager plugin skipped the Reallusion download entirely."""
    original = DownloadManager.__dict__['download_convai_realusion_content']
    called = []
    DownloadManager.download_convai_realusion_content = staticmethod(called.append)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            UnrealEngineManager(tmp, 'P', tmp).configure_assets_in_project('Avatar', False)
            assert called == [tmp], called
    finally:
        DownloadManager.download_convai_realusion_content = original


class _FakeProcess:
    def __init__(self, *args, **kwargs):
        self.stdout = io.StringIO("Compiling Convai.cpp\nerror C2039: nope\n")
        self.returncode = 1

    def wait(self):
        return self.returncode


def test_run_unreal_build_streams_and_fails():
    """T-MIG-6: build output reaches the logger and a bad exit code is fatal."""
    import subprocess

    capture = _Capture()
    logger.logger.addHandler(capture)
    original_popen, original_exists = subprocess.Popen, os.path.exists
    subprocess.Popen = _FakeProcess
    os.path.exists = lambda path: True
    try:
        try:
            UnrealEngineManager('C:/UE_5.8', 'P', 'C:/Projects/P').run_unreal_build()
        except BuildError:
            pass
        else:
            raise AssertionError("a failed compile must raise BuildError")
    finally:
        subprocess.Popen, os.path.exists = original_popen, original_exists
        logger.logger.removeHandler(capture)

    logged = "\n".join(capture.messages)
    assert "Compiling Convai.cpp" in logged
    assert "error C2039: nope" in logged


if __name__ == '__main__':
    test_migration_notes_gating()
    test_write_migration_notes()
    test_engine_ini_repoint()
    test_input_manager_never_prompts()
    test_update_modding_dependencies_report()
    test_notes_survive_a_failed_download()
    test_update_existing_project_propagates()
    test_plugin_availability_checked_before_toolchain()
    test_migrate_refuses_without_a_plugin_release()
    test_update_refuses_when_prerequisites_fail()
    test_configure_assets_without_pak_manager()
    test_metadata_resolves_the_chunk_before_the_flat_file()
    test_new_project_metadata_lands_in_chunk_10()
    test_metadata_survives_a_glob_wildcard_in_the_project_path()
    test_run_unreal_build_streams_and_fails()
    print('ok')
