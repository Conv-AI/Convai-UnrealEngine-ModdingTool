"""Self-checks for lazy remote config, the linux packaging flag and version checking.

Plain asserts, no network: run with `python tests/test_config.py`.
"""
import builtins
import json
import logging
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import requests

# The tool's logger writes emoji that a cp1252 console cannot encode; quiet it so the
# self-check output is just the assertions.
logging.getLogger("ConvaiTool").disabled = True


def test_import_does_not_fetch():
    """T-CFG-1: importing core.config_manager must not touch the network."""
    original_get = requests.get
    requests.get = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network used at import"))
    try:
        import core.config_manager as cm
        assert cm.config._remote_config is None, "config was loaded at import time"
    finally:
        requests.get = original_get


def test_linux_enabled():
    """T-CFG-2: the flag reader tolerates junk and reads should-package."""
    from core.config_manager import ConfigManager, DEFAULT_ASSET_UPLOADER_CONFIG

    assert ConfigManager._linux_enabled(None) is False
    assert ConfigManager._linux_enabled({}) is False
    assert ConfigManager._linux_enabled({'unreal-engine': None}) is False
    assert ConfigManager._linux_enabled({'unreal-engine': {'linux': {}}}) is False
    assert ConfigManager._linux_enabled(
        {'unreal-engine': {'linux': {'should-package': True}}}) is True
    assert ConfigManager._linux_enabled(
        {'unreal-engine': {'linux': {'should-package': False}}}) is False
    assert ConfigManager._linux_enabled(DEFAULT_ASSET_UPLOADER_CONFIG) is False


def _fresh_manager(responses):
    """A ConfigManager outside the singleton whose fetches come from `responses`."""
    from core.config_manager import ConfigManager

    saved = ConfigManager._instance
    ConfigManager._instance = None
    try:
        manager = ConfigManager()
        manager._fetch_json = lambda path: responses.get(path)
        return manager
    finally:
        ConfigManager._instance = saved


def test_uploader_config_fallback():
    """T-CFG-3: a failed uploader fetch falls back; a failed main fetch is fatal."""
    from core.config_manager import ConfigManager, DEFAULT_ASSET_UPLOADER_CONFIG
    from core.exceptions import ConfigurationError

    manager = _fresh_manager({
        ConfigManager.CONFIG_FILE_PATH: {'github': {}},
        ConfigManager.VERSION_FILE_PATH: {},
        ConfigManager.UPLOADER_CONFIG_FILE_PATH: None,
    })
    manager.load()
    assert manager.remote_config.uploader_config is DEFAULT_ASSET_UPLOADER_CONFIG
    assert manager.linux_packaging_enabled() is False

    manager._remote_config = None
    manager._fetch_json = lambda path: (
        {'unreal-engine': {'linux': {'should-package': True}}}
        if path == ConfigManager.UPLOADER_CONFIG_FILE_PATH else {'github': {}}
    )
    manager.load()
    assert manager.linux_packaging_enabled() is True

    broken = _fresh_manager({})
    try:
        broken.load()
    except ConfigurationError:
        pass
    else:
        raise AssertionError("a failed main config fetch must raise ConfigurationError")


def test_check_version_never_prompts():
    """T-CFG-4: check_version is exact-match only and never reads stdin."""
    from core.config_manager import RemoteConfig, config
    from core.version_manager import VersionManager, LATEST_RELEASE_URL

    assert LATEST_RELEASE_URL.startswith("https://github.com/")

    def serve(version_data):
        """The startup load's own copy of Version.json - the one CONVAI_MODDING_CONFIG_DIR
        redirects. check_version reading anything else ignores a local checkout."""
        config._remote_config = RemoteConfig(config={}, version_data=version_data,
                                             uploader_config={})

    saved = config._remote_config
    original_input = builtins.input
    builtins.input = lambda *a, **k: (_ for _ in ()).throw(AssertionError("input called"))
    try:
        serve({"modding-tool-version": "9.9.9"})
        assert VersionManager.check_version("3.1.0") is False

        serve({"modding-tool-version": "3.1.0"})
        assert VersionManager.check_version("3.1.0") is True

        # A check that could not be made is None, not False: the boot screen sends an
        # outdated build to the download page, and an unreachable GitHub is not that.
        # An unreadable Version.json loads as {}.
        serve({})
        assert VersionManager.check_version("3.1.0") is None

        serve({"other-key": "3.1.0"})
        assert VersionManager.check_version("3.1.0") is None
    finally:
        builtins.input = original_input
        config._remote_config = saved


