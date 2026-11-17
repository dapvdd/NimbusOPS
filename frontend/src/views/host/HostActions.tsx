import { useState } from "react";
import { api, ApiFailure } from "../../api/client";
import type { Host } from "../../api/types";
import { useAdmin } from "../../auth/Session";
import { Button } from "../../ui/Button";
import { ConfirmDialog } from "../../ui/ConfirmDialog";
import { ReenrollDialog, RotateCredentialDialog } from "./CredentialDialogs";

export interface HostActionsProps {
  host: Host;
  onRefresh: () => void;
}

export default function HostActions({ host, onRefresh }: HostActionsProps) {
  const admin = useAdmin();

  const [showRevoke, setShowRevoke] = useState(false);
  const [showRotate, setShowRotate] = useState(false);
  const [showReenroll, setShowReenroll] = useState(false);

  const [busyRevoke, setBusyRevoke] = useState(false);
  const [revokeError, setRevokeError] = useState<string | null>(null);

  if (!admin) return null;

  const isRevoked = host.is_revoked || host.status === "REVOKED";

  const handleRevoke = async () => {
    setBusyRevoke(true);
    setRevokeError(null);
    try {
      await api.revokeHost(host.id);
      setShowRevoke(false);
      onRefresh();
    } catch (err) {
      setRevokeError(err instanceof ApiFailure ? err.message : "Failed to revoke host.");
    } finally {
      setBusyRevoke(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-3">
      {!isRevoked && (
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => setShowRotate(true)}
        >
          Rotate credential
        </Button>
      )}

      <Button
        type="button"
        variant={isRevoked ? "primary" : "secondary"}
        size="sm"
        onClick={() => setShowReenroll(true)}
      >
        Re-enroll
      </Button>

      {!isRevoked && (
        <Button
          type="button"
          variant="danger"
          size="sm"
          onClick={() => {
            setRevokeError(null);
            setShowRevoke(true);
          }}
        >
          Revoke host
        </Button>
      )}

      {/* Revoke Typed Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showRevoke}
        title={`Revoke ${host.hostname}?`}
        consequences={[
          "The agent's credential is revoked: it receives 401 on its next call and stops reporting.",
          "The host becomes a tombstone: telemetry and history are retained, never deleted.",
          "Containers and files on the host are NOT removed; clean them up manually if desired.",
        ]}
        expectedValue={host.hostname}
        confirmLabel="Confirm revoke"
        variant="danger"
        busy={busyRevoke}
        error={revokeError}
        onConfirm={handleRevoke}
        onClose={() => {
          if (!busyRevoke) setShowRevoke(false);
        }}
      />

      {/* Rotate Credential Dialog */}
      <RotateCredentialDialog
        host={host}
        isOpen={showRotate}
        onClose={() => setShowRotate(false)}
        onSuccess={onRefresh}
      />

      {/* Re-enroll Dialog */}
      <ReenrollDialog
        host={host}
        isOpen={showReenroll}
        onClose={() => setShowReenroll(false)}
        onSuccess={onRefresh}
      />
    </div>
  );
}
