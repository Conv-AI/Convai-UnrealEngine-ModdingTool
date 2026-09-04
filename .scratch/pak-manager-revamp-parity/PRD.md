# Catch the Modding Tool up with the Pak Manager revamp

Status: `ready-for-agent`
Re-verified 2026-09-04 against Pak Manager `feat/legacy-parity` @ `421a6b2` and this repo @ `cba4355`.

The Pak Manager plugin was rewritten: the Blueprint/EUW tool is gone, replaced by a Slate nomad
tab; content is discovered as **Chunks** from Primary Asset Labels; server records are partitioned
per backend **Environment**; the Publish runs on the plugin's own runner.

Repo A below = the Pak Manager plugin. Repo B = this repo.

---

## P0

### 1. `get_metadata` reads a path the plugin moves out from under it

*`core/file_utility_manager.py:232` and `:265` both resolve `config.get_metadata_file_name()`, which
is `"ModdingMetaData.txt"` (`resources/modding_tool_config.json:67`, `core/config_manager.py:289`).*

The plugin migrates the flat layout into the per-Chunk one on boot and on every panel refresh,
**moving** rather than copying:

```
ConvaiEssentials/ModdingMetaData.txt   →   ConvaiEssentials/ChunkId_<N>/ModdingMetaData_<N>.json
```

Its read order is:

1. `ConvaiEssentials/ChunkId_<N>/ModdingMetaData_<N>.json`
2. `ConvaiEssentials/ChunkId_<N>/ModdingMetaData_<N>.txt`
3. `ConvaiEssentials/ModdingMetaData.txt` (flat, last resort — still present at HEAD)

This repo reads **only** path 3. Once a creator has opened the Pak Manager on a project that has a
Chunk, `get_metadata` returns `{}`, so `plugin_name` / `asset_type` / `api_key` come back `None` and
Update and Migrate fail.

**Do:** resolve in the plugin's order, discovering `<N>` by globbing
`ConvaiEssentials/ChunkId_*/ModdingMetaData_*.json` rather than hardcoding it. `<N>` is whatever the
Primary Asset Label declares — 10 for a creator project, but internal projects carry others.

**The content and keys are unchanged.** The file was always JSON inside a `.txt`. The plugin still
pulls exactly three keys by hand — `project_name`, `plugin_name`, `asset_type` — and ignores
`api_key` and `is_metahuman`, which this tool still needs, so keep writing them. You should now place the metadata file ConvaiEssentials/ChunkId_10/ModdingMetaData_10.json

`asset_type` now matters more than it did. Commit `820b49b` pinned the publish payload in tests, and
the Scene/Avatar branch keys off this string: it is matched case-insensitively against `Scene`, and
**anything else at all is treated as an Avatar**, sending tags `["Pak","Avatar"]` instead of
`["Pak","ConvaiSim","Background3D","Scene"]`. Keep the literals exactly `"Scene"` and `"Avatar"`.

One related constraint from the same payload work: `content_path` is composed as
`../../../<project basename>/Plugins/<plugin_name>/Content/`, so the Modding Plugin must stay at
`<Project>/Plugins/<plugin_name>/`.

### 2. Where to WRITE it is a bootstrap trap — do not "just" move the write

The obvious change — write `ChunkId_10/ModdingMetaData_10.json` and drop the flat file — **bricks a
fresh project**. A generated project has no Primary Asset Label, so the plugin finds no Chunk,
`GetSoleChunkId()` is `INDEX_NONE`, and the read resolves `ChunkId_-1/ModdingMetaData_-1.json`. It
never globs `ChunkId_*`. The plugin's own "Create chunk" button reads `plugin_name` through that
same call and refuses:

> this project records no modding plugin, so the Pak Manager cannot say where its chunk's label
> belongs; add a Primary Asset Label by hand

The flat `.txt` is the **bootstrap** — the only thing that lets the plugin mint the label. See
*Decisions* for the routes. Whichever is chosen, item 1's read side changes regardless.

---

## P1 — worth doing, plugin currently papers over it

### 4. Generate the Modding Plugin's `.uplugin` with ConvAI already declared

`create_content_only_plugin` (`core/unreal_engine_manager.py:222-240`) writes a descriptor with no
`Plugins` array. Unreal's `AssetValidator_AssetReferenceRestrictions` then rejects the `/ConvAI/`
references the Pak Manager adds to every Avatar blueprint.

