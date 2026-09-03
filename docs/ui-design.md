# Convai Modding Tool — UX/UI redesign specification

## Purpose and scope

This document is the implementation contract for a redesign of `gui/app.py`. It
keeps the current capabilities and flows (boot, project discovery, create,
update, migrate, run log, and settings), but changes their presentation so a
first-time Unreal user can understand the next safe action without reading
documentation.

The target is the existing **Windows Tkinter desktop application**, not a web
application. The companion [visual reference](ui-design-preview.html) is a
static HTML mock-up; it is not intended to be shipped.

## UX goals

1. Make the landing screen answer three questions within a glance: *where am
   I*, *is my Unreal setup ready*, and *what can I do next*.
2. Keep one clear primary action per screen. Destructive or slow actions must
   name their target project and explain their effect before they begin.
3. Expose an unavailable action's reason in text. Do not leave users to infer
   why a disabled button cannot be used.
4. Preserve logs for technical users while leading ordinary users with plain
   progress and recovery guidance.
5. Support a comfortable 100% Windows display at 920 × 640 and scale cleanly
   to 1280 × 800. No horizontal scrolling.

## Information architecture

```
Application shell
├── Boot / start check
├── Project shelf (home)
│   ├── Empty state
│   ├── Project list
│   ├── Selected-project inspector
│   └── Engine-status banner
├── New project (three-stage form)
├── Action review (Update or Migrate)
├── Activity / result
└── Settings dialog
```

Navigation rules:

- The product wordmark in the top bar returns to the project shelf, unless a
  run is active.
- `Esc` returns from New project and Action review after discarding no data;
  it does not cancel an active run.
- A completed run offers `Back to projects` as the primary completion action.
- Do not use an unlabelled gear as the sole path to settings. Use a labelled
  `Settings` button in the top bar.

## Visual foundation

Retain a green-and-black theme, but create visible depth between the canvas,
surfaces, inputs, and selected content. Use the tokens below in `gui/theme.py`.

| Token | Value | Use |
| --- | --- | --- |
| `bg_app` | `#07100A` | window canvas |
| `bg_surface` | `#0E1911` | cards, top bar |
| `bg_surface_raised` | `#142219` | selected card, inputs, log area |
| `bg_hover` | `#1B3022` | hover / pressed-neutral state |
| `border_subtle` | `#203527` | card and input boundary |
| `border_focus` | `#42E18B` | keyboard focus ring |
| `text_primary` | `#EEF7F0` | headings and body |
| `text_secondary` | `#A5B9AA` | supporting copy |
| `text_disabled` | `#65796B` | disabled controls |
| `accent` | `#35D878` | primary action, success |
| `accent_hover` | `#58E996` | primary hover |
| `accent_ink` | `#04130A` | text on accent |
| `warning` | `#F0BD45` | configuration attention |
| `danger` | `#FF7469` | failed run / destructive warning |

Use `Segoe UI` throughout: 24 pt semibold page title, 16 pt semibold section
title, 12 pt semibold field/row title, 10 pt body, and 9 pt metadata. Avoid
emoji as icons because their glyph shape varies on Windows. If an icon is used,
use a small bundled monochrome asset and pair it with a text label or tooltip.

Spacing is based on an 8 px grid: screen gutter 32 px (24 px below 1000 px
wide), surface padding 20 px, related controls 8 px, sections 24 px. Use 8 px
corner radii for cards, fields, and buttons. Give all interactive elements a
44 px minimum hit height; compact secondary buttons may be 36 px but never
smaller.

### Control hierarchy and states

| Control | Visual treatment | Use |
| --- | --- | --- |
| Primary button | green fill, dark text, semibold | one forward/commit action |
| Secondary button | raised dark surface, light text, border | navigation and low-risk actions |
| Quiet button | no fill until hover, muted/light text | `Refresh`, `View log`, settings |
| Danger button | red fill, dark text | only after a warning/review |
| Status pill | subtle tinted surface + coloured dot/text | engine, project type, run state |