def test_shipped_config_json():
    """T-CFG-5: the config the exe fetches from main points at SDK-V4."""
    path = os.path.join(REPO_ROOT, 'resources', 'modding_tool_config.json')
    with open(path, encoding='utf-8') as handle:
        cfg = json.load(handle)

    github = cfg['github']
    assert set(github) == {'convai_plugin', 'convai_http_plugin', 'convai_pak_manager'}, github.keys()

    plugin = github['convai_plugin']
    assert plugin['repo'] == 'Conv-AI/Convai-UnrealEngine-SDK-V4'
    assert plugin['asset_patterns'] == ['-marketplace-no-binaries.zip']
    assert plugin['marketplace_prefix'] == 'marketplace-'
    assert plugin['engine_specific'] is True
    assert plugin['post_process'] is True

    # The helper plugins ship one generic asset each, so they must stay engine-agnostic.
    for name in ('convai_http_plugin', 'convai_pak_manager'):
        assert 'engine_specific' not in github[name], name

    # A shipped pin is legitimate, so this checks its shape, not its absence: a typo'd key
    # is silently ignored, and a twin tag pins a version that does not exist.
    for name, plugin in github.items():
        override = plugin.get('override')
        if override is None:
            continue
        assert set(override) <= {'version', 'asset'}, (name, override)
        prefix = plugin.get('marketplace_prefix')
        version = override.get('version', '')
        assert not (prefix and version.startswith(prefix)), (name, version)

    assert 'editor' not in cfg['directory_names']
    assert 'uploader_asset' not in cfg['asset_names']
    assert cfg['asset_names']['convenience_pack'] == 'ConvaiConveniencePack'

    # The Pak Manager resolves the SDK mount by plugin name and treats /ConvAI/ and
    # /ConvaiHTTP/ as the only content its dependency gather may skip. Rename either here
    # and the gather starts copying that plugin into every creator's Modding Plugin, with
    # nothing in this tool failing: find_plugin_directory just stops matching, so the SDK
    # swap, the source patching and the MetaHumans removal all silently no-op.
    assert cfg['file_names']['plugin_files'] == {
        'convai': 'ConvAI.uplugin',
        'convai_http': 'ConvaiHTTP.uplugin',
        'convai_pak_manager': 'ConvaiPakManager.uplugin',
    }, cfg['file_names']['plugin_files']
    assert cfg['project_settings']['required_plugins'][:3] == [
        'ConvAI', 'ConvaiHTTP', 'ConvaiPakManager'], cfg['project_settings']['required_plugins']


def test_tool_version():
    """T-CFG-6: the exe's version and the one it fetches to compare against must match.

    Value-agnostic on purpose - the release bump is the user's. This only catches one of
    the two files moving without the other, which would block every exe on boot.
    """
    import ConvaiModdingTool

    with open(os.path.join(REPO_ROOT, 'Version.json'), encoding='utf-8') as handle:
        version_data = json.load(handle)

    shipped = version_data['modding-tool-version']
    assert ConvaiModdingTool.TOOL_VERSION == shipped, (ConvaiModdingTool.TOOL_VERSION, shipped)

    # Also value-agnostic. The Pak Manager plugin reads target-ue-version off main on every
    # panel open and fails open on anything it cannot parse, so a typo raises no banner
    # there and silently degrades three things here: the engine getters fall back to
    # hardcoded versions, the engine-match checks stop matching any installation, and every
    # version-specific compatibility rule drops.
    for key in ('current-ue-version', 'target-ue-version'):
        value = version_data.get(key)
        assert isinstance(value, str) and re.fullmatch(r'\d+\.\d+', value), (key, value)


