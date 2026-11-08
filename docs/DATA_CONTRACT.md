# NimbusOps Data Integrity Contract — Phase 1

Normative definitions for telemetry meaning, units, and status thresholds.
Backend, agent, and dashboard all follow this document.

## Metric units and bounds

| Metric | Unit | Valid range | Source (agent) |
| --- | --- | --- | --- |
| CPU usage | percent of total capacity | 0.0–100.0 | `psutil.cpu_percent(interval=0.2)` (real sampling window) |
| RAM used / total | bytes | used ≤ total | `psutil.virtual_memory()` (`total - available`, `total`) |
| RAM usage | percent | 0.0–100.0 | `psutil.virtual_memory().percent` |
| Disk used / total | bytes | used ≤ total | `psutil.disk_usage("/")` (`used`, `total`) |
| Disk usage | percent | 0.0–100.0 | `psutil.disk_usage("/").percent` |

- Percentages are validated server-side (Pydantic ge/le) and re-derived for
  storage; out-of-range or `used > total` payloads are rejected with 422.
- RAM "used" is `total - available` (includes cache/reclaimable), matching
  what `free(1)` reports as used on Ubuntu. Tolerance for OS comparison:
  ±2 percentage points against `free`/`top` readings taken at the same time.

## Timestamps

- All timestamps are **UTC ISO-8601**; JSON serialization uses the `Z`
  suffix convention (e.g. `2026-11-08T12:34:56Z`).
- `recorded_at` is set by the **agent** (when the sample was taken); the
  server stores it verbatim. The server also records `last_seen_at` (its own
  clock, at receive time) — the difference is exposed as telemetry age.
- Dashboard displays are labeled "UTC" explicitly.

## Sampling and thresholds (defaults, all env-tunable)

| Parameter | Default | Meaning |
| --- | --- | --- |
| Sampling interval | 30 s | Agent collects + posts telemetry and heartbeat each interval |
| Stale threshold | 90 s | No heartbeat for this long ⇒ host is STALE (3× interval) |
| Offline threshold | 600 s | No heartbeat for this long ⇒ host is OFFLINE (10 min) |
| Retention | 1440 rows/host | ~12 h at 30 s sampling; oldest rows pruned on insert |

## Status semantics (single source of truth: `services/hosts.compute_status`)

| State | Condition | UI meaning |
| --- | --- | --- |
| `ONLINE` | last heartbeat ≤ 90 s ago | current telemetry, agent reporting |
| `STALE` | heartbeat 90–600 s ago | telemetry exists but may be outdated; UI must warn |
| `OFFLINE` | no heartbeat ever, or > 600 s ago | metrics are historical only; UI must warn |

- **Missing telemetry is never zero.** A host with no samples shows
  `null` metrics (API) and `—` (UI), plus "No telemetry received".
- **Stale telemetry is never presented as current.** STALE/OFFLINE hosts
  carry explicit warnings adjacent to their (historical) values.
- A successful HTTP response from agent endpoints confirms **receipt**, not
  host health: health is computed solely from heartbeat recency.
- Agents behind on their clocks: `recorded_at` skew is not corrected; the
  server-side `last_seen_at` drives status, and telemetry age is computed
  from the server clock, so a skewed client cannot fake freshness.
