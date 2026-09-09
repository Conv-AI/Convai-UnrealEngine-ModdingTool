# HTTP dependency selection for Cloud Avatars

The V1 Unreal editor uploader reads the existing remote `github.convai_http_plugin` configuration before each package/upload operation and before a new download. It resolves one compatible HTTP archive for the operation, verifies its SHA-256, and reuses unchanged downloads and builds. It never downloads a replacement for the user's Convai SDK.

The `cloud_avatars` extension is ignored by the V0 Python resolver. Existing repository, asset patterns, and version/asset overrides retain their V0 meaning.

- `protocol` identifies the expected transfer commandlet contract.
- `engine_versions` lists tested Unreal major/minor versions.
- `sha256` verifies the selected archive. A release asset's GitHub `sha256:` digest may supply this when no explicit checksum is configured.
- `source_commit` selects an immutable source ZIP from the configured HTTP repository for development. It requires an explicit SHA-256. Omit it for normal release-asset resolution through the existing `override.version` / `override.asset` fields.

This draft config points to a candidate on the HTTP feature branch containing the editor commandlet and the five existing `stg` streaming commits. It is a development dependency, not a published release. Before promoting to the released `main` config, validate the compatible HTTP release, replace the candidate source selection with the intended release/asset and its checksum, and retain the tested protocol/engine metadata.

Development uses the existing `CONVAI_MODDING_CONFIG_BRANCH` override to select this config branch. `CONVAI_MODDING_CONFIG_DIR` permits explicit offline fixtures. Released builds read `main`; changing a development branch does not silently activate the candidate for V0 releases.

The resolved archive remains fixed for all source/platform transfers belonging to the operation. A later operation checks configuration again. A failed check, incompatible manifest, or checksum mismatch stops preparation with an actionable error and keeps cached files; it does not silently select an older dependency.
