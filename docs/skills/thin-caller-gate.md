---
name: thin-caller-gate
description: Enforce the thin-caller size contract on workflows that delegate to projectbluefin/actions. Use when adding or reviewing a caller workflow, wiring the gate into a repo's CI, or answering why a reusable caller is too large.
metadata:
  type: reference
---

# Thin-Caller Gate in the projectbluefin Actions Factory

## When to Use

Use when reviewing or adding a GitHub Actions workflow that `uses:` a
`projectbluefin/actions` reusable, when wiring the gate into a repo's CI, or
when a caller workflow is growing and someone asks whether it should be
extracted into a reusable instead.

## When NOT to Use

- Do not use it for workflows that call only third-party or in-repo actions
  (anything not under `projectbluefin/actions`).
- Do not use it to measure the reusable implementations themselves
  (`reusable-*.yml`, `bootc-build/*/action.yml`) — those are the extraction
  target, not callers.
- Do not treat a weekly drift warning as a pre-merge block; the gate is meant
  to fail the build, not just report it.

## Core Process

1. A caller workflow is any file under `.github/workflows/` with an active
   (non-comment) `uses:` line referencing `projectbluefin/actions`.
2. Count its effective lines (non-blank, non-comment). The threshold is 50.
3. Run the canonical validator:

   ```bash
   python3 scripts/validate_thin_caller.py --max-lines 50 --root .
   ```

   Exit 0 passes; exit 1 lists each violating workflow and its line count.
4. On a violation, extract the logic into a reusable workflow in
   `projectbluefin/actions`, advance `@v1`, and keep the caller thin.

Enforcement is published as the reusable
`.github/workflows/reusable-thin-caller-gate.yml` (issue #546). Consumer repos
call it from their own PR checks so a caller that exceeds the threshold fails
before it reaches that repo's `main`:

```yaml
jobs:
  thin-caller-gate:
    uses: projectbluefin/actions/.github/workflows/reusable-thin-caller-gate.yml@v1
```

The reusable re-checks-out `projectbluefin/actions@v1` and runs the same
`validate_thin_caller.py`, so every consumer enforces the identical rule and
single source of truth is preserved.

## Common Rationalizations

- "It's only a few lines over." — drift is cumulative; a 55-line caller today
  is a 120-line monolith before anyone notices (the original `promote
  -testing-to-main.yml`).
- "The weekly drift check will catch it." — that is the post-merge-detection
  problem #411 was filed about. Pre-merge is the point.
- "The caller is large because the reusable is incomplete." — that is a signal
  to grow the reusable, not to excuse the caller.

## Red Flags

- A caller workflow that reads like a job definition rather than a pointer.
- New `uses: projectbluefin/actions/...` lines added to an already-thick caller.
- A consumer repo that has not opted into `reusable-thin-caller-gate.yml`
  while siblings have — it is drifting from the contract.

## Verification

- `python3 scripts/validate_thin_caller.py --max-lines 50 --root .` exits 0.
- `pytest tests/` passes; the new gate is covered by
  `tests/test_reusable_thin_caller_gate.py` and the comment-skip case in
  `tests/test_validate_thin_caller.py`.
- `.github/workflows/actionlint.yml` lints the reusable workflow on every PR.