Commit `71aa9b4` made the plugin repair this itself (`EnsureConvaiDependency` rewrites the
descriptor through `IPlugin::UpdateDescriptor`), so this is belt-and-braces — but it **warns rather
than refuses**, and the repair cannot land when the file is read-only or checked in under source
control. Generating it correctly turns the repair into a no-op.

**Do:** add `'Plugins': [{'Name': 'ConvAI', 'Enabled': True}]` to that dict. The literal is
`ConvAI` — capital A, capital I, matching `ConvAI.uplugin`, which is already how
`resources/modding_tool_config.json` spells it. The plugin's matcher is case-insensitive, so an
existing enabled entry makes its repair a no-op.

### 5. Never delete or regenerate `Plugins/<PluginName>/` on Update or Migrate

New constraint, and it is easy to violate by accident. Since `770177a` the Pak Manager copies every
out-of-plugin dependency of the Entry Point **into** that folder and repoints the references —
everything except the Convai SDK mount and `/ConvaiHTTP/`, engine content included. Deleting or
recreating the folder destroys gathered copies that other packages have already been repointed at.

`update_modding_dependencies` is correct today (it deletes only the Convai plugin, ConvaiHTTP,
ConvaiPakManager, a stale project-level `Content/ConvaiConveniencePack`, and `ConvaiEssentials/*.zip`).
The requirement is to keep it that way, and to say so where the Update flow is documented.

### 6. The Entry Point must live under `/<PluginName>/`

Three things to get right about the scope of this rule:

- It gates the **Entry Point package only**, not all content. `/Game/` and engine dependencies are
  legal — the gather copies them in.
- It is not only a pick-time gate. The same refusal runs on every publish and package, so an Entry
  Point moved out of the plugin after picking refuses the publish outright.
- The match is `StartsWith("/" + PluginName + "/")`, deliberately not `Contains`, so
  `/Game/<PluginName>_old/` is refused.

