# Portfolio access rejection: diagnosis and safe release gate

## Incident evidence (2026-10-15, Asia/Shanghai)

The Bridge browser retained an already-loaded, signed-in home page, but a new
portfolio navigation returned `403: Forbidden`, `This request was blocked`, and
zero position rows. Same-browser reads of `/` and `/portfolio` both returned
HTTP 403 at 00:42, with `server: Vercel` and
`cache-control: private, no-store, max-age=0`.

This proves an upstream access rejection. It does not establish whether the
cause is IP reputation, rate limiting, an account rule, or a regional rule.
The signed-in page and Bridge readiness do not prove that new requests work.

The previous reader ignored the navigation response status, waited for rows,
scraped an incomplete result, and created another page. Repeating that loop
could not repair the HTTP denial. An empty result here is unknown holdings,
not an empty account.

## Narrow client repair

- Preserve the navigation response and detect portfolio HTTP 401/403/429.
- Fail before scraping or recreating a page, with an explicit upstream error,
  `portfolio_complete=false`, and `empty_state_confirmed=false`.
- Invalidate the old complete snapshot and defer further portfolio navigation
  for 300 seconds, including forced execution reads. A later successful read
  clears the failure state; no previously failed signal is replayed.
- Leave wallet data, browser profile, cookies, login state, trading settings,
  and existing fail-closed execution guards unchanged.
- A visible `portfolio-error-banner` keeps even valid rows incomplete: they may
  be cached. Do not advance the last successful synchronization time or enrich
  those rows as a complete live snapshot.
- Repeated render failures also enter the cooldown after one fresh-page retry.
  Do not overwrite login state based on a failed portfolio page, or navigate a
  second time merely to obtain the account's already-resolved wallet address.

## Release gate

This client repair does **not** remove the upstream rejection or establish
that holdings are readable. Do not change proxy, fingerprint, account, or risk
rules to work around it, and do not interpret a locally passing test as live
portfolio recovery.

Before activating a Bridge release, confirm that the platform permits normal
access from the server, fresh signed-in pages work, and a fresh complete
portfolio can be read. If the upstream denial persists, preserve the existing
browser rather than restarting it merely to activate this patch; request
platform assistance with the access rejection.

Once access is restored: verify admission drain, no queued/in-flight trade or
verification task, and preserved wallet/configuration state. Deploy only the
reviewed Bridge file, retain the persistent browser-profile volume, and verify
the served file hash, login, fresh portfolio completeness, and enforced risk
mode. Never backfill trades to verify recovery.
