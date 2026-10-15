import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { KeyValues, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Alert, Tag } from "@/components/ui/status";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { errorMessage, useAsync } from "@/lib/useAsync";

interface MfaStatus {
  enabled: boolean;
  enabled_at: string | null;
  required: boolean;
  recovery_codes_remaining: number;
}

interface Setup {
  secret: string;
  otpauth_uri: string;
  qr_svg_base64: string;
}

type Step =
  | { kind: "idle" }
  | { kind: "password" }
  | { kind: "scan"; setup: Setup }
  | { kind: "codes"; codes: string[] }
  | { kind: "regenerate" }
  | { kind: "disable" };

/** Save recovery codes as a plain-text file; nothing is sent anywhere. */
export function downloadCodes(username: string, codes: string[]): void {
  const text = [
    "Drikr Systems training simulator: multi-factor recovery codes",
    `Account: ${username}`,
    `Created: ${new Date().toISOString()}`,
    "Each code works once. Store this file offline.",
    "",
    ...codes,
    "",
  ].join("\n");
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `drikr-recovery-codes-${username}.txt`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function MfaPanel() {
  const { user, refresh } = useAuth();
  const st = useAsync((sig) => api.get<MfaStatus>("/auth/mfa", sig), []);
  const [step, setStep] = useState<Step>({ kind: "idle" });
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!user) return null;

  function reset(next: Step = { kind: "idle" }) {
    setStep(next);
    setPassword("");
    setCode("");
    setError(null);
  }

  async function run(e: FormEvent, fn: () => Promise<void>) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await fn();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const status = st.data;
  const codeField = (
    <Field label="Code from your authenticator app">
      <Input
        autoComplete="one-time-code"
        inputMode="numeric"
        value={code}
        onChange={(e) => setCode(e.target.value.trim())}
      />
    </Field>
  );
  const passwordField = (
    <Field label="Current password">
      <Input
        type="password"
        autoComplete="current-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
    </Field>
  );
  const errorAlert = error ? <Alert tone="danger">{error}</Alert> : null;
  const cancel = (
    <Button type="button" variant="secondary" onClick={() => reset()}>
      Cancel
    </Button>
  );

  let body;
  if (st.loading) body = <LoadingState rows={2} />;
  else if (st.error || !status) body = <ErrorState error={st.error} onRetry={st.reload} />;
  else if (step.kind === "codes")
    body = (
      <div className="space-y-3">
        <Alert tone="warning" title="Save your recovery codes now">
          Each code signs you in once if your authenticator is unavailable. They are not shown again.
        </Alert>
        <ul aria-label="Recovery codes" className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm tabular">
          {step.codes.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="secondary" onClick={() => downloadCodes(user.username, step.codes)}>
            Download codes
          </Button>
          <Button
            type="button"
            onClick={async () => {
              reset();
              st.reload();
              await refresh();
            }}
          >
            I have saved these codes
          </Button>
        </div>
      </div>
    );
  else if (step.kind === "password")
    body = (
      <form
        className="space-y-3"
        noValidate
        onSubmit={(e) =>
          run(e, async () => {
            const setup = await api.post<Setup>("/auth/mfa/setup", { current_password: password });
            reset({ kind: "scan", setup });
          })
        }
      >
        <p className="text-sm text-ink-muted">Confirm your password to create a new authenticator key.</p>
        {passwordField}
        {errorAlert}
        <div className="flex gap-2">
          <Button type="submit" disabled={busy || !password}>
            Continue
          </Button>
          {cancel}
        </div>
      </form>
    );
  else if (step.kind === "scan")
    body = (
      <form
        className="space-y-3"
        noValidate
        onSubmit={(e) =>
          run(e, async () => {
            const res = await api.post<{ recovery_codes: string[] }>("/auth/mfa/enable", { code });
            setNotice("Multi-factor authentication is on. Other sessions were signed out.");
            reset({ kind: "codes", codes: res.recovery_codes });
          })
        }
      >
        <p className="text-sm text-ink-muted">
          Scan the code with an authenticator app (any app that supports time-based codes), then enter the
          6-digit code it shows.
        </p>
        <img
          src={`data:image/svg+xml;base64,${step.setup.qr_svg_base64}`}
          alt="QR code for adding this account to an authenticator app"
          width={176}
          height={176}
          className="rounded-sm border border-border bg-white p-2"
        />
        <p className="text-xs text-ink-muted">
          Cannot scan? Enter this key manually:{" "}
          <span className="break-all font-medium text-ink tabular">{step.setup.secret}</span>
        </p>
        {codeField}
        {errorAlert}
        <div className="flex gap-2">
          <Button type="submit" disabled={busy || code.length < 6}>
            Turn on
          </Button>
          {cancel}
        </div>
      </form>
    );
  else if (step.kind === "regenerate")
    body = (
      <form
        className="space-y-3"
        noValidate
        onSubmit={(e) =>
          run(e, async () => {
            const res = await api.post<{ recovery_codes: string[] }>("/auth/mfa/recovery-codes", { code });
            setNotice("New recovery codes created. The previous codes no longer work.");
            reset({ kind: "codes", codes: res.recovery_codes });
          })
        }
      >
        <p className="text-sm text-ink-muted">Creating new recovery codes invalidates all unused codes.</p>
        {codeField}
        {errorAlert}
        <div className="flex gap-2">
          <Button type="submit" disabled={busy || code.length < 6}>
            Create new codes
          </Button>
          {cancel}
        </div>
      </form>
    );
  else if (step.kind === "disable")
    body = (
      <form
        className="space-y-3"
        noValidate
        onSubmit={(e) =>
          run(e, async () => {
            await api.post("/auth/mfa/disable", { current_password: password, code });
            setNotice("Multi-factor authentication is off.");
            reset();
            st.reload();
            await refresh();
          })
        }
      >
        {passwordField}
        <Field label="Authenticator or recovery code">
          <Input autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value.trim())} />
        </Field>
        {errorAlert}
        <div className="flex gap-2">
          <Button type="submit" variant="danger" disabled={busy || !password || code.length < 6}>
            Turn off
          </Button>
          {cancel}
        </div>
      </form>
    );
  else
    body = (
      <div className="space-y-3">
        <KeyValues
          items={[
            [
              "Status",
              <Tag key="s" tone={status.enabled ? "success" : status.required ? "warning" : "neutral"}>
                {status.enabled ? "On" : status.required ? "Required, not set up" : "Off"}
              </Tag>,
            ],
            ...(status.enabled
              ? ([
                  ["Turned on", status.enabled_at ? formatDateTime(status.enabled_at) : "—"],
                  ["Recovery codes left", String(status.recovery_codes_remaining)],
                ] as [string, string][])
              : []),
            ["Policy", status.required ? "Required for your role" : "Optional for your role"],
          ]}
        />
        {status.enabled && status.recovery_codes_remaining <= 2 ? (
          <Alert tone="warning">Few recovery codes remain. Create new ones.</Alert>
        ) : null}
        <div className="flex flex-wrap gap-2">
          {status.enabled ? (
            <>
              <Button variant="secondary" onClick={() => reset({ kind: "regenerate" })}>
                New recovery codes
              </Button>
              {!status.required ? (
                <Button variant="ghost" onClick={() => reset({ kind: "disable" })}>
                  Turn off
                </Button>
              ) : null}
            </>
          ) : (
            <Button onClick={() => reset({ kind: "password" })}>Set up authenticator</Button>
          )}
        </div>
      </div>
    );

  return (
    <Panel>
      <PanelHeader
        title="Multi-factor authentication"
        description="Sign-in also asks for a 6-digit code from an authenticator app on a device you keep with you."
      />
      <PanelBody className="space-y-3">
        {notice && step.kind !== "codes" ? <Alert tone="success">{notice}</Alert> : null}
        {body}
      </PanelBody>
    </Panel>
  );
}