(ADR-0011 argues this from "a Pak holds only its own mount". **That premise was retracted on
2026-09-04** — a real Pak carries 1921 files across four mounts. The code is unchanged, so the
requirement stands; read the ADR's correction banner before citing its reasoning.)

### 7. `ConvAI.uplugin` and `ConvaiHTTP.uplugin` are frozen filenames

Repo A resolves the SDK mount by `FindPlugin("ConvAI")` with a hardcoded `/ConvAI/` fallback, and
`/ConvaiHTTP/` is a bare literal with no lookup at all. These two mounts are the *only* exclusions
from the dependency gather. Rename either descriptor and that plugin's content stops being excluded
— the gather starts copying it into every creator's Modding Plugin, silently.

The same literal is why the Convenience Pack must stay inside the SDK plugin, mounting at
`/ConvAI/ConvaiConveniencePack/`. Repo A loads `BP_ConvaiChatbotComponent` from that root and has no
`/Game/` fallback, and since `8bd838f` the entry-point check runs at publish and package as well as
at the pick — so a project whose pack sat under `/Game/` would fail all three.

---

## P2 — this repo serves TWO production endpoints

Both are fetched anonymously from `main` by every creator's editor. Neither has a cached or
compiled-in fallback that a creator can set — the plugin's pins are compiled-in constants, described
in its own header as *"Constants, not settings - values that never change."*

### `resources/asset_uploader_config.json` — the Publish Policy

```
raw.githubusercontent.com/Conv-AI/Convai-UnrealEngine-ModdingTool/main/resources/asset_uploader_config.json
```

Fetched **before every Publish**. A failed fetch **refuses the run**, deliberately (ADR-0004).

- **Never rename, move or delete it**, and never change its shape. It is an API.
- **A packaged platform must always name a `configuration`.** The parser clears `Configuration`
  before each platform block, so a JSON policy can never inherit the `"Shipping"` default that typed
  overrides get. `should-package: true` with no `configuration` refuses the **whole** policy:
  *"the publish policy asks to package Windows but names no configuration"*.
- **Never commit all three of** `windows.should-package`, `linux.should-package` and
  `raw-project-upload` **as false** — a policy that would produce nothing is treated as a misread.
  Archive-only (both platforms false, raw true) is valid.
- **A merge to `main` touching this file is a production deploy.** `c0569d4 chore: disable linux
  packaging` was exactly that.

### `Version.json` — the engine pin

```
raw.githubusercontent.com/Conv-AI/Convai-UnrealEngine-ModdingTool/main/Version.json
```

Fetched on **every Pak Manager panel open**. The plugin reads exactly one key out of it:
`"target-ue-version"`, compares it to the running editor on **Major.Minor only** (patch ignored, so
`5.8.1` matches `5.8`), and banners on a mismatch:

> This project runs Unreal {engine}; Convai targets {target}. Paks built here may not load in Convai
> products.

It **fails open** — unreachable network, missing key, or unparseable value produces no banner rather
than a false one. That is also the danger: a typo is silent on both sides.

- Keep the file at the **repository root**, spelled `Version.json` (raw.githubusercontent is
  case-sensitive), on `main`, in a public repo.
- Keep `"target-ue-version"` a JSON **string** of the form `Major.Minor`.
- **Do not raise it ahead of the engine Convai's runtime actually consumes Paks from.** The moment
  it moves, every installed creator sees that banner — with no plugin release in between.
- **Nothing here guards it.** The release pipeline only checks `modding-tool-version`. Add an
  assertion beside `test_tool_version` that `target-ue-version` exists, is a string, and matches
  `^\d+\.\d+$`.

### The other banner names this tool as the fix

> Pak Manager {installed} is installed and {latest} is available. **Update it with the Convai Modding
> Tool before publishing.**

That instruction is only true while Update keeps re-downloading the *latest* Pak Manager release. Do
not pin `convai_pak_manager` to a fixed tag and do not turn Update into an in-place patch. It works
today; the requirement is to keep it working.

One known wrinkle, documented rather than chased: Repo A compares against `ConvaiPakManager.uplugin`
on **`main`**, not the latest release, so during a window where `main` is bumped and the release job
has not finished, creators can be nagged about a version this tool cannot install yet. That is
Repo A's flagged shortcut, not a bug here — do not add version-chasing logic.

### Write no ini keys for the Publish Policy

Still nothing to write; every plugin C++ default is already the creator-correct value. The existing
`PrimaryAssetTypesToScan` entry with `(Path="/<PluginName>")` **is** still wanted — the plugin re-adds
the same entry idempotently and early-returns when it is already listed.

`resources/ui_message.json` still appears genuinely dead — nothing in either repo references it.
Verify, then drop it.

---

## P3 — docs still owed

- **`ConvaiEssentials` must never be moved, renamed or deleted.** ADR-0005 puts this warning in
  *this tool's* documentation. ADR-0010 sharpens it: the AssetID lives only in
  `ConvaiEssentials/ChunkId_<N>/Env_<slug>/CreateAssetData_<N>.json`, once **per Environment**.
  Losing it orphans the published Asset permanently — no update, no delete, no recovery path.
- **One Chunk per creator project.** A creator needing a second Asset makes a second project.
- **Where publishable work goes**: `Plugins/<UniqueName>/Content/`. The project's own `Content/` is
  scratch — anything a creator puts there and references gets *copied* into the Modding Plugin by
  the gather, leaving two divergent copies.
- **The gather modal, and its one sharp edge.** On picking an Entry Point the Pak Manager may offer
  to copy outside dependencies in and repoint at the copies; the originals stay put, so from then on
  edit the copies. **Adding a `/Game/` or engine reference after picking does not re-trigger this**
  — re-pick the Entry Point, or use **Dependencies…**, before publishing.
- **Terminology**: "content plugin" / "content-only plugin" → **Modding Plugin**; keep **Asset Type**
  capitalised as a defined term, fixed for the life of the project. If this repo ever gains a URL
  setting, the term is **Environment**, derived from the resolved base URL, never configured.
- **`Version.json` and `asset_uploader_config.json` have a second consumer.** Wherever the README
  explains what `main` serves at runtime, say that the Pak Manager plugin — shipping on its own
  schedule — reads them, and name the keys.

The on-disk tree, for the warning to name real things:

```
ConvaiEssentials/
├── *.zip                              # this tool's download scratch
└── ChunkId_<N>/
    ├── ModdingMetaData_<N>.json       # written by this tool
    ├── Draft_<N>.json                 # plugin-owned
    ├── Thumbnail_<N>.png              # plugin-owned
    └── Env_<host>_<8hex>/             # e.g. Env_api.convai.com_29e2cb96
        ├── CreateAssetData_<N>.json   # THE AssetID — irreplaceable
        ├── PakMetaData_<N>.json
        └── RawArchive_<N>.txt
```

Nothing under `ChunkId_<N>/` other than `ModdingMetaData_<N>.json` may be written, moved or cleaned
by this tool. The existing zip cleanup is a non-recursive `os.listdir` filtered to `.zip`, so it is
already safe — keep it that way.

---

## Decisions needed

1. **Bootstrap route** (blocks P0 item 2):
   - **(A)** Keep writing the flat `ConvaiEssentials/ModdingMetaData.txt` while no `ChunkId_*/`
     exists; the plugin's migration moves it on the creator's first "Create chunk". Needs nothing
     from Repo A. Cost: a freshly generated project opens showing the legacy-recovery banner with
     Publish disabled until the creator presses one button.
   - **(B)** Author the label here and write the per-chunk JSON directly. The shipped values to
     match are `PAL_<PluginName>` at the plugin content root, `bLabelAssetsInMyDirectory=true`,
     `bIsRuntimeLabel=true`, `Priority=0`, `bApplyRecursively=true`, `CookRule=AlwaysCook` — all
     confirmed verbatim against the plugin's `EnsureLabel`. Two caveats:
     `ChunkId = 10` is the *caller's* choice for the first Chunk (the plugin uses
     `Existing.IsEmpty() ? 10 : Existing.Last() + 1`, and leaves any label that already declares an
     id alone); and the scan-directory half is **already done** here — `Directories=((Path="/Game"),
     (Path="/<PluginName>"))` — so do not drop it. Cost went up: commit `c9a9693` **deleted**
     Repo A's `Scripts/create_primary_asset_label.py`, so there is no reference implementation left
     to copy, and this tool never launches the editor.
   - **(C)** Ask Repo A to glob `ChunkId_*/ModdingMetaData_*.json` when the ChunkId is unknown,
     letting this tool go per-chunk-only with no label.

   (A) is smallest and needs nothing from Repo A. (C) is the cleanest end state.

