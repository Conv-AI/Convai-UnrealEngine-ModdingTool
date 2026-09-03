"""Self-checks for lazy remote config, the linux packaging flag and version checking.

Plain asserts, no network: run with `python tests/test_config.py`.
"""
import builtins
import json
import logging
import os
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
    from core.github_manager import GitHubManager
    from core.version_manager import VersionManager, LATEST_RELEASE_URL

    assert LATEST_RELEASE_URL.startswith("https://github.com/")

    original_input, original_fetch = builtins.input, GitHubManager.get_file_content
    builtins.input = lambda *a, **k: (_ for _ in ()).throw(AssertionError("input called"))
    try:
        GitHubManager.get_file_content = staticmethod(
            lambda *a, **k: '{"modding-tool-version": "9.9.9"}')
        assert VersionManager.check_version("3.1.0") is False

        GitHubManager.get_file_content = staticmethod(
            lambda *a, **k: '{"modding-tool-version": "3.1.0"}')
        assert VersionManager.check_version("3.1.0") is True

        GitHubManager.get_file_content = staticmethod(lambda *a, **k: None)
        assert VersionManager.check_version("3.1.0") is False

        GitHubManager.get_file_content = staticmethod(lambda *a, **k: "not json")
        assert VersionManager.check_version("3.1.0") is False
    finally:
        builtins.input = original_input
        GitHubManager.get_file_content = original_fetch


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

    assert 'editor' not in cfg['directory_names']
    assert 'uploader_asset' not in cfg['asset_names']
    assert cfg['asset_names']['convenience_pack'] == 'ConvaiConveniencePack'


def test_tool_version():
    """T-CFG-6: the exe's version and the one it fetches to compare against must match.

    Value-agnostic on purpose - the release bump is the user's. This only catches one of
    the two files moving without the other, which would block every exe on boot.
    """
    import ConvaiModdingTool

    with open(os.path.join(REPO_ROOT, 'Version.json'), encoding='utf-8') as handle:
        shipped = json.load(handle)['modding-tool-version']

    assert ConvaiModdingTool.TOOL_VERSION == shipped, (ConvaiModdingTool.TOOL_VERSION, shipped)


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
    test_config_source_override()
    print('ok')
