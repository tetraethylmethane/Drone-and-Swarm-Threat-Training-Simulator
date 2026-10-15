import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RequireAuth } from "@/components/layout/RequireAuth";
import { TimelineSection } from "@/features/aar/AarSections";
import { LoginPage } from "@/features/auth/LoginPage";
import { MfaPanel } from "@/features/auth/MfaPanel";
import { AuthProvider } from "@/lib/auth";
import type { Me } from "@/lib/types";

type Handler = (url: string, init?: RequestInit) => { status: number; body: unknown };

function mockFetch(handler: Handler) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const { status, body } = handler(url, init);
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const unauth = { status: 401, body: { error: { code: "unauthorized", message: "Authentication required" } } };

function me(over: Partial<Me> = {}): Me {
  return {
    id: "u1",
    username: "trainee1",
    display_name: "Demo Trainee One",
    role: "trainee",
    is_active: true,
    must_change_password: false,
    locked: false,
    mfa_enabled: false,
    deactivated_at: null,
    anonymised_at: null,
    permissions: [],
    mfa_required: false,
    mfa_enrollment_required: false,
    ...over,
  };
}

function body(init?: RequestInit): Record<string, unknown> {
  return JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("two-step sign-in", () => {
  function renderLogin() {
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/trainee" element={<p>Trainee home</p>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );
  }

  async function passwordStep() {
    await userEvent.type(await screen.findByLabelText("Username"), "trainee1");
    await userEvent.type(screen.getByLabelText("Password"), "Training-Pass-2026!");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  }

  it("asks for a code after the password and signs in with it", async () => {
    const fetch = mockFetch((url, init) => {
      if (url.endsWith("/auth/login"))
        return { status: 200, body: { mfa_required: true, mfa_token: "challenge-token-1", expires_at: "x" } };
      if (url.endsWith("/auth/mfa/verify")) {
        expect(body(init)).toEqual({ mfa_token: "challenge-token-1", code: "123456" });
        return { status: 200, body: { mfa_required: false, user: me({ mfa_enabled: true }) } };
      }
      return unauth;
    });
    renderLogin();
    await passwordStep();
    const code = await screen.findByLabelText("Code");
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
    await userEvent.type(code, "123456");
    await userEvent.click(screen.getByRole("button", { name: "Verify and sign in" }));
    expect(await screen.findByText("Trainee home")).toBeInTheDocument();
    expect(fetch.mock.calls.some(([u]) => String(u).endsWith("/auth/mfa/verify"))).toBe(true);
  });

  it("validates the code format and keeps the challenge after a wrong code", async () => {
    mockFetch((url) => {
      if (url.endsWith("/auth/login"))
        return { status: 200, body: { mfa_required: true, mfa_token: "challenge-token-1", expires_at: "x" } };
      if (url.endsWith("/auth/mfa/verify"))
        return {
          status: 401,
          body: { error: { code: "mfa_code_invalid", message: "The verification code is not valid" } },
        };
      return unauth;
    });
    renderLogin();
    await passwordStep();
    const code = await screen.findByLabelText("Code");
    await userEvent.type(code, "12");
    await userEvent.click(screen.getByRole("button", { name: "Verify and sign in" }));
    expect(await screen.findByText("Enter the 6-digit code or a recovery code")).toBeInTheDocument();
    await userEvent.clear(code);
    await userEvent.type(code, "654321");
    await userEvent.click(screen.getByRole("button", { name: "Verify and sign in" }));
    expect(await screen.findByText("The verification code is not valid")).toBeInTheDocument();
    expect(screen.getByLabelText("Code")).toBeInTheDocument(); // still on the code step
  });

  it("returns to the password step when the challenge has expired", async () => {
    mockFetch((url) => {
      if (url.endsWith("/auth/login"))
        return { status: 200, body: { mfa_required: true, mfa_token: "challenge-token-1", expires_at: "x" } };
      if (url.endsWith("/auth/mfa/verify"))
        return {
          status: 401,
          body: {
            error: {
              code: "mfa_challenge_invalid",
              message: "The sign-in attempt has expired; sign in again",
            },
          },
        };
      return unauth;
    });
    renderLogin();
    await passwordStep();
    await userEvent.type(await screen.findByLabelText("Code"), "ABCDE-FGHIJ");
    await userEvent.click(screen.getByRole("button", { name: "Verify and sign in" }));
    expect(await screen.findByText("The sign-in attempt has expired; sign in again")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
  });
});

describe("MFA enrolment", () => {
  it("shows the QR code, enables with a code and shows recovery codes once", async () => {
    let enabled = false;
    mockFetch((url, init) => {
      if (url.endsWith("/auth/me")) return { status: 200, body: me({ mfa_enabled: enabled }) };
      if (url.endsWith("/auth/mfa") && (init?.method ?? "GET") === "GET")
        return {
          status: 200,
          body: { enabled, enabled_at: null, required: false, recovery_codes_remaining: enabled ? 10 : 0 },
        };
      if (url.endsWith("/auth/mfa/setup")) {
        expect(body(init)).toEqual({ current_password: "Training-Pass-2026!" });
        return {
          status: 200,
          body: {
            secret: "JBSWY3DPEHPK3PXP",
            otpauth_uri: "otpauth://totp/x",
            qr_svg_base64: btoa("<svg/>"),
          },
        };
      }
      if (url.endsWith("/auth/mfa/enable")) {
        enabled = true;
        return { status: 200, body: { enabled: true, recovery_codes: ["AAAAA-BBBBB", "CCCCC-DDDDD"] } };
      }
      return unauth;
    });
    render(
      <MemoryRouter>
        <AuthProvider>
          <MfaPanel />
        </AuthProvider>
      </MemoryRouter>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Set up authenticator" }));
    await userEvent.type(screen.getByLabelText("Current password"), "Training-Pass-2026!");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    const qr = await screen.findByRole("img", { name: /QR code/ });
    expect(qr.getAttribute("src")).toMatch(/^data:image\/svg\+xml;base64,/);
    expect(screen.getByText("JBSWY3DPEHPK3PXP")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Code from your authenticator app"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Turn on" }));
    const list = await screen.findByRole("list", { name: "Recovery codes" });
    expect(list).toHaveTextContent("AAAAA-BBBBB");
    await userEvent.click(screen.getByRole("button", { name: "I have saved these codes" }));
    await waitFor(() =>
      expect(screen.queryByRole("list", { name: "Recovery codes" })).not.toBeInTheDocument(),
    );
    expect(await screen.findByText("On")).toBeInTheDocument();
  });
});

describe("route guard", () => {
  it("sends a user who must enrol in MFA to the account page", async () => {
    mockFetch((url) =>
      url.endsWith("/auth/me")
        ? {
            status: 200,
            body: me({ role: "administrator", mfa_required: true, mfa_enrollment_required: true }),
          }
        : unauth,
    );
    render(
      <MemoryRouter initialEntries={["/admin/users"]}>
        <AuthProvider>
          <Routes>
            <Route
              path="/admin/users"
              element={
                <RequireAuth roles={["administrator"]}>
                  <p>Users</p>
                </RequireAuth>
              }
            />
            <Route path="/account" element={<p>Account page</p>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByText("Account page")).toBeInTheDocument();
    expect(screen.queryByText("Users")).not.toBeInTheDocument();
  });
});

describe("AAR timeline after retention", () => {
  it("explains that the event log was removed", async () => {
    mockFetch((url) =>
      url.includes("/timeline")
        ? {
            status: 200,
            body: { items: [], total: 0, limit: 50, offset: 0, events_purged_at: "2026-10-01T10:00:00Z" },
          }
        : unauth,
    );
    render(<TimelineSection sessionId="s1" trackIds={[]} allowGroundTruth={false} />);
    expect(await screen.findByText("Event log removed under the data-retention policy")).toBeInTheDocument();
  });
});
