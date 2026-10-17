import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AdversaryPlan } from "@/lib/types";

import { AdversaryPlanPanel } from "./AarSections";

const base: AdversaryPlan = {
  engine: "adversary-1.0.0",
  method: "Rules-based tactics chosen by recorded weaknesses; no machine learning.",
  summary: "",
  sessions_considered: 3,
  tactics: [],
};

describe("Adaptive adversary in the AAR", () => {
  it("explains each tactic with its evidence and the ranges it narrowed", () => {
    render(
      <AdversaryPlanPanel
        plan={{
          ...base,
          tactics: [
            {
              tactic: "low_and_slow",
              effect: "Drones fly in the lower half of their altitude and speed ranges, to look like birds",
              reason: "5 of 6 single drones were classified as birds or clutter",
              evidence: 6,
              changes: [{ group: "intruder", field: "altitude_m", from: [50, 80], to: [50, 65] }],
            },
          ],
        }}
      />,
    );
    expect(screen.getByText(/from 3 earlier scored session/)).toHaveTextContent("no machine learning");
    expect(screen.getByText(/to look like birds/)).toBeInTheDocument();
    expect(
      screen.getByText("Because 5 of 6 single drones were classified as birds or clutter."),
    ).toBeInTheDocument();
    expect(screen.getByText("intruder: altitude (m) 50–80 → 50–65")).toBeInTheDocument();
  });

  it("says why nothing was adapted", () => {
    render(
      <AdversaryPlanPanel plan={{ ...base, summary: "No adaptation: no weakness had enough evidence." }} />,
    );
    expect(screen.getByText("No adaptation: no weakness had enough evidence.")).toBeInTheDocument();
  });
});
