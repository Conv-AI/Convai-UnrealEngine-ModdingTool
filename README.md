# Convai Modding Tool

## Overview

A Windows GUI tool that sets up and maintains Unreal Engine projects for Convai
integration. It creates a project from the blank template, installs the Convai
plugins, wires up the API key and project settings, and builds the project.

The home screen is a project shelf: every modding project the tool can see, with
its engine version and Asset Type, and one-click Update and Migrate. A project is
any folder next to the tool's executable that contains a `ConvaiEssentials` folder
and a `.uproject` file, so keep the exe in the directory where your projects live.

## Requirements

- Windows
- Unreal Engine 5.8, installed through the Epic Games Launcher
- Internet access to GitHub - the tool reads its configuration and downloads the
  plugins at runtime
- No Linux cross-compilation toolchain is needed unless Linux packaging is turned
  on in the remote configuration. When it is off, the tool skips the toolchain
  entirely; you can still install it by hand from Settings.

## Using the tool

### New project

Fill in the form on the New project screen:

- **Name** - 1 to 20 characters, letters, digits and underscores only, cannot start
  with a digit, and cannot match a folder that already exists next to the exe.
- **Convai API key** - taken from the Convai account you are signed in to.
- **Asset Type** - Scene or Avatar, with a MetaHuman option. Fixed for the life of
  the project: the Pak Manager keys its publish payload off this string, and Update
  and Migrate read it back rather than asking again.
- **Unreal Engine path** - detected from the registry; Browse to point at a
  different installation. The path is validated before the run starts.

### Update

Update brings an existing project onto the current Convai V4 plugin. It is
destructive by design:

- installs the current Convai plugin from source, deleting whatever Convai plugin
  was there before
- removes the project-level `Content/ConvaiConveniencePack` folder - the pack now
  ships inside the plugin
- repoints `GlobalDefaultGameMode` to
  `/ConvAI/ConvaiConveniencePack/Sample/BP_SampleGameMode.BP_SampleGameMode_C`
- writes `ConvaiMigrationNotes.md` into the project when any of that actually
  changed something, and shows the same notes on the done screen

Update never touches `Plugins/<generated>/`, your Modding Plugin. The Pak Manager
copies the Entry Point's out-of-plugin dependencies into that folder and repoints
references at the copies, so deleting or regenerating it would break packages that
already point there.

Updating a project that is already on V4 changes nothing and writes no notes file.

Any of your own assets that reference `/Game/ConvaiConveniencePack/...` have to be
repointed to `/ConvAI/ConvaiConveniencePack/...` after an update, or they will fail
to load. That is what the notes file is there to remind you of.

### Migrate

Migrate moves a project to the target engine version. It runs the Update above
against the project's current engine, copies the project to `<Name>_<target>`
alongside it, retargets the copy to the new engine version, patches the sources for
the newer API, and builds it. The original project is left in place.

### Settings

Settings holds the manual **Install Linux toolchain** action, for when you need the
cross-compilation toolchain even though Linux packaging is off.

## What gets installed

| Plugin | Source |
| --- | --- |
| ConvAI | `Conv-AI/Convai-UnrealEngine-SDK-V4`, the `marketplace-*` no-binaries release whose asset matches your engine version |
| ConvaiHTTP | `Conv-AI/Convai-UnrealEngine-HTTP` |
| ConvaiPakManager | `Conv-AI/Convai-UnrealEngine-PakManager` |

The Convai plugin ships as source with no precompiled binaries, so UnrealBuildTool
compiles it as part of your project. The first build after a create or an update
takes noticeably longer than it used to, and a compile error inside the plugin
source now fails the whole project build.

If no `marketplace-*` release carries an asset for your engine, the tool falls back
to the compiled release for that engine and strips `Binaries/`, `Intermediate/` and
the `Installed` flag out of it, so both paths end up building from source.

## Publishing from the Pak Manager

Publishing is the Pak Manager plugin's job, not this tool's, but two of its rules
decide how you lay a project out.

**Publishable work goes in `Plugins/<generated>/Content/`** - your Modding Plugin.
The **Entry Point** you publish must live under that plugin's mount, and the Pak
Manager re-checks that at publish and at package, not only when you pick it. The
project's own `Content/` is scratch: anything you keep there and reference gets
*copied* into the Modding Plugin, leaving two copies that then drift apart.

