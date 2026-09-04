# Pin a specific plugin release, per plugin

Status: `ready-for-agent`
Designed 2026-09-04 against this repo @ `68f36cc`. Decision record: [ADR 0002](../../docs/adr/0002-plugin-overrides-fail-closed.md).
Glossary: [CONTEXT.md](../../CONTEXT.md) — *release pair*, *compiled release*, *marketplace twin*,
*version*, *override*, *version pin*, *asset pin*, *unsatisfiable override*.

Today every plugin installs whatever resolution picks, and there is no way to hold one still. Two
levers are wanted:

- **A — fleet pin.** "beta.29.1 regressed; hold everyone on beta.29 until we ship a fix." Lands in
  `resources/modding_tool_config.json` on `main`, reaches users on the next launch.
- **B — local lever.** A dev builds against an older SDK, or grabs one specific zip. Already served
  by `CONVAI_MODDING_CONFIG_DIR=<checkout>` (`core/config_manager.py:105`), which reads the same
  file off disk. Same config key, no separate mechanism.

Use case C — an end-user version dropdown — is explicitly **out of scope**.

---

## What "latest" means today

Two resolution paths, not one. Both must honour the override.

| Plugin | Path | Picks |
|---|---|---|
| `convai_plugin` | `github_manager.py:250-262` → `resolve_plugin_release` | newest **marketplace twin of the newest compiled release** carrying an asset for this engine, walking backward until one matches. Never calls `/releases/latest`. |
| `convai_http_plugin`, `convai_pak_manager` | `github_manager.py:264-286` | `/releases/latest` + first `asset_patterns` substring hit |

`/releases/latest` ≠ `releases[0]` — the endpoint skips prereleases and drafts, the listing does
not. Do **not** unify the two paths onto a listing; that silently changes what "latest" means for
HTTP and PakManager.

---

## Config schema

One optional `override` object per plugin, sibling to the existing keys. Both members optional and
independently settable. Absent `override` → behaviour byte-identical to today.

```jsonc
"convai_plugin": {
  "repo": "Conv-AI/Convai-UnrealEngine-SDK-V4",
  "asset_patterns": ["-marketplace-no-binaries.zip"],
  "marketplace_prefix": "marketplace-",
  "engine_specific": true,
  "post_process": true,
  "override": {
    "version": "4.0.0-beta.24",              // the compiled tag, never the twin tag
    "asset": "Convai-UE5.8-hotfix.zip"       // exact filename; local lever only
  }
}
```

`version` names a **version**, not a literal tag. On `convai_plugin` that is the compiled release's
tag and the pair logic still runs against it; on the other two, where there are no pairs, the
version *is* the tag.

---

## Semantics

| Override set | Resolution |
|---|---|
| none | unchanged |
| `version` | resolve that version exactly as today's logic resolves the newest one — twin preferred, compiled half + source strip as fallback, engine matching applied. No walk-back to any other version. |
| `asset` | newest release containing that filename, scanning the cached listing newest-first. Engine matching **bypassed** — that is the point; patterns cannot reach an asset lacking a `ue5.8`-shaped token because `find_matching_asset` ANDs the engine check (`github_manager.py:122`). |
| both | that version's release pair, that filename |

Fail-closed rules, per ADR 0002:

- Version or asset not found for the engine in hand → return `None`, log an error naming the
  override and the reason. No fallback. On `convai_plugin` this ends the run with `DownloadError`
  via `CRITICAL_PLUGINS` (`download_utils.py:23`).
- A pinned version flagged `prerelease: true` **resolves**. The filter at
  `github_manager.py:146-150` guards automatic selection only; it must not participate in a pin.
- A `version` starting with the plugin's `marketplace_prefix` is a **config error**, not a lookup.
  Message names the value that was meant: `pin the version 4.0.0-beta.24, not the twin tag
  marketplace-4.0.0-beta.24`.

---

## Work

### 1. Config accessor

*`core/config_manager.py:236` — matches the shape of `get_github_asset_patterns`.*

**Do:** add `get_github_override(plugin_name) -> dict` returning `self.get(f'github.{plugin_name}.override', {})`.
One accessor, used by both call sites below. Two independent reads of the key will drift, and the
drift shows up as a pre-check that greenlights a download the resolver then refuses.

### 2. Resolver

*`core/github_manager.py:135-176` — `resolve_plugin_release`.*

**Do:** take `version: str = None` and `asset: str = None`. When `version` is set, select the pair
by tag rather than by position — build `compiled` from the whole listing without the `prerelease`
filter for that lookup — and drop the backward walk. When `asset` is set, match by exact filename
and skip `asset_matches_engine`. Return `None` on any unsatisfiable override.

### 3. Download entry point

*`core/github_manager.py:229-232` — `download_plugin_from_release`.*

The signature already carries `version: str = None`, documented "Specific version tag, or None for
latest", already routed to `/releases/tags/`. `if marketplace_prefix:` wins first, so it is
silently ignored on the SDK path — the defect this feature closes.

**Do:** reuse `version`, make it apply on **both** paths, add `asset` beside it. On the
non-marketplace path: `version` alone stays a `/releases/tags/` hit; `asset` alone requires the
cached listing (`get_releases`) to find the newest release containing it; no override stays
`/releases/latest`.

### 4. Call sites

*`core/download_utils.py:162` and `core/download_utils.py:225-247`.*

**Do:** read the override via §1 in `download_plugin_from_github` and pass it down. Do the same in
`check_convai_plugin_available` — it is the pre-flight gate before a ~400MB download and must reach
the same verdict as the download.

Keep the layering: `download_utils` reads config, `github_manager` takes explicit arguments and
stays config-agnostic. That is what lets `tests/test_plugin_download.py` seed releases and call the
statics directly.

### 5. Documentation

**Do:** note in the config file or `docs/` that a fleet pin only reaches users whose tool version
understands the key — old exes fetch the same config from `main` and ignore it. Deliberate; see
ADR 0002. No forced update, no gating on tool version.

---

## Tests

`tests/test_plugin_download.py` — plain asserts, no network, seeded config, `T-DL-N` docstrings.

| # | Case | Guards |
|---|---|---|
| 1 | `check_convai_plugin_available` and the download agree on the same override — both pass or both fail | the only failure that costs a user ten minutes and 400MB before showing itself. **Write this first.** |
| 2 | version pin picks the pinned pair's twin, not the newest | pin selects a version |
| 3 | pinned version whose twin lacks the engine → **that version's compiled half** + strip, not another version | a pin constrains the version, not the half |
| 4 | pinned version covers no asset for the engine → `None`, no walk-back; through `download_plugin_from_github` → `DownloadError` | fail closed |
| 5 | pin to a `prerelease: true` release resolves | the filter guards defaults only |
| 6 | `version` starting with `marketplace-` → config error naming the right value | the 2am mistake |
| 7 | asset pin picks an asset carrying no `ue5.8` token on an engine-specific plugin | the one thing patterns cannot do |
| 8 | asset pin alone → newest release containing that filename | no accidental version pin |
| 9 | no override → the existing tests pass unchanged | regression |

`tests/test_config.py:130-145` asserts the shipped config's shape.

**Do:** assert well-formedness only — if `override` is present, known keys only and `version` does
not start with `marketplace-`. Do **not** assert that no pin is committed; that guard would have to
be disabled every time a real pin ships, and would then stay disabled.
