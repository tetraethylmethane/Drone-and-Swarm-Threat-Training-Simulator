import { useState, type FormEvent } from "react";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { KeyValues, PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Alert } from "@/components/ui/status";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { label, ROLE_LABELS } from "@/lib/labels";
import { errorMessage } from "@/lib/useAsync";

import { MfaPanel } from "./MfaPanel";

export const PasswordSchema = z
  .object({
    current_password: z.string().min(1, "Enter your current password"),
    new_password: z
      .string()
      .min(12, "Use at least 12 characters")
      .max(128, "Use at most 128 characters")
      .refine(
        (v) => [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(v)).length >= 3,
        "Use at least three of: lowercase, uppercase, digit, symbol",
      ),
    confirm: z.string(),
  })
  .refine((d) => d.new_password === d.confirm, { path: ["confirm"], message: "Passwords do not match" })
  .refine((d) => d.new_password !== d.current_password, {
    path: ["new_password"],
    message: "Choose a different password",
  });

type Fields = "current_password" | "new_password" | "confirm";

export function AccountPage() {
  const { user, refresh } = useAuth();
  const [values, setValues] = useState({ current_password: "", new_password: "", confirm: "" });
  const [errors, setErrors] = useState<Partial<Record<Fields, string>>>({});
  const [status, setStatus] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  if (!user) return null;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setStatus(null);
    const parsed = PasswordSchema.safeParse(values);
    if (!parsed.success) {
      const fe: typeof errors = {};
      for (const i of parsed.error.issues) fe[i.path[0] as Fields] ??= i.message;
      setErrors(fe);
      return;
    }
    setErrors({});
    setBusy(true);
    try {
      await api.post("/auth/change-password", {
        current_password: values.current_password,
        new_password: values.new_password,
      });
      setValues({ current_password: "", new_password: "", confirm: "" });
      setStatus({ tone: "success", text: "Password changed. Other sessions have been signed out." });
      await refresh();
    } catch (err) {
      const details =
        err instanceof ApiError && Array.isArray(err.details)
          ? ` (${(err.details as string[]).join("; ")})`
          : "";
      setStatus({ tone: "danger", text: errorMessage(err) + details });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Account and security" />
      {user.must_change_password ? (
        <Alert tone="warning" title="Password change required" className="mb-4">
          An administrator set a temporary password for this account. Choose a new password to continue.
        </Alert>
      ) : null}
      {user.mfa_enrollment_required ? (
        <Alert tone="warning" title="Multi-factor authentication required" className="mb-4">
          Your role requires an authenticator app. Set it up below to continue; until then only this page is
          available.
        </Alert>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="Profile" />
          <PanelBody>
            <KeyValues
              items={[
                ["Name", user.display_name],
                ["Username", user.username],
                ["Role", label(ROLE_LABELS, user.role)],
              ]}
            />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader
            title="Change password"
            description="At least 12 characters, using three of: lowercase, uppercase, digit, symbol."
          />
          <PanelBody>
            <form onSubmit={submit} noValidate className="space-y-3">
              <Field label="Current password" error={errors.current_password}>
                <Input
                  type="password"
                  autoComplete="current-password"
                  value={values.current_password}
                  onChange={(e) => setValues((v) => ({ ...v, current_password: e.target.value }))}
                />
              </Field>
              <Field label="New password" error={errors.new_password}>
                <Input
                  type="password"
                  autoComplete="new-password"
                  value={values.new_password}
                  onChange={(e) => setValues((v) => ({ ...v, new_password: e.target.value }))}
                />
              </Field>
              <Field label="Confirm new password" error={errors.confirm}>
                <Input
                  type="password"
                  autoComplete="new-password"
                  value={values.confirm}
                  onChange={(e) => setValues((v) => ({ ...v, confirm: e.target.value }))}
                />
              </Field>
              {status ? <Alert tone={status.tone}>{status.text}</Alert> : null}
              <Button type="submit" disabled={busy}>
                {busy ? "Saving" : "Change password"}
              </Button>
            </form>
          </PanelBody>
        </Panel>
        <MfaPanel />
      </div>
    </>
  );
}