Every control needs normal, hover, pressed, disabled, and keyboard-focus
states. The focus ring is a 2 px `border_focus` outline outside the control;
do not rely on a colour-only selection change.

## Application shell

The window minimum is **920 × 640**; preferred initial size is **1120 × 760**.
The shell has a 64 px app bar, a scrollable content area, and a 32 px status
bar. This replaces the current screen-by-screen frame that has no persistent
orientation. Account state is resolved with the normal boot checks, before the
home screen becomes actionable.

```
┌ Convai Modding Tool  / Projects                 Engine 5.x ready  Settings ┐
├─────────────────────────────────────────────────────────────────────────────┤
│ page title + supporting sentence                              primary CTA   │
│                                                                             │
│ responsive page content                                                      │
├ v1.x • Projects are discovered beside this tool                 Help / logs ┤
```

- The green 3 px bar under `Projects` communicates the current location.
- The engine chip reads `UE <version> ready` in green, or `UE <version> needs
  attention` in yellow. It is clickable and opens Settings, where the path can
  be repaired.
- Place the account control between the engine chip and `Settings`. When
  signed out it is a subtle `Sign in` button with a question-mark avatar; when
  signed in it shows a compact initial/avatar and first name. It is never an
  unlabeled icon.
- On a 920 px window the app-bar title stays visible, but the breadcrumb can
  collapse to `/ Projects`; `Settings` must remain text-labelled.
- The status bar is informational, not a second action bar. It never holds a
  critical control.

## Screen specifications

### 1. Boot and blocked start

Centre a compact surface (480 px wide) within the application shell. The boot
surface contains product name, `Getting things ready`, a three-stage status
line (`Checking configuration` → `Checking version` → `Opening projects`),
and an indeterminate 4 px green progress bar. Do not say only `Checking for
updates…`, because a network delay otherwise looks frozen.

For a blocked start, use the title `We couldn't start the tool`, plain-language
cause, and a details disclosure containing the raw error. Show actions in this
order: `Try again` (primary), `Download latest version` (only for outdated
build), and `Quit` (quiet). Do not colour the entire heading yellow/red; use a
small warning icon/pill and retain high-contrast body text.

An outdated build uses the stronger title `A newer version is required`, a
yellow update icon, a two-column `Installed vX` / `Required vY` comparison,
and the sentence `Update Convai Modding Tool to continue creating, updating,
and migrating projects.` The actions are `Download latest version` (primary),
`Check again` (secondary), and `Quit` (quiet). This is a blocking screen: it
does not offer access to the project shelf.

### 2. Project shelf (home)

This is the primary redesign. Keep a project list and add a stable inspector,
so selection changes explain which operation will happen.

#### Account state and sign-in modal

The home page is the account entry point. On startup, quietly resolve whether
there is a still-valid local session. A valid session presents the signed-in
account in the app bar without interrupting the user. No session or expired
session presents a focused modal over the shelf:

```
┌──────────────── Sign in to Convai ────────────────┐
│ Connect once to create, update, and manage projects.│
│                                                     │
│ [ G  Continue with Google                        ]  │
│                    ─── or ───                       │
│ [ Use an API key instead                         ]  │
│                                                     │
│ Not now                    Open Convai dashboard    │
└─────────────────────────────────────────────────────┘
```

- `Continue with Google` is the visually dominant, full-width choice. It opens
  the system browser and shows `Opening your browser…` while waiting. On a
  successful callback, dismiss the modal, update the app-bar identity, and
  enable project actions.
- `Use an API key instead` is an equal-width secondary path, but remains
  behind the initial choice rather than cluttering the home page. Its second
  modal view has a back button, one masked key field, `Sign in`, and a short
  privacy sentence. It also links to `Open Convai dashboard` for users who
  need to create or retrieve a key.
- API-key sign-in must verify the key with Convai before the modal is dismissed
  or any protected action is enabled. While verification runs, disable the
  field and button and replace the button label with `Verifying…`. A valid key
  completes the same signed-in state as Google. An invalid or rejected key
  keeps the value masked, focuses the field, and shows `We couldn't verify
  that API key. Check it and try again.` beneath it. Network/service failures
  use a distinct recovery message (`Couldn't reach Convai. Try again.`) so
  users do not mistake an outage for a bad key.
