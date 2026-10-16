import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/form";
import { Checkbox, Dialog } from "@/components/ui/overlay";
import { KeyValues, PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Alert, Tag } from "@/components/ui/status";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, ApiError, qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { label, ROLE_LABELS } from "@/lib/labels";
import type { Page, Role, UserOut } from "@/lib/types";
import { errorMessage, useAsync } from "@/lib/useAsync";

import { RetentionPolicyPanel, RetentionRunsPanel, type RetentionPolicy } from "./RetentionPanel";

const NewUserSchema = z.object({
  username: z
    .string()
    .regex(/^[a-z0-9][a-z0-9._-]{2,63}$/, "3–64 lowercase letters, digits, dots, hyphens or underscores"),
  display_name: z.string().trim().min(2, "Enter a name").max(120),
  role: z.enum(["administrator", "instructor", "trainee"]),
  password: z.string().min(12, "At least 12 characters"),
  unit: z.string().trim().max(80, "At most 80 characters"),
});

function detailText(err: unknown): string {
  const extra =
    err instanceof ApiError && Array.isArray(err.details) && typeof err.details[0] === "string"
      ? `: ${(err.details as string[]).join("; ")}`
      : "";
  return errorMessage(err) + extra;
}

export function UsersPage() {
  const { user: me } = useAuth();
  const [q, setQ] = useState("");
  const [inactive, setInactive] = useState(false);
  const st = useAsync(
    (sig) => api.get<Page<UserOut>>(`/users${qs({ q, include_inactive: inactive, limit: 200 })}`, sig),
    [q, inactive],
  );
  const [createOpen, setCreateOpen] = useState(false);
  const [resetFor, setResetFor] = useState<UserOut | null>(null);
  const [anonymiseFor, setAnonymiseFor] = useState<UserOut | null>(null);
  const [unitFor, setUnitFor] = useState<UserOut | null>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  async function patch(u: UserOut, body: Record<string, unknown>, done: string) {
    setMsg(null);
    try {
      await api.patch(`/users/${u.id}`, body);
      setMsg({ tone: "success", text: done });
      st.reload();
    } catch (err) {
      setMsg({ tone: "danger", text: detailText(err) });
    }
  }

  return (
    <>
      <PageHeader title="Users" actions={<Button onClick={() => setCreateOpen(true)}>Add user</Button>} />
      {msg ? (
        <Alert tone={msg.tone} className="mb-3">
          {msg.text}
        </Alert>
      ) : null}
      <Panel>
        <div className="flex flex-wrap items-end gap-4 border-b border-border px-4 py-3">
          <Field label="Search" className="w-64">
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name or username" />
          </Field>
          <Checkbox
            id="inactive"
            checked={inactive}
            onCheckedChange={setInactive}
            label="Include deactivated accounts"
          />
        </div>
        {st.loading ? (
          <LoadingState rows={5} />
        ) : st.error ? (
          <ErrorState error={st.error} onRetry={st.reload} />
        ) : !st.data?.items.length ? (
          <EmptyState title="No users found" />
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Name</TH>
                <TH>Username</TH>
                <TH>Role</TH>
                <TH>Unit</TH>
                <TH>Status</TH>
                <TH>Created</TH>
                <TH>
                  <span className="sr-only">Actions</span>
                </TH>
              </TR>
            </THead>
            <TBody>
              {st.data.items.map((u) => (
                <TR key={u.id}>
                  <TD className="font-medium">{u.display_name}</TD>
                  <TD>{u.username}</TD>
                  <TD>
                    <Select
                      aria-label={`Role for ${u.username}`}
                      className="h-8 w-36 text-xs"
                      value={u.role}
                      disabled={u.id === me?.id || Boolean(u.anonymised_at)}
                      onChange={(e) =>
                        patch(
                          u,
                          { role: e.target.value },
                          `Role updated for ${u.username}. Their sessions were signed out.`,
                        )
                      }
                    >
                      {(["administrator", "instructor", "trainee"] as const).map((r) => (
                        <option key={r} value={r}>
                          {label(ROLE_LABELS, r)}
                        </option>
                      ))}
                    </Select>
                  </TD>
                  <TD className="text-sm">
                    {u.anonymised_at ? (
                      (u.unit ?? "—")
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`Unit for ${u.username}: ${u.unit ?? "none"}. Change`}
                        onClick={() => setUnitFor(u)}
                      >
                        {u.unit ?? "Set unit"}
                      </Button>
                    )}
                  </TD>
                  <TD className="space-x-1">
                    <Tag tone={u.is_active ? "success" : "neutral"}>
                      {u.is_active ? "Active" : "Deactivated"}
                    </Tag>
                    {u.locked ? <Tag tone="danger">Locked</Tag> : null}
                    {u.must_change_password ? <Tag tone="warning">Password change due</Tag> : null}
                    {u.mfa_enabled ? <Tag tone="info">MFA on</Tag> : null}
                    {u.anonymised_at ? <Tag tone="neutral">Anonymised</Tag> : null}
                  </TD>
                  <TD className="text-xs">{formatDateTime(u.created_at)}</TD>
                  <TD className="whitespace-nowrap text-right">
                    {u.locked ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={async () => {
                          try {
                            await api.post(`/users/${u.id}/unlock`);
                            st.reload();
                          } catch (err) {
                            setMsg({ tone: "danger", text: errorMessage(err) });
                          }
                        }}
                      >
                        Unlock
                      </Button>
                    ) : null}
                    {u.anonymised_at ? null : (
                      <Button size="sm" variant="ghost" onClick={() => setResetFor(u)}>
                        Reset password
                      </Button>
                    )}
                    {u.mfa_enabled && u.id !== me?.id ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={async () => {
                          setMsg(null);
                          try {
                            await api.post(`/users/${u.id}/reset-mfa`);
                            setMsg({
                              tone: "success",
                              text: `Multi-factor authentication reset for ${u.username}. They were signed out and must set it up again if their role requires it.`,
                            });
                            st.reload();
                          } catch (err) {
                            setMsg({ tone: "danger", text: errorMessage(err) });
                          }
                        }}
                      >
                        Reset MFA
                      </Button>
                    ) : null}
                    {!u.is_active && !u.anonymised_at ? (
                      <Button size="sm" variant="ghost" onClick={() => setAnonymiseFor(u)}>
                        Anonymise
                      </Button>
                    ) : null}
                    {u.id !== me?.id && !u.anonymised_at ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          patch(
                            u,
                            { is_active: !u.is_active },
                            `${u.username} ${u.is_active ? "deactivated" : "reactivated"}.`,
                          )
                        }
                      >
                        {u.is_active ? "Deactivate" : "Reactivate"}
                      </Button>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Panel>
      <CreateUserDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={() => {
          st.reload();
          setMsg({ tone: "success", text: "User created. They must change the password at first sign-in." });
        }}
      />
      <ResetPasswordDialog
        user={resetFor}
        onClose={() => setResetFor(null)}
        onDone={(n) => setMsg({ tone: "success", text: `Temporary password set for ${n}.` })}
      />
      <UnitDialog
        user={unitFor}
        onClose={() => setUnitFor(null)}
        onDone={(n, unit) => {
          st.reload();
          setMsg({
            tone: "success",
            text: unit ? `${n} is now in unit ${unit}.` : `${n} is no longer in a unit.`,
          });
        }}
      />
      <AnonymiseDialog
        user={anonymiseFor}
        onClose={() => setAnonymiseFor(null)}
        onDone={(n) => {
          st.reload();
          setMsg({
            tone: "success",
            text: `${n} was anonymised. Their scores remain as pseudonymous records.`,
          });
        }}
      />
    </>
  );
}

function CreateUserDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreated: () => void;
}) {
  const [form, setForm] = useState({
    username: "",
    display_name: "",
    role: "trainee",
    password: "",
    unit: "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (open) {
      setForm({ username: "", display_name: "", role: "trainee", password: "", unit: "" });
      setErrors({});
      setError(null);
    }
  }, [open]);
  async function submit() {
    const p = NewUserSchema.safeParse(form);
    if (!p.success) {
      const fe: Record<string, string> = {};
      for (const i of p.error.issues) fe[String(i.path[0])] ??= i.message;
      setErrors(fe);
      return;
    }
    setErrors({});
    try {
      await api.post("/users", { ...p.data, unit: p.data.unit || null });
      onOpenChange(false);
      onCreated();
    } catch (err) {
      setError(detailText(err));
    }
  }
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Add user"
      description="The user must change this temporary password at first sign-in."
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit}>Create user</Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="Username" error={errors.username}>
          <Input
            autoComplete="off"
            value={form.username}
            onChange={(e) => setForm((f) => ({ ...f, username: e.target.value.toLowerCase() }))}
          />
        </Field>
        <Field label="Display name" error={errors.display_name}>
          <Input
            value={form.display_name}
            onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
          />
        </Field>
        <Field label="Role">
          <Select value={form.role} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}>
            {(["trainee", "instructor", "administrator"] as const).map((r) => (
              <option key={r} value={r}>
                {label(ROLE_LABELS, r)}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          label="Unit (optional)"
          hint="Team, section or course, for unit-level reports."
          error={errors.unit}
        >
          <Input value={form.unit} onChange={(e) => setForm((f) => ({ ...f, unit: e.target.value }))} />
        </Field>
        <Field
          label="Temporary password"
          hint="At least 12 characters, three of: lowercase, uppercase, digit, symbol."
          error={errors.password}
        >
          <Input
            type="password"
            autoComplete="new-password"
            value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
          />
        </Field>
        {error ? <Alert tone="danger">{error}</Alert> : null}
      </div>
    </Dialog>
  );
}

function ResetPasswordDialog({
  user,
  onClose,
  onDone,
}: {
  user: UserOut | null;
  onClose: () => void;
  onDone: (username: string) => void;
}) {
  const [pw, setPw] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setPw("");
    setError(null);
  }, [user]);
  return (
    <Dialog
      open={user !== null}
      onOpenChange={(v) => !v && onClose()}
      title={`Reset password for ${user?.username ?? ""}`}
      description="Signs the user out everywhere and requires a password change at next sign-in."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={async () => {
              if (!user) return;
              try {
                await api.post(`/users/${user.id}/reset-password`, { new_password: pw });
                onDone(user.username);
                onClose();
              } catch (err) {
                setError(detailText(err));
              }
            }}
          >
            Set temporary password
          </Button>
        </>
      }
    >
      <Field label="Temporary password">
        <Input
          type="password"
          autoComplete="new-password"
          value={pw}
          onChange={(e) => setPw(e.target.value)}
        />
      </Field>
      {error ? (
        <Alert tone="danger" className="mt-3">
          {error}
        </Alert>
      ) : null}
    </Dialog>
  );
}

