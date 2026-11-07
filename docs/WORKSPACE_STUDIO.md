# Workspace Studio

Workspaces now contains source files, DOCX documents, an assistant and HTML preview.
Example: «Создай пространство Кофейня, хранение в облаке Delta, делаем лендинг».
`workspaces.create` accepts `work_type` (website/code/documents/general),
`storage_mode` (cloud/local), and `storage_device_id` for local mode.
`workspaces.build` invokes a workspace-scoped tool registry; only successful file
operations count as saved changes. The existing app-launch bindings remain separate.

## Storage and operations

Cloud files live on the Core host in `DELTA_WORKSPACE_DIR`, default
`<Core working directory>/.runtime/workspaces/<workspace UUID>`. Compose mounts a
persistent `workspace-data` volume at `/data/workspaces`. Back up this directory
alongside the Core database, which stores workspace metadata. Local mode stores
files on the selected Agent in `<Agent config directory>/workspaces/<UUID>`.
The Agent must be online and version 0.4.0 or later. Local file bytes are transiently
relayed through Core for display/AI; they are not mirrored into cloud storage.
Switching storage mode of an existing workspace is not supported; choose at creation.
Workspaces retain the existing shared-admin access model. Documents copied from
personal library are fetched using the current user's ownership check.

Both modes support nested relative paths, optimistic SHA-256 conflicts, atomic
saves and twenty previous versions per file. History can be downloaded or restored.
No shell, package manager, build process or generated Python is executed.
Files: UTF-8 HTML/CSS/JS/TS/JSX/TSX/JSON/MD/TXT/Python/YAML/TOML/CSV/SVG, plus DOCX.
Limit: 128 current files and 64 MB current content per workspace; source files
512 KB each, DOCX 10 MB. History is additional storage (up to twenty prior copies
per file); monitor disk usage. Deleting workspace metadata does not destroy its
stored files; remove orphaned storage manually only after checking backups.
Paths cannot escape storage, traverse symlinks, use hidden components or common
credential filenames. File contents and search results are redacted from device
activity logs. General assistant history retains result summaries, not file bytes.

## Documents and importing

Upload with file chooser or drag and drop. Choose an existing document from the
Delta document library to copy it into the workspace. Editing a copied document
does not change its source. New DOCX documents can also be created by the assistant.
DOCX paragraphs and table cells are displayed and edited using the existing OOXML
service; images, headers and other package parts remain intact. Textual preview is
not a page-layout renderer. Edits use the paragraph's first run formatting.

Computer import uses explicit `search_files`/`read_file` Agent capabilities in
permitted folders. The desktop Settings has a Documents / Downloads / Desktop
button; enabling full access adds those existing folders only when the list is
empty. Individual deny/ask policies remain in force. Search does not scan hidden
folders, node_modules, build caches or OS-private folders. It returns at most 50
matches and stops after 30,000 entries or five seconds, marking partial results.
An ambiguous filename is presented with paths for user selection; the assistant
stops instead of silently choosing a match. Import never overwrites an existing
workspace file and never modifies the source. Arbitrary disk-wide search and
reading credentials are not supported.

## Preview and AI

HTML preview bundles saved relative styles/scripts and SVG from this workspace
(maximum 2 MB source content) into an opaque-origin sandboxed iframe. It does not
have same-origin access to Delta; CSP blocks remote resources, fetch and forms.
No backend or npm/dev server runs. ES module dependency resolution, React/TS
compilation, server-side languages and live external integrations are not previewed.

Workspace assistant receives file names and selected file context through tools,
reads existing content before editing, and uses revision hashes to reject stale
writes. DOCX changes must name exact paragraph IDs and old text. Uploaded contents
are data, not instructions. A turn has at most 16 tool calls / 7 model rounds and
240 seconds; partial changes are reported and remain accessible in history.
Large files above 32,000 serialized characters require smaller files/manual edits.
The active Delta LLM bridge remains switchable cloud/local/auto. Coding responses
allow up to 6,000 output tokens and 45 seconds for cloud inference; regular command
routing keeps its short deadline. A weak local model may fail complex coding tasks;
failed or truncated proposals are not executed. Chat history in the Studio lasts
for the current mounted workspace view; files and revisions are persistent.

API: `/api/v1/workspaces/{id}/studio/{files,file,document,history,download,upload,
search,import,library,chat,preview,restore,new-document}`. Schema migration `0008`.
Update Core/contracts before Agent 0.4.0; older Agents keep their previous actions
but cannot serve local workspaces. UI documents the required update.

## Verification

- Backend regression suite and focused tests cover cloud files, stale writes,
  revisions/restore, DOCX preservation, invalid paths, local dispatch, ambiguous
  search, assistant writes and source boundaries.
- Agent tests cover full/ask/deny, cancellation, search/read and local storage.
- Live Nobara: actual model created a landing file, and the global Assistant created
  a workspace then called its builder. Live Agent found/imported/edited a file while
  preserving the original. Browser preview verified against saved generated HTML.
- macOS/Windows run the same bounded file operations; native packaging is built
  in CI. A physical Mac/Windows desktop session was not available here.
