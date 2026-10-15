import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { FirstVisitGuide, HowToPlayContent } from "./HowToPlay";
import { nextStep, type StepTrack } from "./nextStep";

function track(id: string, over: Partial<StepTrack> = {}): StepTrack {
  return { id, lost: false, classification: null, response: null, ...over };
}

const none = new Set<string>();

describe("nextStep", () => {
  it("walks a trainee through one track", () => {
    expect(nextStep("created", [], none).title).toMatch(/Start exercise/);
    expect(nextStep("running", [], none).title).toBe("Watch for tracks");
    const first = track("TRK-001");
    const t = [first];
    expect(nextStep("running", t, none).title).toBe("Select a track: tick TRK-001 in the Tracks table");
    const sel = new Set(["TRK-001"]);
    expect(nextStep("running", t, sel).title).toBe("Classify TRK-001: what is it?");
    first.classification = { value: "small_multirotor" };
    expect(nextStep("running", t, sel).title).toBe("Choose a training response for TRK-001");
    first.response = { value: "report_to_exercise_control" };
    expect(nextStep("running", t, sel).step).toBe(5);
    expect(nextStep("running", t, none).title).toBe("All tracks handled");
  });

  it("points to a visible unhandled track before a lost one", () => {
    const t = [track("TRK-001", { lost: true }), track("TRK-002")];
    expect(nextStep("running", t, none).title).toContain("TRK-002");
  });

  it("covers several selected tracks and other states", () => {
    const t = [track("TRK-001", { classification: { value: "unknown" } }), track("TRK-002")];
    expect(nextStep("running", t, new Set(["TRK-001", "TRK-002"])).title).toBe(
      "Classify 2 tracks: what is it?",
    );
    expect(nextStep("paused", t, none).title).toBe("The exercise is paused");
    expect(nextStep("completed", t, none).step).toBeNull();
  });
});

describe("guide", () => {
  beforeEach(() => window.localStorage.clear());

  it("shows the welcome once", async () => {
    const { unmount } = render(
      <MemoryRouter>
        <FirstVisitGuide />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("dialog", { name: "Welcome to the training simulator" }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Got it" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    unmount();
    render(
      <MemoryRouter>
        <FirstVisitGuide />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("explains every classification and response in plain words", () => {
    render(
      <MemoryRouter>
        <HowToPlayContent />
      </MemoryRouter>,
    );
    for (const name of [
      "Small multirotor",
      "Fixed-wing UAS",
      "Coordinated swarm",
      "Bird or clutter",
      "Unknown",
    ])
      expect(screen.getByRole("cell", { name })).toBeInTheDocument();
    for (const name of [
      "Continue monitoring",
      "Request sensor confirmation",
      "Report to exercise control",
      "Log as cleared",
    ])
      expect(screen.getByRole("cell", { name })).toBeInTheDocument();
    expect(screen.getByText(/A small drone with rotors/)).toBeInTheDocument();
  });
});