function UnitDialog({
  user,
  onClose,
  onDone,
}: {
  user: UserOut | null;
  onClose: () => void;
  onDone: (username: string, unit: string | null) => void;
}) {
  const [unit, setUnit] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setUnit(user?.unit ?? "");
    setError(null);
  }, [user]);
  return (
    <Dialog
      open={user !== null}
      onOpenChange={(v) => !v && onClose()}
      title={`Unit for ${user?.username ?? ""}`}
      description="Units group trainees for unit-level reports. Leave empty to remove the user from their unit."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={async () => {
              if (!user) return;
              try {
                const out = await api.patch<UserOut>(`/users/${user.id}`, { unit: unit.trim() || null });
                onDone(user.username, out.unit ?? null);
                onClose();
              } catch (err) {
                setError(detailText(err));
              }
            }}
          >
            Save unit
          </Button>
        </>
      }
    >
      <Field label="Unit">
        <Input value={unit} maxLength={80} onChange={(e) => setUnit(e.target.value)} />
      </Field>
      {error ? (
        <Alert tone="danger" className="mt-3">
          {error}
        </Alert>
      ) : null}
    </Dialog>
  );
}

function AnonymiseDialog({
  user,
  onClose,
  onDone,
}: {
  user: UserOut | null;
  onClose: () => void;
  onDone: (username: string) => void;
}) {
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setConfirm("");
    setError(null);
  }, [user]);
  return (
    <Dialog
      open={user !== null}
      onOpenChange={(v) => !v && onClose()}
      title={`Anonymise ${user?.username ?? ""}`}
      description="Permanent. Replaces the name and username with a pseudonym, deletes this person's exercise event logs, notes and review text, and removes sign-in data. Scores are kept for cohort statistics. The audit log keeps its history."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="danger"
            disabled={!user || confirm !== user.username}
            onClick={async () => {
              if (!user) return;
              try {
                await api.post(`/users/${user.id}/anonymise`, { confirm_username: confirm });
                onDone(user.username);
                onClose();
              } catch (err) {
                setError(detailText(err));
              }
            }}
          >
            Anonymise permanently
          </Button>
        </>
      }
    >
      <Field label={`Type ${user?.username ?? "the username"} to confirm`}>
        <Input autoComplete="off" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      </Field>
      {error ? (
        <Alert tone="danger" className="mt-3">
          {error}
        </Alert>
      ) : null}
    </Dialog>
  );
}