2. **Whose definition of `target-ue-version` wins?** This repo uses it as *the engine the Modding
   Tool migrates projects to* — a lever raised **first**. Repo A reads it as *the engine Convai's
   runtime consumes Paks from* — a fact that changes **last**. Both are `"5.8"` today, so the
   conflict is latent. If they must diverge, either Repo A reads `current-ue-version` instead, or
   this repo gains a third key.

3. **Should either endpoint stay on `main`?** Both `PolicyRef` and the compatibility `SourceRef` are
   `"main"`, so both files reach every installed editor the instant they merge, with no review gate
   on either side. Keep `main` and gate the files behind CODEOWNERS, or ask Repo A to point at tags
   this repo cuts.

---

## Out of scope

- **The `/CharacterParts/` dangling reference**, if a data-validation pass surfaces it. A copied
  MetaHuman ControlRig soft-references a mount no consumer project has; the path is baked into the
  source asset the creator's own MetaHuman export shipped, before any gather runs. No plugin to
  enable, no content to ship — it is Repo A's decision (drop the reference, or refuse the pick).
- **Thumbnail dimensions.** Repo A-only, and the 512×1024 shape is itself awaiting Anmol's
  confirmation, so do not pin a size in documentation here yet.

---

## Verification

Nothing here has been executed against a running editor. Suggested proof:

- Generate a fresh project; assert `Plugins/ConvaiPakManager/` exists, that a non-MetaHuman Avatar
  project has the Reallusion content, and that `Plugins/ConvAI/Content/MetaHumans` survives.
- Assert the generated `<PluginName>.uplugin` declares `ConvAI`.
- Open it in 5.8; the Pak Manager tab must appear under Tools with no load errors and no
  compatibility banner.
- Press "Create chunk", then run Update — it must still find `plugin_name`.
- Pick an Avatar blueprint as the Entry Point; it must be accepted.

## Sources

Repo A @ `421a6b2`: `CONTEXT.md`; `docs/adr/0003`, `0004`, `0005`, `0009`, `0010`, `0011` (read its
2026-09-04 correction banner), `0012`; `.scratch/legacy-parity/PRD.md`;
`.scratch/backend-environments/PRD.md`; `.scratch/overnight-fixes/` (PRD + issues 01, 02, 07, 12, 15);
`.scratch/dependency-gather/issues/01`; `docs/handoff/2026-09-03-dependency-gather.md`;
`Source/ConvaiPakManager/Private/Chunk/CPM_Chunk.cpp`; `Private/Avatar/CPM_AvatarBlueprint.cpp`;
`Private/Publish/CPM_PublishTypes.cpp`; `Public/Publish/CPM_Compatibility.h`;
`Public/CPM_PakManagerSettings.h`; `Public/Jobs/CPM_PublishRunner.h`; `.github/workflows/release.yml`.