- `Not now` dismisses the modal and leaves the shelf browsable. Show an amber
  inline banner: `Sign in to create or manage Convai projects.` Its `Sign in`
  action reopens the modal. Any protected action opens the same modal instead
  of failing later.
- If the session expires during a form or review, preserve all entered values,
  show the same modal, and return the user to their previous step after sign-in.
  The user must never see raw cache, token, expiry, or network error details.

When signed in, selecting the avatar/name opens a compact menu:

```
Alex Chen
alex.chen@example.com
────────────────────
Open Convai dashboard
Switch account
Log out
```

`Open Convai dashboard` uses the default browser. `Log out` asks for a brief
confirmation only if it would discard local work; otherwise it clears the
session, changes the account control back to `Sign in`, and returns to the
signed-out shelf state.

```
Projects                                                     [Refresh] [+ New project]
Create, update, and migrate the Unreal projects beside this tool.

┌ PROJECTS (2) ────────────────────────┐  ┌ SELECTED PROJECT ──────────────────────┐
│ Search projects…                     │  │ ● CityGuide                  [Scene]   │
│                                      │  │ UE 5.4 · Sign in to manage               │
│ ● CityGuide    Scene       UE 5.4    │  │ E:\…\CityGuide                         │
│   Updated just now                    │  │                                         │
│                                      │  │ Keep this project current with the      │
│   MetaHost     Avatar      UE 5.3    │  │ latest Convai integration.              │
│   Needs migration → UE 5.4            │  │ [Update project]                        │
│                                      │  │ [Migrate to UE 5.4]                     │
└──────────────────────────────────────┘  └─────────────────────────────────────────┘
```

Layout:

- At widths >= 1000 px, use a 55/45 two-column grid; both panels begin below
  the title row and have matching top edges.
- At 920–999 px, stack inspector below the list; preserve selection and scroll
  it into view when selection changes.
- Each project row is a 72 px clickable surface, not a dense multi-column
  table. It shows name (first line), type and UE version (second line), and
  one state on the right. Selected row has `bg_surface_raised`, green 3 px
  left rail, and a focus ring when keyboard-focused.
- Filter as the user types and show `No projects match “…”` with `Clear
  search`, rather than an empty list.
- `Refresh` rescans without navigating away. During scanning its label becomes
  `Refreshing…` and it is disabled; preserve existing selection by path when
  possible.

Inspector content:

- Show project name, type pill, engine version, a Convai connection state
  (`Connected` or `Sign in to manage`), and the full path in a selectable, ellipsised field with
  `Copy path` as a quiet action.
- Show `Update project` as the only primary button. Its helper text: `Updates
  Convai plugins and project settings. Your content stays in place.`
- `Migrate to UE <target>` is secondary. If unavailable, **keep it visible**
  and replace the action with a warning line such as `Migration is unavailable:
  this project already uses UE 5.4.` or `Choose a UE 5.4 installation in
  Settings.` The explanatory line is the action's accessible description.
- A project using an unknown engine displays `Engine version not detected` and
  makes `Update project` open the engine-picker review rather than silently
  asking through a native dialog midway through the operation.

Empty state:

- Replace the lone `No projects found next to the tool` label with a centred
  empty surface: `No modding projects here yet`, one sentence that explains
  discovery (projects live beside the tool), primary `Create a project`, and
  quiet `Refresh`.
- Include a small folder illustration only if a bundled vector/icon exists;
  never rely on downloaded artwork.

### 3. New project

Use a focused, scrollable page with a 640 px maximum form width; do not spread
fields across the full window. A three-step progress indicator is informative,
not a tab control: `1 Details — 2 Project type — 3 Unreal Engine`.

```
New project                                           Step 1 of 3
Start with an Unreal project configured for Convai.

┌ 1  Project details ──────────────────────────────────────────────┐
│ Project name  [                                               ]    │
│ Letters, digits, and underscores only.                             │
│                                                                     │
└───────────────────────────────────────────────────────────────────┘
                                      [Cancel] [Continue]
```

