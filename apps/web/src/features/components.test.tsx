import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ErrorState } from "@/components/ui/states";
import { ProgressSection } from "@/features/analytics/ProgressCharts";
import { PasswordSchema } from "@/features/auth/AccountPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { DecisionPanel, TrackTable } from "@/features/exercise/panels";
import { applyEvents, emptyPicture, sortedTracks } from "@/features/exercise/trackPicture";
import { ApiError } from "@/lib/api";
import { AuthProvider } from "@/lib/auth";

function mockFetch(handler: (url: string, init?: RequestInit) => { status: number; body: unknown }) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const { status, body } = handler(url, init);
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("LoginPage", () => {
  it("validates required fields before calling the API", async () => {
    const fetch = mockFetch(() => ({
      status: 401,
      body: { error: { code: "unauthorized", message: "Authentication required" } },
    }));
    render(
      <MemoryRouter>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </MemoryRouter>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter your username")).toBeInTheDocument();
    expect(screen.getByText("Enter your password")).toBeInTheDocument();
    expect(fetch.mock.calls.filter(([u]) => String(u).includes("/auth/login"))).toHaveLength(0);
  });

  it("shows the server's generic error on failed sign-in", async () => {
    mockFetch((url) =>
      url.includes("/auth/login")
        ? {
            status: 401,
            body: {
              error: {
                code: "invalid_credentials",
                message: "Invalid username or password, or the account is temporarily locked",
              },
            },
          }
        : { status: 401, body: { error: { code: "unauthorized", message: "Authentication required" } } },
    );
    render(
      <MemoryRouter>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </MemoryRouter>,
    );
    await userEvent.type(await screen.findByLabelText("Username"), "trainee1");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText(/Invalid username or password/)).toBeInTheDocument();
  });
});

describe("password policy", () => {
  it("mirrors the backend policy", () => {
    const base = { current_password: "Old-Password-1", confirm: "" };
    expect(PasswordSchema.safeParse({ ...base, new_password: "short", confirm: "short" }).success).toBe(
      false,
    );
    expect(
      PasswordSchema.safeParse({
        ...base,
        new_password: "alllowercaseletters",
        confirm: "alllowercaseletters",
      }).success,
    ).toBe(false);
    expect(
      PasswordSchema.safeParse({ ...base, new_password: "Good-Password-22", confirm: "Different-22" })
        .success,
    ).toBe(false);
    expect(
      PasswordSchema.safeParse({ ...base, new_password: "Good-Password-22", confirm: "Good-Password-22" })
        .success,
    ).toBe(true);
  });
});

describe("states", () => {
  it("never invents analytics when there is no data", () => {
    render(<ProgressSection points={[]} showTrainee={false} />);
    expect(screen.getByText("No completed sessions match these filters")).toBeInTheDocument();
    expect(screen.getByText(/No sample or estimated data is shown/)).toBeInTheDocument();
  });

  it("error state offers a retry", async () => {
    const retry = vi.fn();
    render(
      <ErrorState
        error={new ApiError(503, "database_unavailable", "The database is temporarily unavailable.")}
        onRetry={retry}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("temporarily unavailable");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledOnce();
  });
});

describe("exercise panels", () => {
  const picture = applyEvents(emptyPicture(), [
    {
      event_id: "G-000001",
      seq: 1,
      t_ms: 1000,
      available_at_ms: 1000,
      type: "track_observation",
      visibility: "trainee",
      origin: "generated",
      payload: { track_id: "TRK-001", sensor: "radar", synthetic: true, quality: 0.8, x_m: 100, y_m: 200 },
    },
    {
      event_id: "G-000002",
      seq: 2,
      t_ms: 1500,
      available_at_ms: 1500,
      type: "track_observation",
      visibility: "trainee",
      origin: "generated",
      payload: {
        track_id: "TRK-002",
        sensor: "rf",
        synthetic: true,
        quality: 0.5,
        bearing_deg: 10,
        beacon: true,
      },
    },
  ]);

  it("track table supports keyboard-accessible multi-selection", async () => {
    const onToggle = vi.fn();
    render(
      <TrackTable
        tracks={sortedTracks(picture)}
        selected={new Set(["TRK-001"])}
        onToggle={onToggle}
        nowMs={3000}
      />,
    );
    expect(screen.getByLabelText("Select TRK-001")).toBeChecked();
    await userEvent.click(screen.getByLabelText("Select TRK-002"));
    expect(onToggle).toHaveBeenCalledWith("TRK-002", true);
    expect(screen.getByText("Observed")).toBeInTheDocument();
  });

  it("decision panel submits only predefined training actions", async () => {
    const onSubmit = vi.fn(async () => ({}));
    render(<DecisionPanel selected={["TRK-001"]} disabled={false} onSubmit={onSubmit} />);
    const submit = screen.getByRole("button", { name: "Submit classification" });
    expect(submit).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Classification"), "bird_or_clutter");
    await userEvent.click(screen.getByLabelText("Low"));
    await userEvent.click(submit);
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({
        kind: "classify",
        track_ids: ["TRK-001"],
        classification: "bird_or_clutter",
        confidence: "low",
        note: undefined,
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: /Report to exercise control/ }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenLastCalledWith({
        kind: "respond",
        track_ids: ["TRK-001"],
        response: "report_to_exercise_control",
        note: undefined,
      }),
    );
    const labels = screen.getAllByRole("button").map((b) => b.textContent ?? "");
    expect(labels.join(" ")).not.toMatch(/engage|intercept|target/i);
  });

  it("decision panel is disabled when nothing is selected", () => {
    render(<DecisionPanel selected={[]} disabled={false} onSubmit={vi.fn()} />);
    expect(screen.getByText(/Select one or more tracks/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Continue monitoring/ })).toBeDisabled();
  });
});
