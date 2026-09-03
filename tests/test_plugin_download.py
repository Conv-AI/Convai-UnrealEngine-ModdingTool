"""Self-checks for engine-matched plugin resolution, the source strip and fatal deps.

Plain asserts, no network: run with `python tests/test_plugin_download.py`.
"""
import copy
import json
import logging
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from core.config_manager import RemoteConfig, config

logging.getLogger("ConvaiTool").disabled = True

# Seed the config so nothing in this file touches the network.
config._remote_config = RemoteConfig(
    config={
        'github': {
            'convai_plugin': {
                'repo': 'Conv-AI/Convai-UnrealEngine-SDK-V4',
                'asset_patterns': ['-marketplace-no-binaries.zip'],
                'marketplace_prefix': 'marketplace-',
                'engine_specific': True,
                'post_process': True,
            },
            'convai_http_plugin': {'repo': 'Conv-AI/Convai-UnrealEngine-HTTP'},
            'convai_pak_manager': {'repo': 'Conv-AI/Convai-UnrealEngine-PakManager'},
        }
    },
    version_data={},
    uploader_config={'unreal-engine': {'linux': {'should-package': False}}},
)

from core.download_utils import DownloadManager
from core.exceptions import DownloadError
from core.github_manager import GitHubManager


class ReachedNetwork(BaseException):
    """Not an Exception: the code under test wraps everything in `except Exception`."""
from core.plugin_manager import PluginManager


def _assets(*names):
    return [{'name': n, 'browser_download_url': f'https://example/{n}'} for n in names]


def _release(tag, prerelease, assets):
    return {'tag_name': tag, 'prerelease': prerelease, 'assets': _assets(*assets)}


def _compiled(*versions):
    return [f'Convai-UE{v}.zip' for v in versions]


def _marketplace(*versions):
    return [f'Convai-UE{v}-marketplace-no-binaries.zip' for v in versions]


# Mirrors the live SDK-V4 listing: compiled and marketplace releases interleave, the
# beta.24 / beta.23-hotfix twins come after both compiled tags, and beta.22 has no twin.
LIVE_ORDERING = [
    _release('4.0.0-beta.29.1', False, _compiled('5.3', '5.4', '5.5', '5.6', '5.7', '5.8')),
    _release('marketplace-4.0.0-beta.29.1', True, _marketplace('5.3', '5.4', '5.5', '5.6', '5.7', '5.8')),
    _release('4.0.0-beta.29', False, _compiled('5.3', '5.4', '5.5', '5.6', '5.7', '5.8')),
    _release('marketplace-4.0.0-beta.29', True, _marketplace('5.3', '5.4', '5.5', '5.6', '5.7', '5.8')),
    _release('4.0.0-beta.24', False, _compiled('5.3', '5.4', '5.5', '5.6')),
    _release('4.0.0-beta.23-hotfix', False, _compiled('5.3', '5.4', '5.5', '5.6')),
    _release('marketplace-4.0.0-beta.24', True, _marketplace('5.3', '5.4', '5.5', '5.6')),
    _release('marketplace-4.0.0-beta.23-hotfix', True, _marketplace('5.3', '5.4', '5.5', '5.6')),
    _release('4.0.0-beta.22', False, _compiled('5.3', '5.4', '5.5')),
    _release('4.0.0-beta.15', False, _compiled('5.2', '5.3', '5.4', '5.5')),
]

PATTERNS = ['-marketplace-no-binaries.zip']
PREFIX = 'marketplace-'


def test_asset_matches_engine():
    """T-DL-1: engine matching is bounded, so UE5.1 never matches UE5.10."""
    match = GitHubManager.asset_matches_engine

    assert match('Convai-UE5.8.zip', '5.8') is True
    assert match('Convai-UE5.8-marketplace-no-binaries.zip', '5.8') is True
    assert match('convai-ue5.8.zip', '5.8') is True
    assert match('Convai-UE5.10.zip', '5.1') is False
    assert match('Convai-UE5.7.zip', '5.8') is False


def test_find_matching_asset():
    """T-DL-2: the engine wins over asset order (live bug: V5.2.zip into a 5.8 project)."""
    assets = _assets('Convai-UE5.2.zip', 'Convai-UE5.7.zip', 'Convai-UE5.8.zip')

    picked = GitHubManager.find_matching_asset(assets, ['.zip'], '5.8')
    assert picked['name'] == 'Convai-UE5.8.zip', picked

    assert GitHubManager.find_matching_asset(assets, ['.zip'])['name'] == 'Convai-UE5.2.zip'
    assert GitHubManager.find_matching_asset(assets, PATTERNS, '5.8') is None


