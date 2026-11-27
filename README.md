# Tiny Software Factory

GitHub issues go in and merged pull requests come out.

Label an issue `factory` and run `/factory run`. A small team of agents
decides whether the issue is worth building, writes a spec, builds it,
reviews it and opens a PR that closes the issue. The approval agent merges
what it is confident about and passes everything else to you.

The factory works with any agent harness. Each agent declares the CLI and
model it runs on, so Claude and Codex models work together in the same line,
and the `/factory` skill works from Claude Code, Pi or Codex.

## Install

Open your coding agent in your project and paste:

```text
Install the tiny software factory into this repo from:
https://github.com/utpalsinghdev/tiny-software-factory
```

Your agent follows [`INSTALL.md`](INSTALL.md). It copies the skill, agents and
scripts, tailors the reviewers to your stack, creates the GitHub labels and
checks that everything runs.

You need `python3` 3.10 or later, the `claude` and `codex` CLIs signed in, and
an authenticated [`gh`](https://cli.github.com/) that can push to the repo.

## Run the factory

```text
/factory run              work through every open issue labeled `factory`
/factory #42              run one issue now (any GitHub issue id)
/factory ask <anything>   ask about jobs, give feedback, reject a job, file a feature
```

In Pi, run it as the skill: `/skill:factory run`.

## The line

```text
GitHub issues (label: factory)
        │
        ▼
intake ─────────── NEEDS-INFO → asks the author on the issue, waits for a reply
  opus high        REJECT     → explains why on the issue
        │ ACCEPT, maybe rescoped; rates risk and surfaces
        ▼
spec-writer        spec.md with checkable acceptance criteria
  opus medium
        ▼
builder ◄───────── CHANGES: the same builder fixes it
  opus medium      runs the repo's own checks, pushes, opens a draft PR "Closes #n"
        ▼                ▲
reviewers ───────────────┘  run in parallel, the factory waits for all of them
  code-review         gpt-6.2-sol high   always
  ui-ux-review        sonnet             UI changes
  ui-design-review    haiku              UI changes
  security-review     opus medium        security changes
        ▼ all PASS
approval ───────── APPROVE  → merge the PR (gh pr merge)
  gpt-6.2-sol high  ESCALATE → needs a human: you decide on the PR
```

One session orchestrates every job, `concurrency` at a time (3 by default).
Each job gets its own git worktree and branch. All state lives in
`factory/jobs/`, so if the session dies, `/factory run` picks every job back
up.

You approve an escalated job by merging its PR. To ask for changes, tell the
factory with `/factory ask` and the same builder runs another round.

## What's inside

```text
.agents/
  skills/factory/SKILL.md          the orchestrator: queue, concurrency, the line
  agents/
    intake/AGENT.md                worth building? what scope? risk and surfaces
    spec-writer/AGENT.md           spec.md
    builder/AGENT.md               code, commits, the PR, build.md
    code-review/AGENT.md           correctness, simplicity, tests
    ui-ux-review/AGENT.md          flows, states, copy, accessibility
    ui-design-review/AGENT.md      visual consistency
    security-review/AGENT.md       auth, input, secrets, data exposure
    approval/AGENT.md              APPROVE or ESCALATE
.claude/skills/factory/SKILL.md    pointer to the real skill, for Claude Code
                                   (Pi and Codex read .agents/skills directly)
factory/
  config.json                      concurrency, rounds, labels, reviewers, ports
  bin/job                          the only writer of job.json; refuses illegal moves; merges
  bin/agent                        runs an agent on its own CLI and model
  bin/dashboard                    read-only HTML dashboard; reads factory/jobs and gh pr checks
INSTALL.md                         instructions for the installing agent
```

## How it holds together

- **Agents are files.** Each `AGENT.md` has frontmatter (`cli`, `model`,
  `effort` and, for Claude, `tools`) and plain instructions. Change a model in
  one line and nothing else moves.
- **Agents run outside the orchestrator.** `factory/bin/agent` starts each one
  with its own CLI, so the session running `/factory` can be any harness.
- **Agents talk through files.** Each agent writes one file and replies with
  one line. The next agent reads the file; the orchestrator reads only the
  first line, so its context lasts the whole run.
- **A script owns the state.** `factory/bin/job` is the only writer of
  `job.json` and refuses moves the files don't justify, such as reviewing an
  unpushed branch or approving with a review still asking for changes.
- **Every job ends as a PR.** Merges go through `gh pr merge`, so branch
  protection and required checks still apply. The factory never deploys.
- **The label is the trust boundary.** Only issues labeled `factory` run, and
  issue text reaches agents only as quoted data.

## Watch the factory

While a run is in progress you can watch all jobs in a browser:

```bash
factory/bin/dashboard --watch --open
```

This writes `factory/dashboard.html` (gitignored), opens it once, and refreshes every 5 seconds. It shows counts, the stage timeline for each job, review verdicts, and CI check results. Flags: `--out PATH` to change the output file, `--watch N` to change the interval, `--no-gh` to skip the `gh` calls when you are offline. The script is read-only and never writes under `factory/jobs`.

## Safety

The factory opens and merges real PRs. Start with `concurrency: 1` in
`factory/config.json` and read every PR until you trust it.

## License

GPL-3.0. See [`LICENSE`](LICENSE).

Built by [Utpal Singh](https://github.com/utpalsinghdev).
