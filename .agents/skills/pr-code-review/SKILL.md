---
name: pr-code-review
description: Comprehensive code review checklist and guidelines for evaluating Pull Requests. Use this skill when asked to review code, analyze a PR, or check code quality before merging.
---

# PR Code Review Guidelines (Smart Shelter)

## Trigger Commands

**Default — analyze only (never auto-post):**

- `/pr-code-review <PR_LINK_OR_NUMBER>`
- `@[pr-code-review] review <PR>`
- Any request to review a PR or local changes

For these triggers you MUST analyze the changes and **display the review in chat only**. Do **not** call `gh pr review`, `gh pr comment`, or any other command that writes to GitHub unless the user explicitly asks you to post (see below).

**Local staged changes (pre-PR):**

- `@[pr-code-review] review staged`
- Review local / unstaged diff when asked

Use `git diff --cached` (staged) or `git diff` (unstaged) as appropriate, evaluate, and output the review in chat.

**Post to GitHub — explicit command only:**

- `/pr-code-review post <PR_LINK_OR_NUMBER>`
- User says e.g. "post this review", "submit review to GitHub", "approve/request-changes on PR #N"
- Batch: "post reviews for PR #12, #15" — load one artifact per PR (see **Review Artifacts**)

Only then may you run `gh pr review`. **Always read the review body from the artifact file** for that project + PR (not from chat memory). Never post without an explicit post command in the same or a follow-up message.

## Review Artifacts (mandatory)

Every completed review MUST be persisted as a **temporary artifact outside the workspace** so post steps are reliable across turns and support multiple PRs.

### Storage location

```
$HOME/.cursor/pr-code-review/
```

- **Outside the workspace** — never under the project repo.
- Create the directory if missing (`mkdir -p`).
- Mode `0700` on the directory when you create it.

### Filename

```
{owner}__{repo}__pr-{number}.md
```

Resolve `{owner}` and `{repo}` from the current git remote (`gh repo view --json nameWithOwner`) or `git remote get-url origin`. Example: `acme__sindhu__pr-42.md`.

**Local / pre-PR reviews** (no GitHub PR yet):

```
{owner}__{repo}__local-{staged|unstaged|diff}.md
```

### File format

Markdown with YAML frontmatter. The body (below the closing `---`) is what gets posted to GitHub.

```markdown
---
project_owner: acme
project_repo: sindhu
project_full_name: acme/sindhu
pr_number: 42
pr_title: "feat(people): add intake form"
pr_url: https://github.com/acme/sindhu/pull/42
verdict: Request changes
review_action: request-changes
merge_ready: false
attempt_count: 2
escalation_required: false
created_at: 2026-07-03T10:37:00+07:00
workspace: ~/sindhu
---

## PR Review — feat(people): add intake form

**Verdict:** Request changes
**Merge readiness:** ❌ ยังไม่พร้อม merge

### Blockers

- …

### Warnings

- …

### Suggestions

- …

### Nitpicks

- …

### Merge readiness (summary)

- **Status:** ❌ ยังไม่พร้อม merge / ✅ พร้อม merge / ⚠️ พร้อม merge (มีข้อควรระวัง)
- **สรุป:** <1–2 ประโยค อธิบายว่าทำไมพร้อมหรือยังไม่พร้อม>
- **ก่อน merge:** <สิ่งที่ต้องทำก่อน merge — หรือ `—` ถ้าพร้อมแล้ว>
```

**`review_action`** — one of `comment` | `approve` | `request-changes`. Set from verdict:

- Approve, no blockers → `approve`
- Blockers remain → `request-changes`
- Otherwise → `comment`

**`verdict`** — human-readable label for chat context only.

**`merge_ready`** — `true` | `false` (artifact frontmatter only; not posted). Set from **Merge readiness** rules below.

### Merge readiness (mandatory)

Every review MUST state clearly whether the change is **ready to merge**. Include:

1. **One-line badge** immediately after **Verdict** (visible at a glance):
   - `**Merge readiness:** ✅ พร้อม merge`
   - `**Merge readiness:** ❌ ยังไม่พร้อม merge`
   - `**Merge readiness:** ⚠️ พร้อม merge (มีข้อควรระวัง)` — only when allowed (see table)
2. **`### Merge readiness (summary)`** section at the **end** of every review (chat + artifact body) with **Status**, **สรุป**, and **ก่อน merge**.

