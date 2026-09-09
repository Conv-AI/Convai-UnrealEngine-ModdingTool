# HTTP dependency selection for Cloud Avatars

The V1 Unreal editor uploader reads the existing remote `github.convai_http_plugin` configuration before each package/upload operation and before a new download. It resolves one compatible HTTP archive for the operation, verifies its SHA-256, and reuses unchanged downloads and builds. It never downloads a replacement for the user's Convai SDK.

The `cloud_avatars` extension is ignored by the V0 Python resolver. Existing repository, asset patterns, and version/asset overrides retain their V0 meaning.

- `protocol` identifies the expected transfer commandlet contract.
- `engine_versions` lists tested Unreal major/minor versions.
- `sha256` verifies the selected archive. A release asset's GitHub `sha256:` digest may supply this when no explicit checksum is configured.
- `source_commit` selects an immutable source ZIP from the configured HTTP repository for development. It requires an explicit SHA-256. Omit it for normal release-asset resolution through the existing `override.version` / `override.asset` fields.

The staging configuration selects HTTP `staging-v1.2.0`, asset `Convai-UnrealEngine-HTTP.zip`, with its exact checksum. It includes source and precompiled UE5.8 Windows editor DLLs for installed BuildId `55116800`. The transfer module is integrated into HTTP `stg`; the release is a prerelease and does not replace latest stable. Main/production configuration is unchanged.

The V1 staging editor defaults to `staging`. Development can use `CONVAI_MODDING_CONFIG_BRANCH` to select another explicit branch. `CONVAI_MODDING_CONFIG_DIR` permits a local checkout root or flat offline fixture. Existing V0 branch-selection behavior is unchanged.

Top-level `cloud_avatars.project_profile_url` selects the declarative project profile extracted from V0. V1 snapshots this profile, the original modding config, `asset_uploader_config.json` and `Version.json` before an operation. It never executes downloaded Python. Current supported and future migration-target engines remain separate.

The optional archive `Resources/Transfer/prebuilt.json` records platform, configuration, Unreal version/BuildId and SHA256 hashes for both HTTP editor DLLs and their module receipt. A matching build installs without compilation. Other engine builds require compatible binaries or the source fallback; invalid binary hashes fail rather than loading. These are editor/commandlet binaries, not Shipping game binaries.

The resolved archive remains fixed for all source/platform transfers belonging to the operation. A later operation checks configuration again. A failed check, incompatible manifest, or checksum mismatch stops preparation with an actionable error and keeps cached files; it does not silently select an older dependency.
