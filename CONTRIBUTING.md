# Contributing to Zenith AI Lab

This is a deliberately small public experiment repository. Helpful contributions are narrowly scoped, reproducible, and safe to publish.

## Before creating work

1. Read [README.md](README.md) and [AGENTS.md](AGENTS.md).
2. Agree on one measurable experiment or bug and its stop conditions. An agent must have the owner's authorisation before being dispatched or taking consequential action.
3. Confirm you can access the repository. If you can only read it, supply a review, suggested patch, or test case without claiming to have pushed code.

## Suggested structure

- `experiments/<short-name>/`: minimal source, a brief README with setup/run commands, and tests or negative cases.
- `evidence/<short-name>/`: sanitised test output, reproducible inputs, expected/observed distinctions, and limitations.
- Keep third-party dependencies and external network requirements explicit. Prefer local, cheap, disposable experiments.

## Pull-request checklist

- [ ] Explains the question, scope, and expected result.
- [ ] Lists changed files and why they are needed.
- [ ] Supplies exact test commands and **observed**, not invented, results.
- [ ] Includes at least one meaningful negative or failure case where relevant.
- [ ] Confirms no secrets, private-source material, or personal information were exposed.
- [ ] States untested areas, rollback or revert path, and any approval still needed.

Use one responsible implementer per task; review independently where it adds value. No automatic merging, deployments, background polling, or chains of agent handoffs.

## Public content and rights

GitHub issues, PRs, commits, and history are public. Do not post private project material or personal information even as an example. No licence has been selected for this repository; do not assume publication means unrestricted reuse.
