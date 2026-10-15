import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";

import { Wordmark } from "@/components/layout/Wordmark";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { Alert } from "@/components/ui/status";
import { ApiError } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth";
import type { Me } from "@/lib/types";
import { errorMessage } from "@/lib/useAsync";

const LoginSchema = z.object({
  username: z.string().trim().min(1, "Enter your username").max(64),
  password: z.string().min(1, "Enter your password").max(256),
});

const CodeSchema = z
  .string()
  .trim()
  .regex(/^(\d{6}|[A-Za-z0-9]{5}-?[A-Za-z0-9]{5})$/, "Enter the 6-digit code or a recovery code");

export function LoginPage() {
  const { user, login, verifyMfa } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [values, setValues] = useState({ username: "", password: "" });
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<"username" | "password", string>>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [codeError, setCodeError] = useState<string | null>(null);

  if (user) return <Navigate to={homeFor(user.role)} replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const parsed = LoginSchema.safeParse(values);
    if (!parsed.success) {
      const fe: typeof fieldErrors = {};
      for (const issue of parsed.error.issues) fe[issue.path[0] as "username" | "password"] = issue.message;
      setFieldErrors(fe);
      return;
    }
    setFieldErrors({});
    setBusy(true);
    try {
      const res = await login(parsed.data.username.toLowerCase(), parsed.data.password);
      if (res.kind === "mfa_required") {
        setMfaToken(res.mfaToken);
        setValues((v) => ({ ...v, password: "" }));
      } else {
        go(res.user);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function go(me: Me) {
    const from = (location.state as { from?: string } | null)?.from;
    const mustVisitAccount = me.must_change_password || me.mfa_enrollment_required;
    navigate(mustVisitAccount ? "/account" : (from ?? homeFor(me.role)), { replace: true });
  }

  async function onVerify(e: FormEvent) {
    e.preventDefault();
    if (!mfaToken) return;
    setError(null);
    const parsed = CodeSchema.safeParse(code);
    if (!parsed.success) {
      setCodeError(parsed.error.issues[0]?.message ?? "Enter a code");
      return;
    }
    setCodeError(null);
    setBusy(true);
    try {
      go(await verifyMfa(mfaToken, parsed.data));
    } catch (err) {
      // An expired or exhausted challenge cannot be retried: start again from the password.
      if (err instanceof ApiError && err.code !== "mfa_code_invalid") {
        setMfaToken(null);
        setCode("");
      }
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-[380px]">
        <div className="mb-6">
          <Wordmark height={26} />
          <p className="mt-3 text-sm text-ink-muted">Drone and swarm recognition training simulator</p>
        </div>
        {mfaToken ? (
          <form
            onSubmit={onVerify}
            noValidate
            className="rounded-md border border-border bg-surface p-5 shadow-panel"
          >
            <h1 className="text-base">Verification code</h1>
            <p className="mt-1 text-sm text-ink-muted">
              Enter the 6-digit code from your authenticator app, or one of your recovery codes.
            </p>
            <div className="mt-4 space-y-4">
              <Field label="Code" error={codeError ?? undefined}>
                <Input
                  name="code"
                  autoComplete="one-time-code"
                  inputMode="text"
                  autoCapitalize="none"
                  spellCheck={false}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
              </Field>
              {error ? <Alert tone="danger">{error}</Alert> : null}
              <Button type="submit" className="w-full" disabled={busy}>
                {busy ? "Verifying" : "Verify and sign in"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="w-full"
                onClick={() => {
                  setMfaToken(null);
                  setCode("");
                  setError(null);
                }}
              >
                Use a different account
              </Button>
            </div>
          </form>
        ) : (
          <form
            onSubmit={onSubmit}
            noValidate
            className="rounded-md border border-border bg-surface p-5 shadow-panel"
          >
            <h1 className="text-base">Sign in</h1>
            <div className="mt-4 space-y-4">
              <Field label="Username" error={fieldErrors.username}>
                <Input
                  name="username"
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  value={values.username}
                  onChange={(e) => setValues((v) => ({ ...v, username: e.target.value }))}
                />
              </Field>
              <Field label="Password" error={fieldErrors.password}>
                <Input
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  value={values.password}
                  onChange={(e) => setValues((v) => ({ ...v, password: e.target.value }))}
                />
              </Field>
              {error ? <Alert tone="danger">{error}</Alert> : null}
              <Button type="submit" className="w-full" disabled={busy}>
                {busy ? "Signing in" : "Sign in"}
              </Button>
            </div>
          </form>
        )}
        <p className="mt-4 text-xs leading-relaxed text-ink-subtle">
          Authorised training use only. All tracks, sensor readings and events in this application are
          synthetic and exist only inside the virtual exercise environment.
        </p>
      </div>
    </div>
  );
}
