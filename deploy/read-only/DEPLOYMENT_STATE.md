# Read-only public deployment

## Complete

- VPS services are running behind Nginx on ports 80 and 443.
- The application and database pass their container health checks.
- Copy-trading polling is disabled; no local accounts, private keys, database data, or Bridge profile were transferred.
- The database migration for a fresh MySQL deployment was corrected and verified during this deployment.

## Pending external action

- Replace the existing `www.spaceflag.site` CNAME with an A record to `173.199.122.23`.
- After DNS propagation, issue the Let's Encrypt certificate and verify `https://www.spaceflag.site`.
