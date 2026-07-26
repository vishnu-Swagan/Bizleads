# scripts

## setup_supabase.py

Configures and verifies a Supabase project for BizLeads. Run it after creating
a new project, before touching Render or Vercel.

```bash
app/backend/.venv/bin/python scripts/setup_supabase.py \
  --url https://<new-ref>.supabase.co \
  --anon-key eyJ... \
  --db-password 'your-db-password' \
  --write-env --migrate
```

Omit `--write-env` and `--migrate` for a dry run — it only reports.

### What it handles that catches people out

**The direct database host is IPv6-only.** `db.<ref>.supabase.co` has no A
record. Most home networks and Render cannot reach it, and the failure looks
like a hang, not a DNS error. The script uses the Supavisor pooler instead and
probes the clusters to find which region owns your project — a wrong region
answers "tenant not found", the right one answers "password rejected" or
succeeds, and that difference identifies it.

**The password must be percent-encoded.** An unencoded `@` splits the
connection URL at the wrong place, and `$` gets eaten by the shell. The script
encodes it for you and prints the exact string to paste into Render.

**The pooler username is `postgres.<project-ref>`,** not `postgres`.

**There is no JWT secret to configure.** Supabase signs with ES256 and
publishes a JWKS; the backend verifies against the public key. A value some
dashboards label "JWT Secret" is the public key id, not a credential.