interface SettingsShape {
  adaptive_policy: {
    window: number;
    min_sessions: number;
    promote_mean: number;
    promote_min_each: number;
    demote_mean: number;
    high_confidence_max_stdev: number;
  };
  self_guided_enabled: boolean;
  mfa_required_roles: Role[];
  retention_policy: RetentionPolicy;
}

export function SettingsPage() {
  const st = useAsync((sig) => api.get<SettingsShape>("/admin/settings", sig), []);
  const [form, setForm] = useState<SettingsShape | null>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  useEffect(() => {
    if (st.data) setForm(st.data);
  }, [st.data]);
  if (st.loading || !form)
    return st.error ? <ErrorState error={st.error} onRetry={st.reload} /> : <LoadingState />;
  const p = form.adaptive_policy;
  const setP = (k: keyof SettingsShape["adaptive_policy"], v: number) =>
    setForm({ ...form, adaptive_policy: { ...p, [k]: v } });
  const fields: [keyof SettingsShape["adaptive_policy"], string, string][] = [
    ["window", "Sessions considered", "Most recent scored sessions used for each recommendation."],
    ["min_sessions", "Minimum sessions", "Below this, difficulty is held with low confidence."],
    ["promote_mean", "Increase when mean is at least (%)", ""],
    ["promote_min_each", "…and every recent score is at least (%)", ""],
    ["demote_mean", "Decrease when mean is below (%)", ""],
    [
      "high_confidence_max_stdev",
      "High confidence when spread is at most (points)",
      "Population standard deviation of recent scores.",
    ],
  ];
  return (
    <>
      <PageHeader
        title="Settings"
        description="Changes are recorded in the audit log with before and after values."
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader
            title="Adaptive difficulty policy"
            description="Rules-based; applied after each scored adaptive session. Instructor bounds always apply."
          />
          <PanelBody className="grid gap-3 sm:grid-cols-2">
            {fields.map(([k, l, h]) => (
              <Field key={k} label={l} hint={h || undefined}>
                <Input type="number" value={p[k]} onChange={(e) => setP(k, Number(e.target.value))} />
              </Field>
            ))}
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Training options" />
          <PanelBody className="space-y-3">
            <Checkbox
              id="self-guided-enabled"
              checked={form.self_guided_enabled}
              onCheckedChange={(v) => setForm({ ...form, self_guided_enabled: v })}
              label="Allow trainees to start self-guided practice"
            />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader
            title="Multi-factor authentication"
            description="Accounts in these roles must use an authenticator app. Until they set it up they can only reach their account page."
          />
          <PanelBody className="space-y-3">
            {(["administrator", "instructor", "trainee"] as const).map((r) => (
              <Checkbox
                key={r}
                id={`mfa-${r}`}
                checked={form.mfa_required_roles.includes(r)}
                onCheckedChange={(v) =>
                  setForm({
                    ...form,
                    mfa_required_roles: v
                      ? [...form.mfa_required_roles, r]
                      : form.mfa_required_roles.filter((x) => x !== r),
                  })
                }
                label={`Require for ${label(ROLE_LABELS, r).toLowerCase()}s`}
              />
            ))}
            <p className="text-xs text-ink-subtle">
              To require it for administrators, first turn it on for your own account.
            </p>
          </PanelBody>
        </Panel>
        <RetentionPolicyPanel
          value={form.retention_policy}
          onChange={(retention_policy) => setForm({ ...form, retention_policy })}
        />
      </div>
      {msg ? (
        <Alert tone={msg.tone} className="mt-4">
          {msg.text}
        </Alert>
      ) : null}
      <Button
        className="mt-4"
        onClick={async () => {
          setMsg(null);
          try {
            setForm(await api.put<SettingsShape>("/admin/settings", form));
            setMsg({ tone: "success", text: "Settings saved." });
          } catch (err) {
            const d =
              err instanceof ApiError && Array.isArray(err.details)
                ? `: ${(err.details as { message: string }[]).map((x) => x.message).join("; ")}`
                : "";
            setMsg({ tone: "danger", text: errorMessage(err) + d });
          }
        }}
      >
        Save settings
      </Button>
      <RetentionRunsPanel className="mt-6" />
    </>
  );
}

