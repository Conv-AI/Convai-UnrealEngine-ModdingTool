"""
Compatibility Patcher — applies regex compatibility patch rules to a migrated /
updated project's source before building, fixing UE API-break compile errors in
the embedded ConvAI plugin.

Only ever edits the embedded ConvAI plugin source and the project's own Target.cs
files — never the helper plugins, which are fixed upstream. See patch_rules.py.

Failure model: best-effort and non-blocking. A rule that matches nothing is
normal (source already fixed). Unreadable/unwritable files are warned and skipped
without aborting the pass. Never blocks the build.
"""

import os
import re
import fnmatch

from core.logger import logger
from core.patch_rules import get_rules_for_engine

# Only these source files are considered for patching.
_SOURCE_EXTS = (".cpp", ".h", ".hpp", ".inl", ".cs")

# Build output / VCS dirs are skipped for speed and safety.
_SKIP_DIRS = {
    ".git", "Binaries", "Intermediate", "Saved", "DerivedDataCache",
    ".venv", "PackgedApp", "PackagedApp",
}


class CompatibilityPatcher:
    """Applies compatibility patch rules to a project's source tree."""

    def __init__(self, project_dir):
        self.project_dir = project_dir

    def _iter_source_files(self):
        """
        Yield (abs_path, rel_posix_lower) for every source file under the project
        directory, skipping build-output directories.
        """
        for root, dirs, files in os.walk(self.project_dir):
            # Prune skip dirs in place so os.walk does not descend into them.
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for name in files:
                if not name.lower().endswith(_SOURCE_EXTS):
                    continue
                abs_path = os.path.join(root, name)
                rel = os.path.relpath(abs_path, self.project_dir).replace(os.sep, "/")
                yield abs_path, rel, rel.lower()

    def apply_rules(self, target_engine_version):
        """
        Apply every rule for the target engine version (plus always-on rules) to
        the project source. Returns the total number of substitutions made.

        Best-effort and non-blocking: exceptions per file/rule are logged and
        skipped; the method does not raise.
        """
        rules = get_rules_for_engine(target_engine_version)
        if not rules:
            logger.info(f"No compatibility patch rules for engine {target_engine_version}")
            return 0

        # One directory walk; reused across all rules.
        source_files = list(self._iter_source_files())
        total_subs = 0

        for rule in rules:
            name = rule.get("name", "<unnamed>")
            try:
                pattern = re.compile(rule["pattern"], rule.get("flags", 0))
            except re.error as e:
                logger.warning(f"Compatibility rule '{name}': invalid regex, skipping: {e}")
                continue

            glob_lower = rule["file_glob"].lower()
            replacement = rule["replacement"]
            rule_subs = 0
            changed_files = 0

            for abs_path, rel, rel_lower in source_files:
                if not fnmatch.fnmatch(rel_lower, glob_lower):
                    continue
                try:
                    with open(abs_path, "r", encoding="utf-8") as f:
                        content = f.read()
                except Exception as e:
                    logger.warning(f"Compatibility rule '{name}': cannot read {rel}: {e}")
                    continue

                new_content, n = pattern.subn(replacement, content)
                if n == 0 or new_content == content:
                    continue

                try:
                    with open(abs_path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                except Exception as e:
                    logger.warning(f"Compatibility rule '{name}': cannot write {rel}: {e}")
                    continue

                rule_subs += n
                changed_files += 1
                logger.debug(f"Compatibility rule '{name}': {n} site(s) in {rel}")

            if rule_subs:
                logger.info(
                    f"Compatibility rule '{name}': {rule_subs} substitution(s) "
                    f"across {changed_files} file(s)"
                )
                total_subs += rule_subs

        if total_subs:
            logger.info(
                f"Compatibility patching complete: {total_subs} total substitution(s) "
                f"for engine {target_engine_version}"
            )
        else:
            logger.info(f"Compatibility patching: no changes needed for engine {target_engine_version}")
        return total_subs


def patch_source_files(project_dir, target_engine_version):
    """
    Module-level convenience: patch the ConvAI plugin source under project_dir for
    the given target engine version. Returns the total number of substitutions.

    Args:
        project_dir: project root (the folder containing the .uproject).
        target_engine_version: e.g. "5.8".
    """
    if not project_dir or not os.path.isdir(project_dir):
        logger.warning(f"Compatibility patcher: project dir not found: {project_dir}")
        return 0
    return CompatibilityPatcher(project_dir).apply_rules(target_engine_version)
