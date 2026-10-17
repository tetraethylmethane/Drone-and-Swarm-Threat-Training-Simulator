import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SessionsPage } from "./OverviewPages";

function session(id: string, overall: number | null) {
  return {
    id,
    status: overall === null ? "running" : "completed",
    mode: "assigned",
    attempt_number: 1,
    created_at: "2026-10-16T09:00:00Z",
    trainee: { id: "t1", display_name: `Trainee ${id}` },
    scenario: { id: "sc1", key: "demo-perimeter-basics", version: 2, name: "Perimeter basics" },
    result: overall === null ? null : { overall },
  };
}

function mockApi() {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(url);
      const body = url.includes("/analytics/filters")
        ? { scenarios: [], objectives: [], trainees: [] }
        : url.includes("sort=score_asc")
          ? { items: [session("low", 41.5), session("high", 92), session("open", null)], total: 3 }
          : { items: [session("open", null), session("high", 92), session("low", 41.5)], total: 3 };
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return urls;
}

afterEach(() => vi.unstubAllGlobals());

describe("Sessions and reviews: sort by score (B-07)", () => {
  it("asks the server to sort before paging and shows its order", async () => {
    const urls = mockApi();
    render(
      <MemoryRouter>
        <SessionsPage />
      </MemoryRouter>,
    );
    await screen.findByText("Trainee open");
    expect(urls.some((u) => u.includes("/sessions?") && u.includes("sort=newest"))).toBe(true);

    fireEvent.change(screen.getByLabelText("Sort"), { target: { value: "score_asc" } });
    await waitFor(() =>
      expect(urls.some((u) => u.includes("sort=score_asc") && u.includes("offset=0"))).toBe(true),
    );
    await waitFor(() => {
      const names = screen.getAllByText(/^Trainee /).map((n) => n.textContent);
      expect(names).toEqual(["Trainee low", "Trainee high", "Trainee open"]);
    });
  });
});