def test_shipped_uploader_config():
    """T-CFG-8: the publish policy main serves is one the Pak Manager can act on.

    The plugin fetches this before every Publish and refuses the run if it cannot. Nothing
    downstream of a merge checks it, so a `chore:` commit that drops a key reaches every
    installed editor at once.
    """
    from core.config_manager import DEFAULT_ASSET_UPLOADER_CONFIG

    path = os.path.join(REPO_ROOT, 'resources', 'asset_uploader_config.json')
    with open(path, encoding='utf-8') as handle:
        policy = json.load(handle)

    platforms = policy['unreal-engine']
    assert set(platforms) == {'windows', 'linux'}, platforms.keys()

    packaged = []
    for name, platform in platforms.items():
        assert isinstance(platform['should-package'], bool), (name, platform)
        if not platform['should-package']:
            continue
        packaged.append(name)
        # The plugin's parser clears the configuration before each platform block, so a
        # packaged platform cannot inherit the Shipping default and the whole policy is
        # refused instead.
        assert platform.get('configuration'), (name, platform)

    raw = policy['raw-project-upload']
    assert isinstance(raw, bool), raw
    assert packaged or raw, 'a policy that packages nothing and uploads nothing is a misread'

    # The exe bundles no data files, so an unreachable fetch falls back to a copy of this
    # policy typed out in Python. Nothing else makes the two move together.
    assert policy == DEFAULT_ASSET_UPLOADER_CONFIG, 'flip the fallback in config_manager.py too'

def test_config_source_override():
    """T-CFG-7: the overrides let a config change be tested before it reaches main.

    The local one must not fall through to the network on a bad path - a silent fetch of
    main's config is exactly the confusion the override exists to remove.
    """
    from core.config_manager import ConfigManager

    manager = ConfigManager.__new__(ConfigManager)
    manager._max_attempts, manager._timeout = 1, 1

    urls = []
    original_get = requests.get
    requests.get = lambda url, **k: urls.append(url) or (_ for _ in ()).throw(
        requests.RequestException("no network in this test"))
    original_env = {k: os.environ.get(k) for k in (ConfigManager.LOCAL_ENV, ConfigManager.BRANCH_ENV)}
    try:
        os.environ.pop(ConfigManager.LOCAL_ENV, None)
        os.environ.pop(ConfigManager.BRANCH_ENV, None)
        manager._fetch_json(ConfigManager.CONFIG_FILE_PATH)
        assert f"/{ConfigManager.GITHUB_BRANCH}/" in urls[-1], urls[-1]

        os.environ[ConfigManager.BRANCH_ENV] = 'some-branch'
        manager._fetch_json(ConfigManager.CONFIG_FILE_PATH)
        assert '/some-branch/' in urls[-1], urls[-1]

        # A readable directory returns the file on disk, and never reaches the network.
        os.environ[ConfigManager.LOCAL_ENV] = REPO_ROOT
        before = len(urls)
        local = manager._fetch_json(ConfigManager.CONFIG_FILE_PATH)
        assert local and 'github' in local, local
        assert len(urls) == before, "local override still hit the network"

        os.environ[ConfigManager.LOCAL_ENV] = os.path.join(REPO_ROOT, 'no-such-dir')
        assert manager._fetch_json(ConfigManager.CONFIG_FILE_PATH) is None
        assert len(urls) == before, "a bad local override fell through to the network"
    finally:
        requests.get = original_get
        for key, value in original_env.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value


if __name__ == '__main__':
    test_import_does_not_fetch()
    test_linux_enabled()
    test_uploader_config_fallback()
    test_check_version_never_prompts()
    test_shipped_config_json()
    test_tool_version()
    test_shipped_uploader_config()
    test_config_source_override()
    print('ok')