def test_resolve_plugin_release():
    """T-DL-3: prefer the marketplace twin, then any marketplace, then compiled."""
    resolve = GitHubManager.resolve_plugin_release

    release, asset, source = resolve(LIVE_ORDERING, '5.8', PATTERNS, PREFIX)
    assert release['tag_name'] == 'marketplace-4.0.0-beta.29.1', release['tag_name']
    assert asset['name'] == 'Convai-UE5.8-marketplace-no-binaries.zip', asset['name']
    assert source == 'marketplace'

    # Newest twin missing this engine: walk back to the next marketplace release.
    gapped = copy.deepcopy(LIVE_ORDERING)
    gapped[1]['assets'] = [a for a in gapped[1]['assets'] if '5.8' not in a['name']]
    release, asset, source = resolve(gapped, '5.8', PATTERNS, PREFIX)
    assert release['tag_name'] == 'marketplace-4.0.0-beta.29', release['tag_name']
    assert source == 'marketplace'

    # No marketplace release ever shipped 5.2, so the compiled fallback takes over.
    release, asset, source = resolve(LIVE_ORDERING, '5.2', PATTERNS, PREFIX)
    assert release['tag_name'] == '4.0.0-beta.15', release['tag_name']
    assert asset['name'] == 'Convai-UE5.2.zip', asset['name']
    assert source == 'compiled'

    # A marketplace release ahead of the newest compiled tag is not the one users are
    # meant to be on: the twin of the newest compiled release still wins.
    unpaired = [_release('marketplace-4.0.0-beta.30', True, _marketplace('5.8'))] + LIVE_ORDERING
    release, asset, source = resolve(unpaired, '5.8', PATTERNS, PREFIX)
    assert release['tag_name'] == 'marketplace-4.0.0-beta.29.1', release['tag_name']

    # ...unless that twin has nothing for this engine, and then order decides again.
    unpaired[2]['assets'] = [a for a in unpaired[2]['assets'] if '5.8' not in a['name']]
    release, asset, source = resolve(unpaired, '5.8', PATTERNS, PREFIX)
    assert release['tag_name'] == 'marketplace-4.0.0-beta.30', release['tag_name']

    assert resolve(LIVE_ORDERING, '5.9', PATTERNS, PREFIX) is None
    assert resolve([], '5.8', PATTERNS, PREFIX) is None


BUILD_CS = '''using UnrealBuildTool;

public class Convai : ModuleRules
{
    private const bool BEnableConvaiHttp = false;

    public Convai(ReadOnlyTargetRules Target) : base(Target)
    {
        PublicDefinitions.Add("USE_CONVAI_HTTP=0" + (BEnableConvaiHttp ? "1" : "0"));

        if (BEnableConvaiHttp)
        {
            PublicDependencyModuleNames.Add("ConvaiHTTP");
        }
    }
}
'''


def test_set_convai_http_enabled():
    """T-DL-4: flip the value, keep the declaration's own spelling, touch nothing else."""
    updated, count = PluginManager.set_convai_http_enabled(BUILD_CS)
    assert count == 1, count
    assert '    private const bool BEnableConvaiHttp = true;' in updated

    before = [l for l in BUILD_CS.splitlines() if 'BEnableConvaiHttp' in l][1:]
    after = [l for l in updated.splitlines() if 'BEnableConvaiHttp' in l][1:]
    assert before == after, after

    again, count = PluginManager.set_convai_http_enabled(updated)
    assert (again, count) == (updated, 1)
    assert PluginManager.set_convai_http_enabled(updated.replace('true;', 'false;'))[0] == updated

    # V3 spells it bEnableConvaiHTTP; renaming it would break the use sites (CS0103).
    v3 = BUILD_CS.replace('BEnableConvaiHttp', 'bEnableConvaiHTTP')
    updated_v3, count = PluginManager.set_convai_http_enabled(v3)
    assert count == 1
    assert 'private const bool bEnableConvaiHTTP = true;' in updated_v3

    missing, count = PluginManager.set_convai_http_enabled('public class Convai {}')
    assert (missing, count) == ('public class Convai {}', 0)


def test_strip_to_source():
    """T-DL-5: both install paths converge on a source-only tree."""
    with tempfile.TemporaryDirectory() as plugin_dir:
        for name, payload in (('Binaries', 'x.dll'), ('Intermediate', 'y'), ('Source', 'z.cpp')):
            os.makedirs(os.path.join(plugin_dir, name))
            with open(os.path.join(plugin_dir, name, payload), 'w') as handle:
                handle.write('x')

        uplugin = os.path.join(plugin_dir, 'ConvAI.uplugin')
        with open(uplugin, 'w') as handle:
            json.dump({'Installed': True, 'EngineVersion': '5.8.0',
                       'VersionName': '4.0.0-beta.29.1'}, handle)

        for _ in range(2):
            assert PluginManager.strip_precompiled(plugin_dir) is True
            assert PluginManager.clean_uplugin(uplugin) is True

            assert sorted(os.listdir(plugin_dir)) == ['ConvAI.uplugin', 'Source']
            with open(uplugin) as handle:
                data = json.load(handle)
            assert data == {'VersionName': '4.0.0-beta.29.1'}, data


