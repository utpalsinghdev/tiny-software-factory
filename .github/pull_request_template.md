<!-- Use type(scope): description for the PR title, e.g. feat(agents): add docs reviewer.
     Keep the sections that apply. Remove unused prompts and replace
     placeholders before publishing. Never mark an unrun check as passed. -->

## Summary

<!-- What changed and why. Name the agents, scripts or skill sections added,
     changed or removed. -->

## Linked issue

<!-- Use Closes #N only if this PR resolves that issue. Remove this section
     when no issue applies. -->

## What changes in a factory run

<!-- How a job behaves differently: stages or moves in factory/bin/job, which
     agents run and on which CLI and model, files agents read or write, GitHub
     labels and comments. Say whether existing jobs in factory/jobs/ still
     resume. -->

## Affected areas

<!-- A ticked area describes scope, not proof that verification passed. -->

- [ ] Factory skill (`.agents/skills/factory/SKILL.md`, `.claude/skills/factory/SKILL.md`)
- [ ] Agents (`.agents/agents/<agent>/AGENT.md`)
- [ ] Job state and moves (`factory/bin/job`)
- [ ] Agent runner (`factory/bin/agent`)
- [ ] Config (`factory/config.json`)
- [ ] Install and docs (`INSTALL.md`, `README.md`)

## Acceptance criteria

<!-- Each requested outcome with what you observed, or mark it unmet or
     unverified. -->

## Reproduction

<!-- For a bug fix: the starting state, steps, and expected versus actual
     behaviour before the fix, then what happens after it. Remove this
     section when it doesn't apply. -->

## Verification

<!-- The checks you ran and their results, for example:
     - python3 -m py_compile factory/bin/job factory/bin/agent
     - python3 -m json.tool factory/config.json
     - factory/bin/agent --help, and every AGENT.md has cli, model and effort
     - a real run on a test repo: issue, job id, final stage, PR
     Name the harness (Claude Code, Pi, Codex) and CLI versions you used, and
     any check that failed or wasn't run. -->

## Docs and limits

<!-- Docs updated, anything an existing install must change by hand
     (config keys, labels), unsupported harnesses, and follow-up work. -->