| Status                         | `merge_ready` | Condition                                                                                                             |
| ------------------------------ | ------------- | --------------------------------------------------------------------------------------------------------------------- |
| ✅ พร้อม merge                 | `true`        | No blockers, verdict `Approve`, `escalation_required` is false                                                        |
| ❌ ยังไม่พร้อม merge           | `false`       | Any blocker, verdict `Request changes`, or `escalation_required` is true                                              |
| ⚠️ พร้อม merge (มีข้อควรระวัง) | `true`        | No blockers, verdict `Comment`, only warnings/suggestions/nitpicks — merge acceptable but note follow-ups in **สรุป** |

**สรุป** must answer in plain language: _พร้อม merge แล้วหรือยัง และทำไม_ (1–2 sentences). Use Thai for **Status** / **สรุป** / **ก่อน merge**; English summary optional in parentheses.

When **ยังไม่พร้อม merge**, **ก่อน merge** must list concrete next steps (e.g. แก้ blockers, รอ senior verify). When **พร้อม merge**, write `—`.

### After review (write artifact)

1. **Load / update attempt state** — see **Review Attempt Threshold** (increment on fail, reset on pass).
2. Finish analysis and format the review (see **Output Format**).
3. Display the review in chat (include escalation notice when `attempt_count >= 3`).
4. **Write the artifact file** to `$HOME/.cursor/pr-code-review/{owner}__{repo}__pr-{number}.md` — include `merge_ready`, `attempt_count`, and `escalation_required` in frontmatter.
5. **Write / update / delete** the matching `.state.json` file.
6. Tell the user the artifact path so they can edit it before posting.
7. If an artifact for the same project + PR already exists, **overwrite** it (latest review wins).

### Before post (read artifact)

1. Resolve target PR number from the user's command.
2. Resolve `{owner}` / `{repo}` from the current repo; confirm they match the artifact frontmatter (warn if mismatch).
3. **Read the artifact file** — use the markdown body as the `gh pr review -b` payload.
4. Honor `review_action` in frontmatter unless the user explicitly overrides (e.g. "post as approve").
5. If `escalation_required: true`, apply **Posting under escalation** rules before posting.
6. If the artifact is missing, stop and ask the user to re-run the review or provide the path.

### After successful post (delete artifact)

1. Run `gh pr review` with the body from the artifact.
2. **Only on success** (exit code 0): delete the artifact file (`rm`) **and** the matching `.state.json` if the posted review was an **Approve**.
3. Confirm in chat which PR was posted and that the artifact was removed.

### On post failure

- **Do not delete** the artifact.
- Report the error; the user can fix the artifact or retry.

### Multiple PRs

- Each PR gets its **own artifact file** — safe to review many PRs in one session.
- Posting multiple PRs: load and post **one artifact per PR** sequentially; delete each only after its post succeeds.
- Never merge multiple PR reviews into one GitHub comment.

## Human Review First (mandatory)

1. Analyze → display findings in chat grouped by severity.
2. **Save artifact** to `$HOME/.cursor/pr-code-review/`.
3. Human reads chat output and/or **edits the artifact file** directly.
4. Human explicitly commands post → read artifact → post to GitHub → delete artifact on success.

If the user has not said to post, end your response with a short note that the review is for human review only, include the artifact path, and that they can ask you to post when ready.

## Review Attempt Threshold (3 attempts)

Track consecutive **non-passing** reviews per PR (or local review target). When a target fails **3 times**, escalate — a **senior developer** or **tech lead** must verify manually before merge.

**Constant:** `MAX_REVIEW_ATTEMPTS = 3`

### Pass / fail

| Result   | Condition                                                                                                     |
| -------- | ------------------------------------------------------------------------------------------------------------- |
| **Pass** | Verdict is `Approve` — no blockers                                                                            |
| **Fail** | Verdict is `Request changes`, **or** the review lists one or more **Blockers** (even if verdict is `Comment`) |

### State file

Persist attempt count alongside artifacts (same directory, same `{owner}__{repo}__` prefix):

```
$HOME/.cursor/pr-code-review/{owner}__{repo}__pr-{number}.state.json
```

Local / pre-PR reviews:

```
$HOME/.cursor/pr-code-review/{owner}__{repo}__local-{staged|unstaged|diff}.state.json
```

```json
{
  "project_full_name": "acme/sindhu",
  "review_target": "pr-42",
  "attempt_count": 2,
  "last_verdict": "Request changes",
  "last_review_at": "2026-07-06T15:38:00+07:00",
  "escalation_required": false
}
```

- Create the directory with mode `0700` if missing.
- `review_target` — e.g. `pr-42`, `local-staged`.

### Counter workflow (every analyze review)

