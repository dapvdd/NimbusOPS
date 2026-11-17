import { useEffect, useRef, useState } from "react";
import { api, ApiFailure } from "../../api/client";
import type { Host } from "../../api/types";
import { Button } from "../../ui/Button";
import { CopyField } from "../../ui/CopyField";
import { formatUtcTime } from "../../lib/format";

/** Keep a callback in a ref so effects never re-fire on identity changes. */
function useLatest<T>(value: T) {
  const ref = useRef(value);
  ref.current = value;
  return ref;
}

interface RotateCredentialDialogProps {
  host: Host;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function RotateCredentialDialog({
  host,
  isOpen,
  onClose,
  onSuccess,
}: RotateCredentialDialogProps) {
  const [issued, setIssued] = useState<{ token: string; graceUntil: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onSuccessRef = useLatest(onSuccess);

  useEffect(() => {
    if (!isOpen) {
      setIssued(null);
      setError(null);
      setBusy(false);
      return;
    }

    let active = true;
    setBusy(true);
    setError(null);
    setIssued(null);

    void (async () => {
      try {
        const res = await api.rotateCredential(host.id);
        if (!active) return;
        setIssued({
          token: res.new_agent_token,
          graceUntil: res.old_token_expires_at,
        });
        onSuccessRef.current();
      } catch (err) {
        if (!active) return;
        setError(err instanceof ApiFailure ? err.message : "Failed to rotate credential.");
      } finally {
        if (active) setBusy(false);
      }
    })();

    return () => {
      active = false;
    };
  }, [isOpen, host.id, onSuccessRef]);

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="rotate-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-950/80 backdrop-blur-sm"
    >
      <div className="w-full max-w-lg rounded-xl border border-ink-700 bg-surface-2 p-6 shadow-2xl space-y-4">
        <h2 id="rotate-dialog-title" className="text-xl font-semibold text-ink-50">
          Rotate Agent Credential
        </h2>

        {busy && (
          <div className="flex items-center gap-3 py-6 text-sm text-ink-300">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-signal-info border-t-transparent" />
            <span>Generating new agent credential…</span>
          </div>
        )}

        {error && (
          <div role="alert" className="rounded-lg border border-signal-bad/40 bg-signal-bad/10 p-3 text-sm text-signal-bad">
            {error}
          </div>
        )}

        {issued && (
          <div className="space-y-4">
            <div className="rounded-lg border border-amber-400/40 bg-amber-400/10 p-4 text-xs text-amber-200 space-y-2">
              <p className="font-semibold text-sm">
                New agent token — shown ONCE. Copy it now.
              </p>
              <p className="text-ink-300">
                This token clears from the screen as soon as you close this dialog. It is never stored or shown again.
              </p>
            </div>

            <CopyField
              label="New Agent Token"
              value={issued.token}
            />

            <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-3 text-xs text-ink-300 space-y-1">
              <p data-testid="grace-deadline" className="font-medium text-ink-200">
                Grace ends {formatUtcTime(issued.graceUntil)} — update the agent before then.
              </p>
              <p className="text-signal-warn">
                Hard warning: The agent must be updated with this new token before grace expires, or its access will be permanently lost and require re-enrollment.
              </p>
            </div>
          </div>
        )}

        <div className="pt-2 flex justify-end">
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
          >
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}

interface ReenrollDialogProps {
  host: Host;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  pollIntervalMs?: number;
}

export function ReenrollDialog({
  host,
  isOpen,
  onClose,
  onSuccess,
  pollIntervalMs = 1000,
}: ReenrollDialogProps) {
  const [issued, setIssued] = useState<{ token: string; expiresAt: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTokenConflict, setActiveTokenConflict] = useState<string | null>(null);
  const [enrolledSuccess, setEnrolledSuccess] = useState(false);

  const initialVersion = useRef(host.credential_version ?? 1);
  // `undefined` = not captured yet. The baseline must be a FRESH post-issuance
  // reading: a host that reported before revocation still has an old non-null
  // last_seen_at, and using it would declare success at token consumption
  // instead of at the first heartbeat with the new credential.
  const baselineSeen = useRef<string | null | undefined>(undefined);
  const onSuccessRef = useLatest(onSuccess);

  const requestReenroll = async (): Promise<boolean> => {
    setBusy(true);
    setError(null);
    setActiveTokenConflict(null);
    baselineSeen.current = undefined;
    try {
      const res = await api.reenrollHost(host.id);
      setIssued({
        token: res.bootstrap_token,
        expiresAt: res.expires_at,
      });
      return true;
    } catch (err) {
      if (err instanceof ApiFailure) {
        if (err.status === 409 || err.code === "BOOTSTRAP_TOKEN_ACTIVE") {
          setActiveTokenConflict(err.message || "An active bootstrap token already exists for this host.");
        } else {
          setError(err.message);
        }
      } else {
        setError("Re-enrollment request failed.");
      }
      return false;
    } finally {
      setBusy(false);
    }
  };

  // One-shot issuance: fires only when the dialog opens for a given host.
  useEffect(() => {
    if (!isOpen) {
      setIssued(null);
      setError(null);
      setActiveTokenConflict(null);
      setEnrolledSuccess(false);
      setBusy(false);
      baselineSeen.current = undefined;
      return;
    }
    initialVersion.current = host.credential_version ?? 1;
    void requestReenroll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, host.id]);

  const handleRevokeAndRetry = async () => {
    setBusy(true);
    setError(null);
    try {
      const tokensRes = await api.listBootstrapTokens({ limit: 50 });
      const staleToken = (tokensRes?.tokens || []).find(
        (t) => t.hostname.toLowerCase() === host.hostname.toLowerCase() && !t.consumed_at && !t.revoked_at
      );
      if (staleToken) {
        await api.revokeBootstrapToken(staleToken.id);
      }
    } catch (err) {
      setError(err instanceof ApiFailure ? err.message : (err as Error)?.message || "Failed to revoke existing token and retry.");
      setBusy(false);
      return;
    }
    await requestReenroll();
  };

  // Polling confirms re-enrollment via credential_version + is_revoked=false
  // + a heartbeat that CHANGED after issuance. Never the RE_ENROLLED event
  // string, and never mere presence of an old last_seen_at.
  useEffect(() => {
    if (!isOpen || !issued || enrolledSuccess) return;

    let stopped = false;
    const interval = setInterval(async () => {
      if (document.visibilityState === "hidden" || stopped) return;
      try {
        const current = await api.getHost(host.id);
        if (stopped) return;
        const versionBumped = (current.credential_version ?? 0) > initialVersion.current;
        if (baselineSeen.current === undefined) {
          // First successful reading: capture the pre-enrollment heartbeat as
          // the baseline; success requires a DIFFERENT (later) heartbeat.
          baselineSeen.current = current.last_seen_at;
          return;
        }
        const activeSeen =
          !current.is_revoked &&
          current.last_seen_at !== null &&
          current.last_seen_at !== baselineSeen.current;
        if (versionBumped && activeSeen) {
          stopped = true;
          setEnrolledSuccess(true);
          clearInterval(interval);
          onSuccessRef.current();
        }
      } catch {
        // ignore polling errors
      }
    }, pollIntervalMs);

    return () => {
      stopped = true;
      clearInterval(interval);
    };
  }, [isOpen, issued, enrolledSuccess, host.id, pollIntervalMs, onSuccessRef]);

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="reenroll-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-950/80 backdrop-blur-sm"
    >
      <div className="w-full max-w-lg rounded-xl border border-ink-700 bg-surface-2 p-6 shadow-2xl space-y-4">
        <h2 id="reenroll-dialog-title" className="text-xl font-semibold text-ink-50">
          Re-enroll Host {host.hostname}
        </h2>

        {busy && (
          <div className="flex items-center gap-3 py-6 text-sm text-ink-300">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-signal-info border-t-transparent" />
            <span>Issuing single-use bootstrap token…</span>
          </div>
        )}

        {error && (
          <div role="alert" className="rounded-lg border border-signal-bad/40 bg-signal-bad/10 p-3 text-sm text-signal-bad">
            {error}
          </div>
        )}

        {activeTokenConflict && (
          <div className="space-y-3 rounded-lg border border-signal-warn/40 bg-signal-warn/10 p-4 text-xs text-signal-warn">
            <p className="font-semibold text-sm">An active token already exists</p>
            <p className="text-ink-300">{activeTokenConflict}</p>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              loading={busy}
              onClick={() => void handleRevokeAndRetry()}
            >
              Revoke existing token & retry
            </Button>
          </div>
        )}

        {issued && !enrolledSuccess && (
          <div className="space-y-4">
            <div className="rounded-lg border border-signal-info/40 bg-signal-info/10 p-4 text-xs text-ink-200 space-y-2">
              <p className="font-semibold text-sm text-signal-info">
                Bootstrap Token — shown ONCE.
              </p>
              <p className="text-ink-300">
                Execute the agent on {host.hostname} with this single-use bootstrap token.
              </p>
            </div>

            <CopyField
              label="Bootstrap Token"
              value={issued.token}
            />

            <div className="flex items-center gap-2 text-xs text-ink-400">
              <div className="h-2 w-2 animate-pulse rounded-full bg-signal-warn" />
              <span>Waiting for agent to connect… (expires {formatUtcTime(issued.expiresAt)})</span>
            </div>
          </div>
        )}

        {enrolledSuccess && (
          <div
            data-testid="reenroll-success"
            className="space-y-3 rounded-lg border border-signal-good/40 bg-signal-good/10 p-4 text-sm text-signal-good"
          >
            <p className="font-semibold">Host successfully re-enrolled!</p>
            <p className="text-xs text-ink-300">
              {host.hostname} has connected with its new credential and sent a fresh heartbeat.
            </p>
          </div>
        )}

        <div className="pt-2 flex justify-end">
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
          >
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}
