/**
 * ReEnrollDialog honesty: success is declared only after a heartbeat that is
 * NEWER than the pre-enrollment reading, together with a bumped
 * credential_version and is_revoked=false. A host that reported before
 * revocation keeps an old non-null last_seen_at — that stale value must never
 * be mistaken for "connected with the new credential".
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReenrollDialog } from "../host/CredentialDialogs";
import type { Host } from "../../api/types";

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

const revokedHost = {
  id: "h-rev",
  hostname: "revoked-vm",
  status: "REVOKED",
  agent_version: "0.1.0",
  platform: "Linux",
  platform_release: "6.8",
  cpu_cores: 2,
  total_memory_bytes: 8,
  boot_time: null,
  enrolled_at: "2026-11-16T07:00:00Z",
  // Reported BEFORE revocation: non-null, must never count as post-enroll proof.
  last_seen_at: "2026-11-16T08:00:00Z",
  last_telemetry_at: "2026-11-16T08:00:00Z",
  latest_metrics: null,
  is_revoked: true,
  enrollment_status: "REVOKED",
  docker_enabled: false,
  environment: "PRIVATE",
  credential_version: 1,
} as unknown as Host;

function stubReenrollApi(overrides: { lastSeenAt?: string | null; credentialVersion?: number; isRevoked?: boolean } = {}) {
  return vi.fn(async (url: string) => {
    if (url.includes("/re-enroll")) {
      return jsonResponse({ bootstrap_token: "boot-once-token", expires_at: "2026-11-16T09:00:00Z", hostname: "revoked-vm" }, 201);
    }
    if (url.includes("/hosts/h-rev")) {
      return jsonResponse({
        ...revokedHost,
        is_revoked: overrides.isRevoked ?? false,
        credential_version: overrides.credentialVersion ?? 2,
        last_seen_at: overrides.lastSeenAt !== undefined ? overrides.lastSeenAt : "2026-11-16T08:00:00Z",
      });
    }
    return jsonResponse({}, 404);
  }) as unknown as ReturnType<typeof vi.fn> & { _seq?: (string | null)[] };
}

/** Stub whose host readings move through a sequence of last_seen_at values. */
function stubSequencedReenrollApi(sequence: (string | null)[], finalIsRevoked = false) {
  let call = 0;
  return vi.fn(async (url: string) => {
    if (url.includes("/re-enroll")) {
      return jsonResponse({ bootstrap_token: "boot-once-token", expires_at: "2026-11-16T09:00:00Z", hostname: "revoked-vm" }, 201);
    }
    if (url.includes("/hosts/h-rev")) {
      const lastSeenAt = sequence[Math.min(call, sequence.length - 1)];
      call += 1;
      return jsonResponse({
        ...revokedHost,
        is_revoked: finalIsRevoked,
        credential_version: 2,
        last_seen_at: lastSeenAt,
      });
    }
    return jsonResponse({}, 404);
  });
}

function renderDialog() {
  return render(
    <ReenrollDialog host={revokedHost} isOpen onClose={() => {}} onSuccess={() => {}} pollIntervalMs={10} />
  );
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("ReenrollDialog success honesty", () => {
  it("does not declare success from the stale pre-revocation heartbeat alone", async () => {
    vi.stubGlobal("fetch", stubReenrollApi({ lastSeenAt: "2026-11-16T08:00:00Z" }));
    renderDialog();

    // Token issued; polling runs against a host whose last_seen_at is still
    // the old pre-revocation value. Success must NOT be declared.
    expect(await screen.findByText(/boot-once-token/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/Waiting for agent to connect/)).toBeInTheDocument());
    await new Promise((r) => setTimeout(r, 80));
    expect(screen.queryByTestId("reenroll-success")).not.toBeInTheDocument();
  });

  it("declares success only when a fresh post-enrollment heartbeat arrives", async () => {
    // Reading 1 captures the stale baseline; reading 2 still shows the old
    // heartbeat (agent has not enrolled yet); reading 3 is the new heartbeat.
    vi.stubGlobal("fetch", stubSequencedReenrollApi(["2026-11-16T08:00:00Z", "2026-11-16T08:00:00Z", "2026-11-16T08:30:00Z"]));
    renderDialog();

    expect(await screen.findByText(/boot-once-token/)).toBeInTheDocument();
    await waitFor(
      () => expect(screen.getByTestId("reenroll-success")).toBeInTheDocument(),
      { timeout: 3000 }
    );
    expect(screen.getByText(/fresh heartbeat/i)).toBeInTheDocument();
  });

  it("keeps waiting when the fresh heartbeat belongs to a still-revoked credential", async () => {
    vi.stubGlobal("fetch", stubSequencedReenrollApi(["2026-11-16T08:00:00Z", "2026-11-16T08:30:00Z"], true));
    renderDialog();

    expect(await screen.findByText(/boot-once-token/)).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 120));
    expect(screen.queryByTestId("reenroll-success")).not.toBeInTheDocument();
  });

  it("never declares success while the credential is still revoked", async () => {
    vi.stubGlobal("fetch", stubReenrollApi({ lastSeenAt: "2026-11-16T08:30:00Z", isRevoked: true }));
    renderDialog();

    expect(await screen.findByText(/boot-once-token/)).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 80));
    expect(screen.queryByTestId("reenroll-success")).not.toBeInTheDocument();
  });
});
