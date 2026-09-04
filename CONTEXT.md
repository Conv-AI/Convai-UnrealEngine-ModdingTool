# Context

Glossary for the Convai Unreal Engine Modding Tool. Language only — no
implementation detail, no decisions. Decisions live in `docs/adr/`.

## Plugin distribution

**Release pair** — one plugin version published to GitHub twice: a *compiled
release* and its *marketplace twin*. Both carry the same version; they differ
only in what they ship.

**Compiled release** — the half of a release pair that ships built binaries.

**Marketplace twin** — the half of a release pair that ships source without
binaries, tagged with a `marketplace-` prefix on the compiled release's tag.
This is the half the tool installs; when a version has no twin for the engine
in hand, the compiled half is installed and stripped back to source instead.

**Version** — what a release pair is *of*, named by the compiled release's tag
(`4.0.0-beta.24`). The unit humans talk about and the unit a pin names. Not to
be confused with either half's literal tag.

**Override** — configured instruction to install something other than what
normal resolution would pick for a plugin. Two independent kinds; either, both,
or neither may be set. Absent overrides, resolution is unchanged.

**Version pin** — an override naming the *version* to install. Names a version,
never a literal tag, and never changes how that version resolves into an asset.
The fleet-wide lever: it holds every user still on a known-good version.

**Asset pin** — an override naming one release artifact by exact filename,
reaching it directly rather than through pattern and engine matching. A
filename belongs to a single engine, so an asset pin is a local lever — one
machine, one artifact — not something held over the fleet.

**Unsatisfiable override** — an override naming a version or artifact that the
repository does not offer for the engine in hand. It stops the run; resolution
never falls back to what the override was set to avoid.
