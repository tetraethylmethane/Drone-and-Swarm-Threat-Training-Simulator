import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ResultItem, ScoreResult } from "@/lib/types";

import { TimelineSection, TrackDecisionsSection } from "./AarSections";

afterEach(() => vi.unstubAllGlobals());

function event(seq: number) {
  return {
    seq,
    event_id: `evt-${seq}`,
    t_ms: seq * 1000,
    available_at_ms: seq * 1000,
    type: "classification_submitted",
    visibility: "trainee",
    origin: "trainee",
    payload: { track_ids: ["TRK-001"], classification: "small_multirotor", confidence: "low" },
  };
}

function mockTimeline() {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(url);
      // The server answers an around_seq request with the page that holds the event.
      const body = url.includes("around_seq=4101")
        ? { items: [event(4100), event(4101)], total: 300, limit: 100, offset: 200, events_purged_at: null }
        : { items: [event(1), event(2)], total: 300, limit: 100, offset: 0, events_purged_at: null };
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return urls;
}

const item: ResultItem = {
  track_id: "TRK-001",
  entity_id: "e1",
  true_class: "small_multirotor",
  cooperative: false,
  behavior: "hover",
  swarm_member: false,
  closest_range_m: 800,
  beacon_observed: false,
  first_available_s: 10,
  first_classification_s: 14,
  final_classification: "small_multirotor",
  final_confidence: "low",
  final_response: null,
  expected_responses: ["report_to_exercise_control"],
  acceptable_responses: [],
  decision_leaf: "report",
  decision_path: [],
  evidence_at_decision: null,
  decisions: 1,
  evidence_events: [
    {
      seq: 4101,
      event_id: "evt-4101",
      t_s: 14,
      kind: "classification",
      value: "small_multirotor",
      confidence: "low",
    },
  ],
};

describe("AAR evidence links (B-06)", () => {
  it("shows an evidence event when its id is selected", () => {
    const onShowEvent = vi.fn();
    render(
      <TrackDecisionsSection
        result={{ items: [item], dimensions: {} } as unknown as ScoreResult}
        onShowEvent={onShowEvent}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Show event evt-4101 in the event timeline" }));
    expect(onShowEvent).toHaveBeenCalledWith(4101);
  });

  it("opens the page that holds the focused event, highlights it, and pages normally afterwards", async () => {
    const urls = mockTimeline();
    render(
      <TimelineSection sessionId="s1" trackIds={[]} allowGroundTruth={false} focus={{ seq: 4101, n: 1 }} />,
    );
    await waitFor(() => expect(urls.some((u) => u.includes("around_seq=4101"))).toBe(true));
    expect(urls.find((u) => u.includes("around_seq=4101"))).toContain("category=decisions");
    const row = (await screen.findByText(/evt-4101/)).closest("tr")!;
    expect(row).toHaveAttribute("aria-current", "true");
    expect(screen.getByText(/201–300 of 300/)).toBeInTheDocument(); // the server's page, not page 1

    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    await waitFor(() => expect(urls.at(-1)).toContain("offset=100"));
    expect(urls.at(-1)).not.toContain("around_seq");
  });
});
