# Bridge Execution Loop State

## Goal

For the VPS Bridge, eliminate reproducible BUY/SELL execution failures that
occur after a signal has passed the configured copy-trading guards.

## Stop Condition

- Current Bridge health and status are ready and logged in.
- No stale `PENDING` bridge records remain.
- New post-fix qualifying signals complete without browser selector, dialog, or
  target-market execution errors.
- Each non-success record has a configured guard reason (price, whitelist,
  duplicate-market, or insufficient position) rather than an execution error.

## Latest Evidence

- Fixed binary-market target-page verification and rejected sidebar-only titles.
- Fixed binary `Up Or Down` category labels being mistaken for the tradable
  `Up` / `Down` outcomes.
- VPS Bridge image `polyhermes-bridge:linux-amd64` was committed with the
  current executor source after the remote build did not complete.
- Real post-fix records `402` and `420` were ETH BUYs with status `SUCCESS`.
- Subsequent records through `439` were all explicit configured-guard skips;
  no new browser execution errors or stale `PENDING` records were observed.
- `polymtrade-bridge/test_selector_fixture.py` completed with Python warnings
  promoted to errors, and `git diff --check` completed cleanly.

## Completion Audit

- Post-fix records `402+`: two real ETH BUY successes; all remaining BUY/SELL
  failures have explicit configured guard reasons.
- No unclassified post-fix Bridge failures and no `PENDING` records remain.
- Bridge `/health` is OK; `/status` is ready and logged in.
- The running container and the persisted image carry the same executor hash.