- Validate project name while the user types after first blur; reserve space
  below the field for validation so the layout does not jump. State errors in
  plain language and focus the first invalid field on `Continue`.
- This step assumes the user already signed in from the home page. Show a
  compact `Signed in with Convai` reassurance, not an API-key field. If the
  session is no longer valid, use the home sign-in modal and preserve every
  form value.
- Project type uses two large selectable tiles: `Scene — environment or
  gameplay project` and `Avatar — character project`. The MetaHuman checkbox
  only appears for Avatar, with explanatory copy.
- Engine step defaults to detected current UE path, shows a green `Detected`
  state, supports `Choose folder`, and validates immediately. When absent,
  start with `Unreal Engine <version> is required` and make `Choose folder`
  primary. Do not make a blank path look like user error before interaction.
- The final primary action is `Create project`; display an action summary above
  it: name, type, MetaHuman choice where relevant, and engine version. The
  Back button retains all entered values.

### 4. Action review — update and migrate

Insert a review page between project selection and `show_run`. This is where
engine resolution happens, eliminating an unexpected native chooser after the
user has clicked a command.

**Update review** title: `Update <project name>`. Show target project path,
current engine, source plugin/configuration update statement, and the note
`Your content and original project folder remain in place.` Actions: `Back`
(secondary) and `Update project` (primary).

**Migration review** title: `Migrate <project name> to UE <target>`. Show:

- Source project and current UE version.
- Target UE installation with `Change` action.
- Destination folder name (`<Name>_<target>`), followed by `The original
  project will not be changed.`
- Ordered summary: update source configuration, copy project, update engine
  configuration, then build.

If the destination already exists, stop before the action and present an error
with `Choose a new name` / `Open existing folder`; never begin an ambiguous
overwrite. The confirmation button reads `Create migrated copy`, not just
`Migrate`.

### 5. Activity and result

The activity screen prioritizes human-readable progress. It keeps the current
thread-safe log plumbing but gives it a clearer hierarchy.

```
Updating CityGuide                                      In progress
Installing Convai plugins
██████████████────────────────────────────────────────

✓ Validated Unreal Engine
● Updating project files
○ Building project

Technical log                                             [Copy] [Save as…]
┌ timestamped, selectable log text … ─────────────────────────────────────────┐
```

- Use named lifecycle steps driven by phases emitted by the flow. Where a flow
  cannot provide a percentage, use an indeterminate bar and clear current-step
  label—never invent a percent.
- The log begins collapsed to roughly 160 px, can be expanded with `Show
  technical log`, and remains selectable/scrollable. Auto-scroll only while
  the user is already at the bottom; preserve their reading position otherwise.
- While a run is active, disable navigation that could discard context and use
  `Run in progress — closing the tool may interrupt it` in the window-close
  confirmation.
- Success uses a green status icon and direct result: `CityGuide is ready.`
  Offer `Open project folder` (primary) and `Back to projects` (secondary).
  Show migration notes in an expandable `What changed` surface.
- Failure uses a red icon and a concise recoverable sentence, then `View
  technical details`. Offer `Back to projects` and `Try again` only if retrying
  cannot create an ambiguous duplicate. Never label raw exception text as the
  primary explanation.

### 6. Settings

Keep Settings modal, 600 px wide, but change it from a sparse utility dialog
into organised sections.

1. **Unreal Engine**: current configured version, path field, state chip, and
   `Choose folder`. A valid detection says `Ready`; a missing one explains
   which actions need it.
2. **Packaging**: Linux packaging on/off state, a one-sentence consequence,
   and `Install Linux toolchain`. On install, place inline progress/status next
   to the button, not as a detached bottom line.
3. **About**: tool version and a quiet `Check for updates` action.

The modal has a clearly visible `Close` button and supports `Esc`. Use only
the app's dark Ttk styles—native light combobox menus, scrollbars, and dialogs
against the dark surface are defects.

## Interaction and accessibility requirements

