# Installing the tiny software factory

You are a coding agent installing the factory into the user's project. Copy
the generic files, adapt the repo-specific parts, verify and report. Work in
the project root. Don't clone this repository.

Read source files from
`https://raw.githubusercontent.com/utpalsinghdev/tiny-software-factory/main/<path>`.

## 0. Check the project

Stop and tell the user if any of these fail:

- It is a git repo with an `origin` on GitHub, and `gh auth status` shows a
  user who can push to it and manage its labels.
- Its default branch (`gh repo view --json defaultBranchRef`) exists on
  `origin`.
- `claude --version` and `codex --version` both work, and both CLIs are signed
  in. The Claude agents run on `claude`; code-review and approval run on
  `codex`.
- `python3 --version` is 3.10 or later. The scripts use only the standard
  library.
- None of the files in step 1 exist yet. If one does, show the user the clash
  and ask before overwriting.

## 1. Copy

Copy these to the same paths in the project, unchanged:

```text
.agents/skills/factory/SKILL.md
.agents/agents/intake/AGENT.md
.agents/agents/spec-writer/AGENT.md
.agents/agents/builder/AGENT.md
.agents/agents/code-review/AGENT.md
.agents/agents/ui-ux-review/AGENT.md
.agents/agents/ui-design-review/AGENT.md
.agents/agents/security-review/AGENT.md
.agents/agents/approval/AGENT.md
.claude/skills/factory/SKILL.md
factory/config.json
factory/bin/job
factory/bin/agent
```

```bash
SRC=https://raw.githubusercontent.com/utpalsinghdev/tiny-software-factory/main
for f in <the paths above>; do
  mkdir -p "$(dirname "$f")" && curl -fsSL "$SRC/$f" -o "$f"
done
chmod +x factory/bin/job factory/bin/agent
```

The real skill is `.agents/skills/factory/SKILL.md`. Codex and Pi read
`.agents/skills/` directly as a skill (`/skill:factory` in Pi). Claude Code
doesn't, so `.claude/skills/factory/SKILL.md` is a short pointer to the real
file. Don't add a `.pi/skills/factory` copy: Pi would load both and warn
about a name collision.

Don't copy `README.md`, `INSTALL.md` or `LICENSE`. They describe the factory,
not the user's project.

## 2. Adapt

**`factory/config.json`.**

- `base_branch`: the default branch.
- `merge_method`: `merge`, `squash` or `rebase`, whichever the repo allows
  (`gh api repos/{owner}/{repo} --jq '{allow_merge_commit, allow_squash_merge, allow_rebase_merge}'`).
- `ports.base`: move it if the project already uses ports 5100–5199.
- Leave `concurrency`, `max_rounds` and `reviewers` alone unless the user asks.

**Agents.** The checklists are general on purpose. Tailor them to the stack
without changing their structure, frontmatter keys, file names, first-line
formats or one-line replies:

- `security-review`: this project's hot spots (auth, data access rules,
  payments and webhooks, where user input meets queries or HTML).
- `ui-design-review`: where the design tokens, theme and shared components
  live.
- `ui-ux-review`: the kinds of users the app has.
- `approval`: what a human must always see in this project, added to the
  ESCALATE list.
- `intake`: one line under **How to decide** saying what the project is for,
  so intake can tell what belongs.

**`AGENTS.md`** (or `CLAUDE.md`, whichever the project uses; create
`AGENTS.md` if neither exists). Every agent reads it, and the builder runs its
validation commands before every PR, so make sure it says:

- how to set up a fresh checkout (install dependencies, env files to copy);
- how to start the dev server on a given port, if there is one;
- the validation commands: tests, lint, typecheck and build, whichever the
  project has.

Then add a short section:

```markdown
## Software factory

`/factory run` builds every open GitHub issue labeled `factory` through
intake → spec → build → review → approval, one PR per issue. Agents live in
`.agents/agents/`, state in `factory/jobs/` (gitignored), and
`factory/bin/job` is the only writer of that state.

Each job works in its own git worktree at `.worktrees/<job-id>` (gitignored).
Tools run from the repo root that don't read `.gitignore` will see those
copies too; exclude `.worktrees/` in their config.
```

**`.gitignore`.** Append:

```gitignore
/factory/jobs/
/.worktrees/
```

Only these two are runtime state. Everything from step 1 gets committed.

**Labels.**

```bash
gh label create factory --color 5319E7 --description "Build this with the tiny software factory"
gh label create factory:needs-info --color FBCA04 --description "The factory asked the author a question"
gh label create factory:needs-human --color D93F0B --description "The factory needs a human decision on the PR"
```

## 3. Verify

1. The validation commands in AGENTS.md pass on the current branch. If they
   don't, the builder can never reach READY: tell the user what's broken.
2. `factory/bin/job queue` runs without an error.
3. `factory/bin/agent --help` prints its usage, and every `AGENT.md` has
   `cli`, `model` and `effort` in its frontmatter.
4. `python3 -m json.tool factory/config.json` succeeds.
5. `git check-ignore factory/jobs/x .worktrees/x` prints both paths, and
   `git status --porcelain --untracked-files=all` lists every file from step 1
   as committable.

## 4. Hand over

Stay on the user's current branch. Commit the install there with a one-line
message and show the diff. Ask before pushing: every job branches from
`origin/<base_branch>`, so the install must be pushed there before the first
run.

Then tell the user, in a few lines:

- Label one or two small issues `factory`, then run `/factory run` from the
  project root.
- Every job ends as a PR. The approval agent merges what it approves; the rest
  wait with the `factory:needs-human` label. Merge one to approve it, or
  change it with `/factory ask`.
- To start carefully, set `concurrency` to 1 and read every PR until they
  trust it.
