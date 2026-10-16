import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ComparePage } from "@/features/aar/ComparePage";

import { CompetencyPanel } from "./Competency";
import { UnitsPanel } from "./Units";

function mockFetch(byPath: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const key = Object.keys(byPath).find((k) => url.includes(k));
      return new Response(JSON.stringify(key ? byPath[key] : {}), {
        status: key ? 200 : 404,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

const meta = (id: string, overall: number) => ({
  session_id: id,
  completed_at: "2026-10-16T10:00:00Z",
  scenario_key: "demo-perimeter-basics",
  scenario_version: 1,
  difficulty_level: 2,
  seed: 1001,
  overall,
  rubric_version: "standard-assessment v1",
  scoring_engine_version: "scoring-1.2.0",
});

const dim = (trend: string, change: number | null) => ({
  assessed_sessions: 3,
  early_mean: 40,
  recent_mean: change === null ? null : 40 + change,
  change,
  trend,
});

describe("CompetencyPanel", () => {
  it("shows trends, recurring errors and identical-exercise comparisons", async () => {
    mockFetch({
      "/analytics/competency": {
        trainee: { id: "t1", display_name: "Demo Trainee One" },
        sessions: [meta("s1", 30), meta("s2", 50), meta("s3", 70)],
        dimensions: {
          recognition: dim("improving", 30),
          timing: dim("steady", 2),
          consistency: dim("declining", -8),
          uncertainty: dim("insufficient_data", null),
          objectives: dim("steady", 0),
          procedure: dim("steady", 0),
        },
        recurring_errors: [
          {
            type: "missed_tracks",
            label: "Tracks never classified",
            sessions_with_error: 2,
            sessions_considered: 3,
            in_recent_sessions: 2,
            recent_window: 3,
            recurring: true,
            latest: { session_id: "s2" },
          },
          {
            type: "overconfident",
            label: "High confidence on weak evidence",
            sessions_with_error: 0,
            sessions_considered: 3,
            in_recent_sessions: 0,
            recent_window: 3,
            recurring: false,
            latest: null,
          },
        ],
        equivalent_attempts: [
          {
            timeline_digest: "d",
            scenario_key: "demo-perimeter-basics",
            seed: 1001,
            difficulty_level: 2,
            attempts: [meta("s1", 30), meta("s3", 70)],
          },
        ],
        method: { description: "Change compares the first 3 and last 3 assessed sessions." },
      },
    });
    render(
      <MemoryRouter>
        <CompetencyPanel traineeId="t1" />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Improving")).toBeInTheDocument();
    expect(screen.getByText("Declining")).toBeInTheDocument();
    expect(screen.getByText("+30.0")).toBeInTheDocument();
    expect(screen.getByText("Recurring")).toBeInTheDocument();
    expect(screen.queryByText("High confidence on weak evidence")).not.toBeInTheDocument(); // never occurred
    expect(screen.getByRole("link", { name: "Latest occurrence" })).toHaveAttribute(
      "href",
      "/sessions/s2/result",
    );
    expect(screen.getByRole("link", { name: "Compare first and latest" })).toHaveAttribute(
      "href",
      "/sessions/compare?a=s1&b=s3",
    );
  });
});

describe("ComparePage", () => {
  it("states comparability and shows tracks only for identical exercises", async () => {
    mockFetch({
      "/analytics/compare": {
        a: meta("s1", 30),
        b: meta("s3", 70),
        same: { timeline: true },
        comparability: "identical",
        note: "Same exercise (identical timeline) scored with the same rubric: differences come from the decisions.",
        overall: { a: 30, b: 70, delta: 40 },
        dimensions: { recognition: { a: 0, b: 100, delta: 100 } },
        objectives: [{ id: "o1", description: "Classify all tracks", a: "not_met", b: "met" }],
        errors: { missed_tracks: { label: "Tracks never classified", a: 4, b: 0 } },
        tracks: [
          {
            track_id: "TRK-001",
            true_class: "small_multirotor",
            a: { final_classification: null, final_confidence: null, final_response: null },
            b: { final_classification: "small_multirotor", final_confidence: "low", final_response: null },
          },
        ],
      },
    });
    render(
      <MemoryRouter initialEntries={["/sessions/compare?a=s1&b=s3"]}>
        <ComparePage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Identical exercise")).toBeInTheDocument();
    expect(screen.getByText("+40.0")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Track by track" })).toBeInTheDocument();
    expect(screen.getByText("No decision")).toBeInTheDocument();
  });
});

describe("UnitsPanel", () => {
  it("lists units including trainees without one", async () => {
    mockFetch({
      "/analytics/units": {
        units: [
          {
            unit: "Alpha",
            trainees: 2,
            trainees_with_sessions: 1,
            sessions: 3,
            mean_overall: 61.2,
            pass_rate: 33.3,
            dimensions: {},
          },
          {
            unit: null,
            trainees: 1,
            trainees_with_sessions: 0,
            sessions: 0,
            mean_overall: null,
            pass_rate: null,
            dimensions: {},
          },
        ],
        note: "Means over completed, scored sessions.",
      },
    });
    render(<UnitsPanel query="" />);
    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("No unit")).toBeInTheDocument();
    expect(screen.getByText("1 of 2 active")).toBeInTheDocument();
  });
});
