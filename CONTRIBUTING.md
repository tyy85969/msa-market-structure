# Contributing to MSA

All contributors and automated agents must read AGENTS.md before changing this repository.

## Branch policy

The main branch is the stable, reviewed version of the project. Work must be isolated on a branch or worktree using one of these prefixes:

- chore/ for repository and maintenance work;
- feature/ for approved implementation work;
- research/ for hypotheses and experiments;
- audit/ for independent validation and review;
- fix/ for defects.

## Workflow

Issue → Branch / Worktree → Implementation → Tests → Pull Request → Review → Merge

Every pull request must identify its issue, state its scope and exclusions, list the validation performed, and disclose lookahead or repaint relevance.

## Research discipline

- New model behavior requires a documented H-XXX hypothesis and a reproducible EXP-XXX experiment.
- Research branches must not copy experimental results directly into the formal Pine core.
- Experimental conclusions remain provisional until reviewed against development, validation, and out-of-sample data.
- OriginTime and ConfirmTime must remain distinct in designs, tests, metrics, and reports.

## Agent coordination

Multiple agents must not refactor the same core file concurrently. For important changes, separate the Writer role from the Auditor role whenever practical. The Writer produces the scoped change; the Auditor checks requirements, no-lookahead discipline, tests, and out-of-scope drift.

## Pull request readiness

Before requesting review:

1. run all relevant tests;
2. confirm no private data, secrets, or large raw screenshots are tracked;
3. confirm the change contains no unapproved trading algorithm or signal behavior;
4. update documentation and the changelog when the project contract changes;
5. record known limitations and deferred work.
