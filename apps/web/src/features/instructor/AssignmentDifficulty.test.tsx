import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssignmentDifficultyPage } from "./AssignmentDifficulty";

const assignment = {
  id: "a1",
  title: "Perimeter practice",
  instructions: "",
  status: "active",
  scenario: { id: "sc1", key: "demo-perimeter-basics", version: 2, name: "Perimeter basics" },
  trainee: { id: "t1", display_name: "Demo Trainee One" },
  assigned_by: { id: "i1", display_name: "Instructor" },
  trainee_options: {},
  difficulty_mode: "adaptive",
  difficulty_level: 2,
  min_level: 1,
  max_level: 3,
  max_attempts: 5,
  feedback_level: "detailed",
  due_at: null,
  created_at: "2026-10-16T09:00:00Z",
  progress: {
    next_difficulty_level: 3,
    sessions: [],
    attempts_used: 2,
    state: "in_progress",
    best_overall: 88,
  },
};

const adjustments = {
  items: [
    {
      id: "d1",
      trainee_id: "t1",
      assignment_id: "a1",
      scenario_key: "demo-perimeter-basics",
      session_id: "s2",
      from_level: 2,
      to_level: 3,
      change: "increase",
      confidence: "medium",
      reason: "Increasing to level 3: mean 88.0 >= 85 and every recent score >= 75.",
      created_at: "2026-10-16T10:00:00Z",
    },
    { ...{ id: "d0", assignment_id: "other" }, reason: "Another assignment" },
  ],
};

function mockApi() {
  const calls: { url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const body = url.includes("/analytics/difficulty")
        ? adjustments
        : url.endsWith("/difficulty")
          ? { assignment_id: "a1", from_level: 3, to_level: 2, change: "decrease" }
          : assignment;
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return calls;
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/instructor/assignments/a1/difficulty"]}>
      <Routes>
        <Route
          path="/instructor/assignments/:assignmentId/difficulty"
          element={<AssignmentDifficultyPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("AssignmentDifficultyPage", () => {
  it("shows this assignment's adjustments with their reasons", async () => {
    mockApi();
    renderPage();
    expect(await screen.findByText(/Next session: level 3/)).toBeInTheDocument();
    expect(await screen.findByText(/mean 88.0 >= 85/)).toBeInTheDocument();
    expect(screen.queryByText("Another assignment")).not.toBeInTheDocument();
    // At the maximum, only lowering is offered.
    expect(screen.getByRole("button", { name: /Raise to level 4/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Lower to level 2/ })).toBeEnabled();
  });

  it("requires a reason and sends a one-step override", async () => {
    const calls = mockApi();
    renderPage();
    const lower = await screen.findByRole("button", { name: /Lower to level 2/ });
    fireEvent.click(lower);
    expect(await screen.findByText(/Give a reason/)).toBeInTheDocument();
    expect(calls.some((c) => c.url.endsWith("/assignments/a1/difficulty"))).toBe(false);

    fireEvent.change(screen.getByLabelText("Reason for the change"), {
      target: { value: "Struggling with birds" },
    });
    fireEvent.click(lower);
    await waitFor(() =>
      expect(calls.find((c) => c.url.endsWith("/assignments/a1/difficulty"))?.body).toEqual({
        level: 2,
        reason: "Struggling with birds",
      }),
    );
    expect(await screen.findByText(/next session will run at level 2/)).toBeInTheDocument();
  });
});
