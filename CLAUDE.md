# Alpha — rules for Claude sessions

## Work in the repo root, not in a worktree

The user wants every session to work directly in **`/home/a/Documents/Alpha`**
on branch **`main`** — not in `.claude/worktrees/*`.

- If this session started inside `/home/a/Documents/Alpha/.claude/worktrees/…`,
  the desktop app is running it in an isolated worktree. Its working directory
  **cannot** be moved (`mcp__ccd_directory__change_directory` refuses for such
  sessions), and its file-edit tools refuse paths in the root checkout — both
  verified 2026-09-19. Before doing any work, tell the user and ask them to end
  this session and start a new one on `/home/a/Documents/Alpha` with worktree
  isolation turned off (or from a terminal: `cd /home/a/Documents/Alpha &&
  claude`). If they want to continue here anyway: edit and commit in the
  worktree, then bring it into the root with
  `git -C /home/a/Documents/Alpha merge --ff-only <this worktree's branch>`,
  and never let the two drift apart.
- Do not create worktrees (`EnterWorktree`, `git worktree add`) unless the user
  asks for one.
- Only one session should edit the repo at a time. If `git status` in the root
  shows changes you did not make, ask before touching them.

## Where to start

`documentations/log/NEXT_SESSION_PROMPT.md` — what exists so far and a
paste-ready prompt; then `documentations/log/log-v2.md` ("Resume here") and
`docs/CONTRACTS.md` (interfaces). Decisions D1–D4 in `log-v2.md` are settled.

## Working agreements

- Reply in Chinese.
- List every open or conflicting decision and ask the user **before** starting
  work; do not settle them yourself or let subagents settle them.
- Commit freely; **ask before every push**.
- `npm install` hangs from the agent sandbox — ask the user to run
  `npm install --legacy-peer-deps`. `cargo` works.
- Playwright: `ALPHA_CHROMIUM=/usr/bin/chromium` (it cannot download browsers
  here). Sandbox WebGL is SwiftShader — never report those frame times as
  hardware performance.
- Invoke saved workflows by `scriptPath`, not by name (a name can resolve to a
  stale cached copy), and only in an attended session.
