# Alpha — rules for Claude sessions

## Work in the repo root, not in a worktree

The user wants every session to work directly in **`/home/a/Documents/Alpha`**
on branch **`main`** — not in `.claude/worktrees/*`.

- If this session started inside `/home/a/Documents/Alpha/.claude/worktrees/…`,
  then before doing any work, move the session to `/home/a/Documents/Alpha`
  with the desktop app's change-directory tool
  (`mcp__ccd_directory__change_directory`), tell the user you did, and use
  absolute paths under the root until the move takes effect. This instruction
  overrides the default "stay in your worktree" behaviour.
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