- Tab order follows visual order; list rows, all buttons, text fields,
  segmented choices, selectors, and disclosures are keyboard reachable.
- In the shelf, Up/Down changes project selection, Enter activates the primary
  action (Update), and `Ctrl+N` opens New project. Do not steal common text
  editing shortcuts while an entry has focus.
- Provide visible `focus` state for Tk widgets that normally suppress it.
- Every status colour is accompanied by words/icon shape. Minimum contrast is
  4.5:1 for body text and 3:1 for large text/control boundaries.
- Use `wraplength`/responsive width calculations; paths must ellipsise or wrap
  rather than force a horizontal scrollbar.
- Explicitly set dark colours for Ttk popups, Tk file-selection-adjacent
  surfaces where possible, Treeview, scrollbars, Text, menus, and tooltips.
- Use `aria`-equivalent accessible names in the Tk implementation: button text
  must identify its subject (for example `Update CityGuide` in its accessible
  description even if visible text is `Update project`).

## Implementation map

This is a design hand-off, not a demand to rewrite business logic.

| Existing code | Design change |
| --- | --- |
| `App.__init__`, `_show` | Add persistent app/status bars and a scrollable page host; set the new 920 × 640 minimum/preferred geometry. |
| `gui/theme.py` | Introduce the token names above and styles for surface, quiet/secondary buttons, status pill, selected project row, field error/help, focus rings, disclosure, and step indicator. |
| `_build_shelf` | Replace `Treeview`-only shelf with filterable selectable project rows plus inspector. Preserve `_selected`, `_on_update`, and `_on_migrate` semantics. |
| `_scan_projects` | Continue existing metadata lookup; derive display status only from known data. Do not claim a project is up-to-date unless the flow provides that fact. |
| `_resolve_engine` | Move its picker/validation into review and Settings UI; keep a reusable validation helper. |
| `App.__init__`, boot, `show_shelf` | Resolve session state once and hold an account presentation model for the persistent app bar, home banner, modal, and profile menu. Store/cache and expiry mechanics are implementation details; never surface them as UI. |
| `_build_new_project`, `_on_create` | Split UI into form state + three renderable stages; preserve project-name validation and require the already-authenticated credential without displaying it. The implementation team should consult the existing Unreal authentication integration at `E:\Perforce\AnmolConvai\_AvatarStudio\_HQ\Plugins\Convai-UnrealEngine-Auth`; this design does not prescribe or duplicate its protocol. |
| `_on_update`, `_on_migrate` | Render Action review first. Begin `show_run` only after explicit review confirmation. |
| `_build_run`, `_finish_run` | Add phase presentation, collapsible technical log, success/failure result surface, and safe retry conditions while preserving QueueHandler and Tk-thread-only updates. |
| `open_settings` | Render the three grouped settings sections; retain existing asynchronous toolchain installation. |

Recommended implementation order:

1. Add design tokens, control states, app shell, and a fixture-friendly project
   row component.
2. Implement the shelf/empty state/inspector and preserve existing action
   handlers behind temporary callbacks.
3. Build the New project stages and engine configuration components.
4. Add action review, then improve Activity/result and Settings.
5. Test UI at 920 × 640, 1120 × 760, and 150% Windows scale with: no projects,
   one selected project, migration unavailable, missing engine, invalid form,
   success, and failure.

## Acceptance checklist

- [ ] A new user with no projects sees one obvious way to create one and an
  explanation of discovery.
- [ ] A selected project always has visible name, engine, type, path, and
  action consequences before Update/Migrate begins.
- [ ] Migration unavailability has a visible reason; no unexplained disabled
  Migrate action remains.
- [ ] New-project errors are field-specific, stable in layout, and do not
  expose credentials or account tokens.
- [ ] Every run shows a current task, readable outcome, and technical log that
  neither overwhelms the page nor loses user scroll position.
- [ ] The app is usable by keyboard and keeps focus visually apparent.
- [ ] No unsupported product state is invented; all project/engine information
  is sourced from the existing `InputManager`, `config`, and metadata.
