# 2. Plugin overrides fail closed

**Status:** accepted, 2026-09-04

## Context

Plugin resolution walks backward through a repository's releases until it finds one carrying an
asset for the engine on disk (`core/github_manager.py:137`). An override exists because someone
decided that walk lands somewhere wrong: a **version pin** holds the fleet on a known-good build
while a regression is fixed, an **asset pin** reaches one artifact on one machine.

Leaving the walk-back in place under an override makes the override advisory. It silently installs
the exact thing the override was set to prevent, and says so in a warning line inside an otherwise
green run — which nobody reads.

## Decision

An override that cannot be satisfied stops the run. No walk-back, no fallback to newest. The error
names the override and why it could not be satisfied.

Inside a *satisfied* override, resolution is untouched. A pinned version with no marketplace twin
for this engine still installs the compiled half and strips it back to source, because a pin
constrains the version, not which half of the release pair is used.

An explicit pin also sees releases that automatic selection hides: the `prerelease` filter exists
to keep untested builds out of a *default* choice, and a pin is the deliberate override of the
default.

## Consequences

- A pin naming a version that does not cover every supported engine breaks builds for users on the
  engines it misses. That is the intended reading — those users get a run that refuses to start
  with the pin named in the error, not a plugin they were not meant to have.
- `convai_plugin` is in `CRITICAL_PLUGINS` (`core/download_utils.py:23`), so an unsatisfiable pin
  on it raises `DownloadError` and ends the run.
- The availability pre-check (`core/download_utils.py:225`) and the download must read the same
  override through one accessor. Two independent reads drift, and the drift surfaces as a
  pre-check that greenlights a ~400MB download the resolver then refuses.
- Config is fetched from `main` at runtime by every distributed exe, including builds that predate
  this feature and ignore the key entirely (`core/config_manager.py:122`). Version checking is
  advisory and nothing forces an update (`core/version_manager.py:53`), so a fleet-wide pin reaches
  only users on a tool version that understands it. A pin is a fix-forward lever, not a recall.
- An asset pin bypasses engine matching, which is the one thing `asset_patterns` cannot express
  (patterns are ANDed with the engine check at `core/github_manager.py:122`). A filename belongs to
  a single engine, so shipping an asset pin fleet-wide breaks every other engine by the rule above.
  It is a local lever, used through `CONVAI_MODDING_CONFIG_DIR`.
