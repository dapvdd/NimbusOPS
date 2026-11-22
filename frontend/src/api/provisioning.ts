import { request } from './client';
export interface SetupPlan {
  target_id: string; validation_id: string; approval_hash: string; expires_at: number;
  facts: Record<string, string>; changes: string[];
}
export interface SetupJob {
  id: string; state: string; step: string; reason_code: string | null;
  reconciliation_required: boolean; retry_allowed: boolean;
   events: { sequence: number; code: string; at: number; safe_detail?: {transport_exit_status?: number} }[];
}
export const provisioning = {
  targets: () => request<{targets: {id: string; hostname: string; address: string}[]}>('/provisioning/targets'),
  preflight: (target_id: string) => request<SetupPlan>('/provisioning/preflight', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({target_id}),
  }),
  recover: (key: string) => request<{id: string; state: string}>(`/provisioning/requests/${encodeURIComponent(key)}`),
  confirm: (plan: SetupPlan, idempotency_key: string) => request<{id: string; state: string}>('/provisioning/confirm', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({idempotency_key, target_id: plan.target_id,
      validation_id: plan.validation_id, approval_hash: plan.approval_hash, confirmed: true}),
  }),
  job: (id: string) => request<SetupJob>(`/provisioning/jobs/${encodeURIComponent(id)}`),
  retry: (id: string) => request<{target_id: string}>(`/provisioning/jobs/${encodeURIComponent(id)}/retry`, {method: 'POST'}),
};
