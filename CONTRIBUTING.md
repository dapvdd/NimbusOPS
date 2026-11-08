# Contributing to NimbusOps

NimbusOps is a small academic group project at Universitas Gadjah Mada. Keep
changes focused, reviewable, and supported by evidence.

## Before starting

1. Read the [PRD digest](docs/PRD.md), [architecture](docs/ARCHITECTURE.md), and
   [roadmap](docs/ROADMAP.md). The source PRD is still labeled draft/review required.
2. Agree on task scope and ownership with the group. Owners and reviewer assignments
   are not yet confirmed. Record unresolved requirements rather than inventing them.
3. Check `git status --short --branch` and preserve existing local work.
4. Create a focused branch from the agreed baseline. Phase 0 uses
   `docs/nimbusops-foundation`; later work may use `feat/`, `fix/`, or `docs/` prefixes.

## Change conventions

- Use the product name **NimbusOps**; the GitHub repository name is **NimbusOPS**.
- Use UTF-8 Markdown, descriptive headings, and repository-relative document links.
- Distinguish requirements, proposals, implementation, and verified results.
- Reference PRD requirement IDs and acceptance criteria where applicable.
- Use conventional commits, for example `docs: clarify monitoring acceptance gate`.
- Avoid unrelated cleanup, speculative frameworks, and unnecessary dependencies.
- Phase 0 permits documentation and repository hygiene only: no application code,
  dependencies, Compose services, deployment, or infrastructure provisioning.

## Validation and review

Before committing, review `git diff --stat`, `git diff`, and `git diff --check`.
Check Markdown headings, tables, code fences, and relative links. Verify that each
completion claim has evidence and that only intended files are staged with
`git diff --cached --name-status` and `git diff --cached --check`.

There is no application test suite or CI pipeline yet. Documentation-only work
requires document checks, not invented runtime results. Future feature changes
must include checks appropriate to the phase acceptance criteria and describe how
to reproduce them using an isolated test host.

Request group review with a summary, scope, validation evidence, and open issues.
Push, merge, and deployment require explicit authorization for this Phase 0 task;
its delivery is a local commit. Do not rewrite history or force-push.

## Secrets and host safety

Never commit `.env` files, SSH private keys, Tailscale auth keys, cloud credentials,
database contents, or unsanitized logs/screenshots. `.gitignore` is a preventive
filter, not proof that content is safe. Inspect new and staged files before commit.
If a credential is discovered, do not quote it in an issue or commit; notify the
owner privately and arrange revocation/rotation before any approved remediation.

No runtime variables are defined yet, so there is no `.env.example`. Add one with
placeholders only when actual configuration requirements exist. Never copy a
working secret into an example.

Use isolated Ubuntu VMs for future testing. Do not expose the Docker TCP API or
allow arbitrary shell commands. Production DavidLab is not an authorized mutation
target; any future use needs separate approval and a rollback plan.