1. **Load state** — read `.state.json` for this target; if missing, treat `attempt_count` as `0`.
2. **Analyze** — run the normal review checklist.
3. **Update counter:**
   - **Pass** → set `attempt_count = 0`, **delete** `.state.json`.
   - **Fail** → increment `attempt_count`, write `.state.json` with `last_verdict`, `last_review_at`, and `escalation_required: attempt_count >= 3`.
4. **Escalation** — when `attempt_count >= 3` after a fail:
   - Set `escalation_required: true` in state **and** artifact frontmatter.
   - Display the **Escalation notice** (below) at the top of chat output and in the artifact body (immediately after the verdict line).
   - Do **not** auto-post (existing rule). Warn that senior/tech lead sign-off is required before merge.

### Escalation notice (mandatory when `attempt_count >= 3`)

```markdown
> ⚠️ **ต้องให้ Senior / Tech Lead ตรวจสอบเอง (ครบ {attempt_count}/3 ครั้ง)**
>
> PR นี้ยังไม่ผ่านการ review หลังพยายามแก้ไขครบ 3 ครั้งแล้ว กรุณาให้ **senior developer** หรือ **tech lead** เข้ามา verify และตรวจสอบด้วยตัวเองก่อน merge
>
> _This change has not passed review after 3 attempts. A senior developer or tech lead must manually verify before merge._
```

### Posting under escalation

If artifact frontmatter has `escalation_required: true` and the user requests post:

1. Warn that senior/tech lead manual verification is expected.
2. Post **only** if the user explicitly confirms in the same or follow-up message (e.g. "post anyway", "senior approved").

## Output Format (chat)

Always structure the in-chat review with these four severity levels:

| Level          | When to use                                                                                             |
| -------------- | ------------------------------------------------------------------------------------------------------- |
| **Blocker**    | Must fix before merge — bugs, security holes, architecture violations, missing tests for critical paths |
| **Warning**    | Should fix — likely issues, missing edge-case handling, spec drift, weak error handling                 |
| **Suggestion** | Nice to have — clearer naming, small refactors, better patterns                                         |
| **Nitpick**    | Optional polish — style, minor wording, trivial consistency                                             |

Template (chat display **and** artifact body below frontmatter):

```markdown
## PR Review — <title or number>

**Verdict:** <Approve / Request changes / Comment — for human context only; not posted>
**Merge readiness:** <✅ พร้อม merge / ❌ ยังไม่พร้อม merge / ⚠️ พร้อม merge (มีข้อควรระวัง)>
**Attempt:** <attempt_count>/3> _(omit line when attempt_count is 0)_

<!-- Escalation notice here when attempt_count >= 3 — see Review Attempt Threshold -->

### Blockers

- …

### Warnings

- …

### Suggestions

- …

### Nitpicks

- …

### Merge readiness (summary)

- **Status:** <same as one-line badge above>
- **สรุป:** <1–2 ประโยค — พร้อม merge แล้วหรือยัง และทำไม>
- **ก่อน merge:** <ขั้นตอนที่ต้องทำ หรือ `—` ถ้าพร้อมแล้ว>
```

