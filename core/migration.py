"""Notes describing what an update changed when it migrated a project onto the V4 plugin."""
import os
from datetime import date
from typing import Optional

MIGRATION_NOTES_FILENAME = 'ConvaiMigrationNotes.md'


def is_v4_version(version: Optional[str]) -> bool:
    """True when a plugin VersionName belongs to the V4 line."""
    return bool(version) and version.split('.', 1)[0].strip() == '4'


def build_migration_notes(old_plugin_version: Optional[str],
                          new_plugin_version: Optional[str],
                          pack_removed: bool) -> Optional[str]:
    """
    Describe a destructive update, or return None when nothing worth reporting happened.

    Args:
        old_plugin_version: VersionName of the replaced plugin, 'unknown' if it could not
            be read, None if no Convai plugin was installed.
        new_plugin_version: VersionName of the freshly installed plugin.
        pack_removed: Whether a project-level Content/ConvaiConveniencePack was deleted.
    """
    if not pack_removed and (old_plugin_version is None or is_v4_version(old_plugin_version)):
        return None

    new_version = new_plugin_version or 'unknown'
    if old_plugin_version is None:
        plugin_line = (
            f"The Convai plugin was installed fresh into `Plugins/` at version {new_version}."
        )
    else:
        plugin_line = (
            f"The Convai plugin in `Plugins/` was deleted and replaced with V4: "
            f"{old_plugin_version} -> {new_version}."
        )

    pack_line = (
        "The project-level `Content/ConvaiConveniencePack` folder was removed. "
        if pack_removed else ""
    )

    return f"""# Convai modding tool - migration notes

This project was migrated by the Convai modding tool on {date.today().isoformat()}.
The changes below are not reversible, so read them before opening the project again.

## The Convai plugin was replaced

{plugin_line}

## The convenience pack moved into the plugin

{pack_line}The pack now ships inside the plugin and mounts at `/ConvAI/ConvaiConveniencePack/...`.
Any asset that still references `/Game/ConvaiConveniencePack/...` has to be repointed to
`/ConvAI/ConvaiConveniencePack/...` or it will fail to load. The tool repoints the
project's default game mode as part of the update.

## The plugin is now built from source

V4 ships no precompiled binaries, so this project compiles the plugin itself. The first
editor launch and the first build take noticeably longer, and a compile error inside the
plugin source now fails the whole project build.
"""


def write_migration_notes(project_dir: str, text: str) -> str:
    """Write the notes into the project so they outlive the tool window. Returns the path."""
    path = os.path.join(project_dir, MIGRATION_NOTES_FILENAME)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text)
    return path