**The dependency gather has one sharp edge.** When you pick an Entry Point, the Pak
Manager offers to copy its outside dependencies into the Modding Plugin and repoint
the references at the copies. Everything outside the plugin is copied - `/Game/`
content and engine content alike - except the Convai SDK's own `/ConvAI/` and
`/ConvaiHTTP/` mounts. The originals stay where they are, so from then on edit the
copies. Adding a new `/Game/` or engine reference **after** you picked the Entry
Point does not re-trigger the gather: re-pick the Entry Point, or use
**Dependencies...**, before you publish.

**One Chunk per project.** A second Asset means a second project.

## Troubleshooting

- **See the log** - run the exe with `--console` to keep the log console visible.
  Everything the tool logs also appears in the GUI's log panel.
- **Build failures** - UnrealBuildTool writes its own log to
  `%LOCALAPPDATA%\UnrealBuildTool\Log.txt`; that is where the real compile error is.
- **"No Convai plugin release is available for Unreal Engine x.y"** - there is no
  plugin build for that engine. Use a supported engine version. This check runs
  before any download, so it fails in seconds rather than after a large download.
- **"Update required" on launch** - your copy of the tool is older than the released
  version. Download the current release from the link on that screen; the tool will
  not run until you do.

## Development

```bash
pip install -r resources/requirements.txt   # Python 3.13
python ConvaiModdingTool.py [--console]
python tests/selfcheck.py                   # plain-assert self-checks, no network
scripts\Package.bat                         # builds dist/ConvaiAssetUploader.exe
```

The tool fetches `resources/modding_tool_config.json`, `resources/asset_uploader_config.json`
and `Version.json` from `main` at runtime. A config edit on `main` therefore reaches
every distributed exe immediately, which means config changes that depend on new code
must ship in the same release as that code, together with the `Version.json` bump.
`check_version` compares the version strings exactly, so a bump moves every user at once.

Only the first of the three is fatal when it cannot be fetched. `Version.json` falls back
to hardcoded engine versions, and the publish policy falls back to a copy of itself in
`core/config_manager.py`.

**Two of these files have a second reader.** The Pak Manager plugin, which ships on its own
schedule, fetches them straight off `main` too:

| File | Keys it reads | When |
| --- | --- | --- |
| `Version.json` | `target-ue-version` | every time its panel opens; banners on a Major.Minor mismatch with the running editor |
| `resources/asset_uploader_config.json` | `unreal-engine.<platform>.should-package`, `.configuration`, `raw-project-upload` | before every Publish; a failed fetch refuses the run |

So a merge to `main` touching either file is a production deploy for every installed
editor, with no plugin release in between. Both are shape-checked in `tests/test_config.py`;
that is a developer-local guard, not a merge gate. Note this tool itself reads only
`unreal-engine.linux.should-package` out of the policy - the rest is served, not consumed.

## Project structure

A project the tool creates or updates:

```
YourProject/
├── Config/                 # DefaultEngine.ini, DefaultGame.ini, DefaultInput.ini
├── Content/                # scratch - publishable work goes in the Modding Plugin
├── Plugins/
│   ├── ConvAI/             # V4 plugin source, compiled by UBT
│   ├── ConvaiHTTP/
│   ├── ConvaiPakManager/
│   └── <generated>/        # the Modding Plugin - what you publish lives here
├── Source/                 # project sources and Target.cs files
├── ConvaiEssentials/       # see below - never move, rename or delete this
├── YourProject.uproject
└── ConvaiMigrationNotes.md # only written when an update migrated the project
```

### ConvaiEssentials

**Never move, rename or delete this folder.** It is the only place the published Asset's
identity is recorded, and there is no recovery path if it is lost - no update, no delete,
just an orphaned Asset on Convai's side.

```
ConvaiEssentials/
├── *.zip                              # this tool's download scratch
└── ChunkId_<N>/
    ├── ModdingMetaData_<N>.json       # written by this tool
    ├── Draft_<N>.json                 # Pak Manager
    ├── Thumbnail_<N>.png              # Pak Manager
    └── Env_<host>_<8hex>/             # one per backend Environment
        ├── CreateAssetData_<N>.json   # THE AssetID - irreplaceable
        ├── PakMetaData_<N>.json       # Pak Manager
        └── RawArchive_<N>.txt         # Pak Manager
```

This tool writes `ModdingMetaData_<N>.json` and cleans up its own `.zip` files, and
touches nothing else under `ChunkId_<N>/`. A project set up by this tool uses Chunk 10,
the id the Pak Manager mints for a project's first Chunk. A project that still carries the
older flat `ConvaiEssentials/ModdingMetaData.txt` is left as it is - the Pak Manager
migrates it into the Chunk itself, and it knows the Chunk id.