def _plugin_tree(project_dir, installed=True):
    """A freshly extracted compiled-release layout, the one that needs the most stripping."""
    plugin_dir = os.path.join(project_dir, config.get_plugins_dir_name(), 'ConvAI')
    source_dir = os.path.join(plugin_dir, 'Source', 'Convai')
    os.makedirs(os.path.join(plugin_dir, 'Binaries', 'Win64'))
    os.makedirs(source_dir)
    with open(os.path.join(plugin_dir, 'Binaries', 'Win64', 'UnrealEditor-Convai.dll'), 'w') as handle:
        handle.write('x')
    with open(os.path.join(source_dir, config.get_build_file_name()), 'w') as handle:
        handle.write(BUILD_CS)

    uplugin = os.path.join(plugin_dir, config.get_plugin_file_name('convai'))
    with open(uplugin, 'w') as handle:
        json.dump({'Installed': installed, 'EngineVersion': '5.8.0', 'Modules': []}, handle)
    return plugin_dir, uplugin


def test_post_process_convai_plugin():
    """T-DL-5: one call leaves a source-only tree with ConvaiHTTP on, or fails loudly."""
    with tempfile.TemporaryDirectory() as project_dir:
        plugin_dir, uplugin = _plugin_tree(project_dir)

        assert PluginManager.post_process_convai_plugin(project_dir) is True
        assert not os.path.exists(os.path.join(plugin_dir, 'Binaries'))
        with open(uplugin) as handle:
            assert json.load(handle) == {'Modules': []}
        with open(os.path.join(plugin_dir, 'Source', 'Convai', config.get_build_file_name())) as handle:
            assert 'BEnableConvaiHttp = true;' in handle.read()

    # A uplugin left holding Installed: true would make UBT skip the source build, so a
    # rewrite failure has to stop the run and not just warn.
    with tempfile.TemporaryDirectory() as project_dir:
        plugin_dir, uplugin = _plugin_tree(project_dir)
        with open(uplugin, 'w') as handle:
            handle.write('{"Installed": true,')
        assert PluginManager.post_process_convai_plugin(project_dir) is False

    with tempfile.TemporaryDirectory() as project_dir:
        plugin_dir, _ = _plugin_tree(project_dir)
        os.remove(os.path.join(plugin_dir, 'Source', 'Convai', config.get_build_file_name()))
        assert PluginManager.post_process_convai_plugin(project_dir) is False

    with tempfile.TemporaryDirectory() as project_dir:
        assert PluginManager.post_process_convai_plugin(project_dir) is False


def test_engine_specific_download_needs_a_version():
    """T-DL-2: no engine version, no guess at which engine's asset to pull."""
    # The guard has to stop us before the release listing. Without this stub the
    # test passes either way: the download raises, the bare except returns False.
    original = GitHubManager.download_plugin_from_release

    def unreachable(*args, **kwargs):
        raise ReachedNetwork("the engine-version guard is gone")

    GitHubManager.download_plugin_from_release = staticmethod(unreachable)
    try:
        assert DownloadManager.download_plugin_from_github('project', 'convai_plugin') is False
    finally:
        GitHubManager.download_plugin_from_release = original


def test_critical_dependency_failure():
    """T-DL-6: a plugin the project cannot compile without aborts the run."""
    original = DownloadManager.download_plugin_from_github

    def failing(plugin_name):
        return staticmethod(lambda project_dir, name, engine_version=None: name != plugin_name)

    try:
        for name in ('convai_plugin', 'convai_http_plugin'):
            DownloadManager.download_plugin_from_github = failing(name)
            try:
                DownloadManager.download_modding_dependencies('project', '5.8')
            except DownloadError as e:
                assert name in str(e), e
            else:
                raise AssertionError(f"{name} failing must raise DownloadError")

        DownloadManager.download_plugin_from_github = failing('convai_pak_manager')
        DownloadManager.download_modding_dependencies('project', '5.8')
    finally:
        DownloadManager.download_plugin_from_github = original


def test_toolchain_gate():
    """T-DL-7: no toolchain work while Linux packaging is off, unless forced."""
    calls = []
    original = DownloadManager.is_toolchain_installed
    DownloadManager.is_toolchain_installed = staticmethod(
        lambda ue_version: calls.append(ue_version) or True)
    try:
        assert DownloadManager.ensure_toolchain_for_version('5.8') is True
        assert calls == [], calls

        assert DownloadManager.ensure_toolchain_for_version('5.8', force=True) is True
        assert calls == ['5.8'], calls
    finally:
        DownloadManager.is_toolchain_installed = original


def test_no_console_io_in_download_utils():
    """T-DL-7: the toolchain path must not block a GUI on stdin."""
    with open(os.path.join(REPO_ROOT, 'core', 'download_utils.py'), encoding='utf-8') as handle:
        source = handle.read()

    for banned in ('input(', 'print(', 'stdin'):
        assert banned not in source, banned


if __name__ == '__main__':
    test_asset_matches_engine()
    test_find_matching_asset()
    test_resolve_plugin_release()
    test_set_convai_http_enabled()
    test_strip_to_source()
    test_post_process_convai_plugin()
    test_engine_specific_download_needs_a_version()
    test_critical_dependency_failure()
    test_toolchain_gate()
    test_no_console_io_in_download_utils()
    print('ok')
