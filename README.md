# Convai Modding Tool

## Overview

A Windows GUI tool that sets up and maintains Unreal Engine projects for Convai
integration. It creates a project from the blank template, installs the Convai
plugins, wires up the API key and project settings, and builds the project.

The home screen is a project shelf: every modding project the tool can see, with
its engine version and asset type, and one-click Update and Migrate. A project is
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
- **Convai API key** - masked as you type. If you already have a project on the
  shelf, the tool offers to reuse the key stored in its `ModdingMetaData.txt`.
- **Asset type** - Scene or Avatar, with a MetaHuman option.
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

## Project structure

A project the tool creates or updates:

```
YourProject/
├── Config/                 # DefaultEngine.ini, DefaultGame.ini, DefaultInput.ini
├── Content/                # your project content
├── Plugins/
│   ├── ConvAI/             # V4 plugin source, compiled by UBT
│   ├── ConvaiHTTP/
│   ├── ConvaiPakManager/
│   └── <generated>/        # content-only plugin holding your uploaded assets
├── Source/                 # project sources and Target.cs files
├── ConvaiEssentials/       # ModdingMetaData.txt and downloaded archives
├── YourProject.uproject
└── ConvaiMigrationNotes.md # only written when an update migrated the project
```