interface AuditItem {
  id: number;
  occurred_at: string;
  actor_username: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  details: Record<string, unknown>;
  ip_address: string | null;
  hash: string;
}

const AUDIT_PAGE = 50;

export function AuditPage() {
  const [action, setAction] = useState("");
  const [offset, setOffset] = useState(0);
  const st = useAsync(
    (sig) => api.get<Page<AuditItem>>(`/audit${qs({ action, limit: AUDIT_PAGE, offset })}`, sig),
    [action, offset],
  );
  const [verify, setVerify] = useState<{
    valid: boolean;
    checked: number;
    first_invalid_id: number | null;
    reason: string | null;
    head_hash?: string;
  } | null>(null);
  return (
    <>
      <PageHeader
        title="Audit log"
        description="Append-only, hash-chained record of privileged actions. The chain makes tampering detectable; it does not by itself prevent tampering by a database superuser."
        actions={
          <Button variant="secondary" onClick={async () => setVerify(await api.get("/audit/verify"))}>
            Verify chain
          </Button>
        }
      />
      {verify ? (
        <Alert
          tone={verify.valid ? "success" : "danger"}
          className="mb-3"
          title={
            verify.valid
              ? `Chain intact (${verify.checked} events checked)`
              : `Chain broken at event ${verify.first_invalid_id}`
          }
        >
          {verify.valid ? (
            <span className="break-all text-xs">Head hash {verify.head_hash}</span>
          ) : (
            verify.reason
          )}
        </Alert>
      ) : null}
      <Panel>
        <div className="border-b border-border px-4 py-3">
          <Field label="Action starts with" className="w-64">
            <Input
              value={action}
              onChange={(e) => {
                setAction(e.target.value);
                setOffset(0);
              }}
              placeholder="e.g. user. or report."
            />
          </Field>
        </div>
        {st.loading ? (
          <LoadingState rows={6} />
        ) : st.error ? (
          <ErrorState error={st.error} onRetry={st.reload} />
        ) : !st.data?.items.length ? (
          <EmptyState title="No audit events match" />
        ) : (
          <>
            <Table>
              <THead>
                <TR>
                  <TH>#</TH>
                  <TH>When</TH>
                  <TH>Actor</TH>
                  <TH>Action</TH>
                  <TH>Target</TH>
                  <TH>Details</TH>
                </TR>
              </THead>
              <TBody>
                {st.data.items.map((e) => (
                  <TR key={e.id}>
                    <TD className="tabular text-xs">{e.id}</TD>
                    <TD className="whitespace-nowrap text-xs">{formatDateTime(e.occurred_at)}</TD>
                    <TD className="text-xs">{e.actor_username ?? "system"}</TD>
                    <TD className="text-xs font-medium">{e.action}</TD>
                    <TD className="text-xs">
                      {e.target_type ? `${e.target_type} ${e.target_id?.slice(0, 8) ?? ""}` : "—"}
                    </TD>
                    <TD
                      className="max-w-md truncate text-xs text-ink-muted"
                      title={JSON.stringify(e.details)}
                    >
                      {JSON.stringify(e.details)}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            <div className="flex items-center justify-between border-t border-border px-4 py-2 text-xs text-ink-muted">
              <span>
                {offset + 1}–{Math.min(offset + AUDIT_PAGE, st.data.total)} of {st.data.total}
              </span>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={offset === 0}
                  onClick={() => setOffset((o) => Math.max(0, o - AUDIT_PAGE))}
                >
                  Newer
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={offset + AUDIT_PAGE >= st.data.total}
                  onClick={() => setOffset((o) => o + AUDIT_PAGE)}
                >
                  Older
                </Button>
              </div>
            </div>
          </>
        )}
      </Panel>
    </>
  );
}

interface SystemInfo {
  versions: Record<string, string>;
  database: { status: string; latency_ms: number; size_bytes: number };
  counts: Record<string, number>;
  audit_chain: { valid: boolean; checked: number; reason: string | null };
  simulation: { engine: string; visual_clients: string };
  network: { external_runtime_dependencies: string[]; telemetry: string };
  performance?: {
    since: string;
    uptime_s: number;
    requests_total: number;
    window: number;
    overall: { p50_ms: number; p95_ms: number; server_errors: number };
    routes: {
      route: string;
      requests: number;
      p50_ms: number;
      p95_ms: number;
      max_ms: number;
      server_errors: number;
    }[];
    note: string;
  };
}

interface ReproReport {
  counts: {
    checked: number;
    reproducible: number;
    not_reproducible: number;
    exact_score_match: number;
    same_assessment_older_engine: number;
    event_log_purged: number;
  };
  scoring_engine_versions: Record<string, number>;
  failures: { session_id: string; completed_at: string | null; reason: string; note: string | null }[];
  duration_s: number;
  method: string;
}

const REPRO_REASONS: Record<string, string> = {
  timeline_differs: "Timeline no longer regenerates identically",
  stored_log_changed: "Stored event log was changed",
  score_differs: "Re-scoring gives a different assessment",
  other: "Other",
};

function ReproducibilityPanel() {
  const [report, setReport] = useState<ReproReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Panel className="lg:col-span-2">
      <PanelHeader
        title="Reproducibility"
        description="Re-checks recent completed sessions: regenerate each timeline from its stored configuration and seed, compare it with the stored log, and re-score it."
        actions={
          <Button
            variant="secondary"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError(null);
              try {
                setReport(await api.get<ReproReport>("/admin/reproducibility?limit=50"));
              } catch (err) {
                setError(errorMessage(err));
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "Checking" : "Check last 50 sessions"}
          </Button>
        }
      />
      <PanelBody className="space-y-3">
        {error ? <Alert tone="danger">{error}</Alert> : null}
        {!report ? (
          <p className="text-sm text-ink-muted">
            Not run in this view yet. Each run is recorded in the audit log.
          </p>
        ) : (
          <>
            <Alert
              tone={report.counts.not_reproducible ? "danger" : "success"}
              title={`${report.counts.reproducible} of ${report.counts.checked} sessions reproduced (${report.duration_s} s)`}
            >
              {report.counts.exact_score_match} identical score output;{" "}
              {report.counts.same_assessment_older_engine} scored by an earlier engine with the same
              assessment; {report.counts.event_log_purged} with the event log removed by retention. Engines:{" "}
              {Object.entries(report.scoring_engine_versions)
                .map(([k, v]) => `${k} (${v})`)
                .join(", ") || "none"}
              .
            </Alert>
            {report.failures.length ? (
              <Table>
                <THead>
                  <TR>
                    <TH>Session</TH>
                    <TH>Completed</TH>
                    <TH>Reason</TH>
                  </TR>
                </THead>
                <TBody>
                  {report.failures.map((f) => (
                    <TR key={f.session_id}>
                      <TD>
                        <Link className="text-brand hover:underline" to={`/sessions/${f.session_id}/result`}>
                          {f.session_id.slice(0, 8)}
                        </Link>
                      </TD>
                      <TD className="text-xs">{formatDateTime(f.completed_at)}</TD>
                      <TD className="text-sm">{REPRO_REASONS[f.reason] ?? f.reason}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            ) : null}
          </>
        )}
      </PanelBody>
    </Panel>
  );
}

function PerformancePanel({ perf }: { perf: NonNullable<SystemInfo["performance"]> }) {
  return (
    <Panel className="lg:col-span-2">
      <PanelHeader
        title="Measured performance"
        description={`${perf.note} ${perf.requests_total.toLocaleString()} requests since ${formatDateTime(perf.since)}; overall median ${perf.overall.p50_ms} ms, 95th percentile ${perf.overall.p95_ms} ms, ${perf.overall.server_errors} server error(s).`}
      />
      {!perf.routes.length ? (
        <EmptyState title="No requests measured yet" />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Endpoint</TH>
              <TH>Requests</TH>
              <TH>Median</TH>
              <TH>95th percentile</TH>
              <TH>Slowest</TH>
              <TH>Server errors</TH>
            </TR>
          </THead>
          <TBody>
            {perf.routes.map((r) => (
              <TR key={r.route}>
                <TD className="text-xs">{r.route}</TD>
                <TD className="tabular">{r.requests.toLocaleString()}</TD>
                <TD className="tabular">{r.p50_ms} ms</TD>
                <TD className="tabular">{r.p95_ms} ms</TD>
                <TD className="tabular">{r.max_ms} ms</TD>
                <TD className="tabular">{r.server_errors}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </Panel>
  );
}

export function SystemPage() {
  const st = useAsync((sig) => api.get<SystemInfo>("/admin/system", sig), []);
  if (st.loading) return <LoadingState rows={6} />;
  if (st.error || !st.data) return <ErrorState error={st.error} onRetry={st.reload} />;
  const s = st.data;
  return (
    <>
      <PageHeader
        title="System health"
        actions={
          <Button variant="secondary" onClick={st.reload}>
            Refresh
          </Button>
        }
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="Versions" />
          <PanelBody>
            <KeyValues items={Object.entries(s.versions).map(([k, v]) => [k.replace(/_/g, " "), v])} />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Database" />
          <PanelBody>
            <KeyValues
              items={[
                [
                  "Status",
                  <Tag key="s" tone="success">
                    {s.database.status}
                  </Tag>,
                ],
                ["Query latency", `${s.database.latency_ms} ms`],
                ["Size", `${(s.database.size_bytes / 1024 / 1024).toFixed(1)} MB`],
                ...Object.entries(s.counts).map(
                  ([k, v]) => [k.replace(/_/g, " "), v.toLocaleString()] as [string, string],
                ),
              ]}
            />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Integrity" />
          <PanelBody>
            <KeyValues
              items={[
                [
                  "Audit chain",
                  <Tag key="a" tone={s.audit_chain.valid ? "success" : "danger"}>
                    {s.audit_chain.valid
                      ? `Intact (${s.audit_chain.checked} events)`
                      : `Broken: ${s.audit_chain.reason}`}
                  </Tag>,
                ],
              ]}
            />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Simulation and network" />
          <PanelBody>
            <KeyValues
              items={[
                ["Simulation engine", s.simulation.engine],
                ["Visual clients", s.simulation.visual_clients],
                [
                  "External runtime dependencies",
                  s.network.external_runtime_dependencies.length
                    ? s.network.external_runtime_dependencies.join(", ")
                    : "None",
                ],
                ["Telemetry", s.network.telemetry],
              ]}
            />
          </PanelBody>
        </Panel>
        {s.performance ? <PerformancePanel perf={s.performance} /> : null}
        <ReproducibilityPanel />
      </div>
    </>
  );
}