When suggesting code changes, use **Markdown diff blocks** (` ```diff `) with `-` / `+` lines, not plain code blocks.

If a section has no items, write `None.`

End chat output with:

```markdown
---

_Review saved to `~/.cursor/pr-code-review/{owner}__{repo}__pr-{number}.md` (attempt {attempt_count}/3). Edit that file if needed, then say "post review to GitHub" (or `/pr-code-review post <PR>`) when ready._
```

When `escalation_required: true`, add:

```markdown
_⚠️ ครบ 3 ครั้งแล้ว — ต้องให้ senior dev หรือ tech lead ตรวจสอบเองก่อน merge_
```

## 1. Architecture & Data Flow (Remote-First)

- **Repository Pattern**: Are database operations routed through the proper repository layer (`$lib/db/repository.ts`) rather than direct database calls from components?
- **Data Mutation**: Do writes follow active-endpoint policy (central first, edge fallback) without local-only queues, and does disconnected mode stay status-only (no read-only local cache)?
- **Concurrency & `_rev`**: Do update/delete operations properly fetch and provide the latest `_rev` to avoid `409 Conflict` errors?
- **Live Updates**: Does the UI use the project's canonical app-level event channel invalidation/live-update mechanism (without polling as the default)?
- **Schema Documentation**: If the PR modifies or adds data structures in the database, was `docs/data/schema.md` updated accordingly?

## 2. Security & Access Control

- **Admin Boundaries**: Are privileged CouchDB operations (creating DBs, changing `_security`, creating users) strictly kept on the server side using `$lib/server/couch-admin.ts`? Are any admin credentials leaking to the frontend?
- **RBAC / Auth**: Are routes and data operations properly protected by role-based access control?
- **Data Privacy**: Are sensitive fields (PII, medical data, national ID) properly handled and excluded from public or EOC/Open API endpoints?

## 3. Frontend & Framework Standards

- **Svelte 5 (Runes)**: Does the component use modern Svelte 5 syntax (`$state`, `$derived`, `$effect`) correctly? Are there unnecessary reactive statements?
- **Styling**: Are Tailwind CSS v4 utility classes used appropriately? Are custom CSS classes avoided when standard utilities exist? (If using `shadcn-svelte`, are the components used correctly?)
- **Performance**: Are there any unnecessary re-renders or heavy computations inside `$effect` or rendering loops?
- **Accessibility (a11y)**: Does the UI support keyboard navigation? Are semantic HTML and proper ARIA attributes used (e.g. for screen readers)?

## 4. Code Quality & General Principles

- **TypeScript Strictness**: Are there missing types, excessive use of `any`, or ignored TypeScript warnings?
- **DRY & YAGNI**: Is the code duplicating existing utility functions? Is it over-engineering features (You Aren't Gonna Need It)?
- **Error Handling**: Are errors caught and handled gracefully? Is the user informed of failures appropriately?
- **Clean Code**: Are functions small, focused, and well-named? Are magic numbers or hardcoded strings extracted into constants?
- **Test Coverage**: Does the new feature or bug fix include Unit/Integration tests? Do all tests pass?
- **Leftover Code**: Has the code been cleaned of leftover `console.log`, `debugger` statements, and commented-out code before opening the PR?

## 5. Fetching PR Data (GitHub CLI — read-only)

When reviewing a GitHub Pull Request, use `gh` to **fetch only**:

- `gh pr view <number>` — PR description, title, labels, checks
- `gh pr diff <number>` — full diff
- `gh repo view --json nameWithOwner,url` — project identity for artifact naming

Do **not** write to GitHub during the analyze step.

## 6. Posting to GitHub (explicit command only)

After the human approves posting:

1. Read artifact: `$HOME/.cursor/pr-code-review/{owner}__{repo}__pr-{number}.md`
2. Extract body (markdown below frontmatter) and `review_action` from frontmatter
3. Post using the body file (prefer `--body-file` over inline `-b` for long reviews):

```bash
gh pr review <number> --comment --body-file "$HOME/.cursor/pr-code-review/{owner}__{repo}__pr-{number}.md"
```

For `--approve` or `--request-changes`, pass only the **body** (not frontmatter). Strip frontmatter before posting — e.g. write body to a temp slice or use `tail -n +N` after the closing `---` line.

Mapping:

- `review_action: comment` → `gh pr review <n> --comment --body-file <body-only-file>`
- `review_action: approve` → `gh pr review <n> --approve --body-file <body-only-file>`
- `review_action: request-changes` → `gh pr review <n> --request-changes --body-file <body-only-file>`

4. On success: `rm` the artifact
5. On failure: keep artifact, report error

Confirm the PR number with the user if ambiguous. If they edited the artifact, use the file on disk as source of truth.

## Review Process Workflow

1. **Fetch and analyze the diff**
   - **PRs:** `gh pr view` + `gh pr diff` + `gh repo view`
   - **Local:** `git diff --cached` or `git diff`
2. **Load attempt state** — read `.state.json` for this review target (see **Review Attempt Threshold**).
3. **Load related skills** (read and apply before concluding):
   - `project-structure-architecture` — feature layering, file placement
   - `svelte-core-bestpractices` / `shadcn-svelte` / `svelte-code-writer` — Svelte/UI changes
   - `couchdb-bestpractices` — data model, remote-first endpoint policy, MVCC
   - `security-rbac-bestpractices` — roles, shelter scope, PII
   - `testing-bestpractices` — Vitest/Playwright, DoD
4. **Check the checklist** — sections 1–4 above.
5. **Formulate feedback** — Blocker / Warning / Suggestion / Nitpick; use diff blocks for fixes.
6. **Determine merge readiness** — set one-line badge, summary section, and `merge_ready` frontmatter (see **Merge readiness**).
7. **Update attempt counter** — pass resets, fail increments; escalate at 3.
8. **Display in chat** and **write artifact + state** to `~/.cursor/pr-code-review/`.
9. **Post to GitHub** (explicit command only) — read artifact → post → delete artifact on success.
