import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { Dialog } from "@/components/ui/overlay";
import { KeyValues, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Alert, Tag } from "@/components/ui/status";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { errorMessage, useAsync } from "@/lib/useAsync";

/** Mirrors RetentionPolicy in apps/api/drikr_api/services/settings_service.py. null disables a rule. */
export interface RetentionPolicy {
  session_event_days: number | null;
  auth_record_days: number;
  anonymise_deactivated_after_days: number | null;
}

interface Preview {
  evaluated_at: string;
  session_event_logs: { sessions: number; events: number; older_than: string | null; disabled?: boolean };
  auth_records: { sessions: number; mfa_challenges: number; older_than: string };
  accounts_to_anonymise: { count: number; disabled: boolean };
}

interface RetentionRun {
  id: string;
  trigger: string;
  dry_run: boolean;
  summary: {
    session_event_logs?: { sessions: number; events_deleted?: number; events?: number };
    auth_records?: { sessions_deleted?: number; sessions?: number };
    accounts_anonymised?: number;
    accounts_to_anonymise?: { count: number };
  };
  started_at: string;
  finished_at: string | null;
}

function optionalDays(v: string): number | null {
  return v.trim() === "" ? null : Number(v);
}

export function RetentionPolicyPanel({
  value,
  onChange,
}: {
  value: RetentionPolicy;
  onChange: (v: RetentionPolicy) => void;
}) {
  return (
    <Panel className="lg:col-span-2">
      <PanelHeader
        title="Data retention"
        description="Leave a period empty to keep that data indefinitely. Scores, score explanations and the audit log are never deleted by these rules."
      />
      <PanelBody className="grid gap-3 sm:grid-cols-3">
        <Field
          label="Delete exercise event logs after (days)"
          hint="30 to 3650. Completed sessions keep their score; the detailed timeline is removed."
        >
          <Input
            type="number"
            min={30}
            max={3650}
            placeholder="Keep"
            value={value.session_event_days ?? ""}
            onChange={(e) => onChange({ ...value, session_event_days: optionalDays(e.target.value) })}
          />
        </Field>
        <Field label="Delete expired sign-in records after (days)" hint="1 to 365.">
          <Input
            type="number"
            min={1}
            max={365}
            value={value.auth_record_days}
            onChange={(e) => onChange({ ...value, auth_record_days: Number(e.target.value) })}
          />
        </Field>
        <Field
          label="Anonymise deactivated accounts after (days)"
          hint="30 to 3650, counted from deactivation."
        >
          <Input
            type="number"
            min={30}
            max={3650}
            placeholder="Never"
            value={value.anonymise_deactivated_after_days ?? ""}
            onChange={(e) =>
              onChange({ ...value, anonymise_deactivated_after_days: optionalDays(e.target.value) })
            }
          />
        </Field>
      </PanelBody>
    </Panel>
  );
}

function summaryText(r: RetentionRun): string {
  const s = r.summary;
  const parts = [
    `${s.session_event_logs?.sessions ?? 0} session log(s)`,
    `${s.auth_records?.sessions_deleted ?? s.auth_records?.sessions ?? 0} sign-in record(s)`,
    `${s.accounts_anonymised ?? s.accounts_to_anonymise?.count ?? 0} account(s) anonymised`,
  ];
  return parts.join(", ");
}

export function RetentionRunsPanel({ className }: { className?: string }) {
  const runs = useAsync((sig) => api.get<{ items: RetentionRun[] }>("/admin/retention/runs", sig), []);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [msg, setMsg] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadPreview() {
    setMsg(null);
    setBusy(true);
    try {
      setPreview(await api.get<Preview>("/admin/retention/preview"));
    } catch (err) {
      setMsg({ tone: "danger", text: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  async function execute() {
    setBusy(true);
    try {
      const r = await api.post<RetentionRun>("/admin/retention/run", { dry_run: false });
      setMsg({ tone: "success", text: `Retention run complete: ${summaryText(r)}.` });
      setPreview(null);
      runs.reload();
    } catch (err) {
      setMsg({ tone: "danger", text: errorMessage(err) });
    } finally {
      setBusy(false);
      setConfirmOpen(false);
    }
  }

  return (
    <Panel className={className}>
      <PanelHeader
        title="Apply the retention policy"
        description="Uses the saved policy. Preview first; every run is recorded here and in the audit log."
        actions={
          <div className="flex gap-2">
            <Button variant="secondary" onClick={loadPreview} disabled={busy}>
              Preview
            </Button>
            <Button variant="danger" onClick={() => setConfirmOpen(true)} disabled={busy || !preview}>
              Run now
            </Button>
          </div>
        }
      />
      <PanelBody className="space-y-4">
        {msg ? <Alert tone={msg.tone}>{msg.text}</Alert> : null}
        {preview ? (
          <KeyValues
            items={[
              [
                "Exercise event logs",
                preview.session_event_logs.disabled
                  ? "Kept (rule off)"
                  : `${preview.session_event_logs.sessions} session(s), ${preview.session_event_logs.events.toLocaleString()} events`,
              ],
              [
                "Expired sign-in records",
                `${preview.auth_records.sessions} session(s), ${preview.auth_records.mfa_challenges} MFA challenge(s)`,
              ],
              [
                "Accounts to anonymise",
                preview.accounts_to_anonymise.disabled
                  ? "None (rule off)"
                  : String(preview.accounts_to_anonymise.count),
              ],
              ["Evaluated", formatDateTime(preview.evaluated_at)],
            ]}
          />
        ) : (
          <p className="text-sm text-ink-muted">Preview to see what the saved policy would remove.</p>
        )}
        {runs.loading ? (
          <LoadingState rows={2} />
        ) : runs.error ? (
          <ErrorState error={runs.error} onRetry={runs.reload} />
        ) : !runs.data?.items.length ? (
          <EmptyState title="No retention runs yet" />
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Started</TH>
                <TH>Trigger</TH>
                <TH>Type</TH>
                <TH>Result</TH>
              </TR>
            </THead>
            <TBody>
              {runs.data.items.map((r) => (
                <TR key={r.id}>
                  <TD className="whitespace-nowrap text-xs">{formatDateTime(r.started_at)}</TD>
                  <TD className="text-xs">{r.trigger}</TD>
                  <TD>
                    <Tag tone={r.dry_run ? "neutral" : "warning"}>{r.dry_run ? "Dry run" : "Executed"}</Tag>
                  </TD>
                  <TD className="text-xs">{summaryText(r)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </PanelBody>
      <Dialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Delete data now?"
        description="Removes the data shown in the preview. This cannot be undone; restore a backup to recover it."
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={execute} disabled={busy}>
              Delete data
            </Button>
          </>
        }
      />
    </Panel>
  );
}
