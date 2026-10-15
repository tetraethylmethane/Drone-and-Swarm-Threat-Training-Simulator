/** What a trainee should do next during an exercise, worked out from the live state. */

export interface StepTrack {
  id: string;
  lost: boolean;
  classification: { value: string } | null;
  response: { value: string } | null;
}

export interface NextStep {
  /** Short instruction shown in bold. */
  title: string;
  /** One sentence of detail. */
  detail: string;
  /** Number shown in the step badge (1–5), or null when there is nothing specific to do. */
  step: number | null;
}

export function nextStep(status: string, tracks: StepTrack[], selected: ReadonlySet<string>): NextStep {
  if (status === "created")
    return {
      step: 1,
      title: "Press Start exercise when you are ready",
      detail: "Read the briefing below first. The clock starts when you press Start.",
    };
  if (status === "paused")
    return { step: null, title: "The exercise is paused", detail: "Press Resume to continue." };
  if (status !== "running")
    return {
      step: null,
      title: "The exercise has ended",
      detail: "Open the result to see your score and feedback.",
    };

  if (tracks.length === 0)
    return {
      step: 2,
      title: "Watch for tracks",
      detail:
        "Dots will appear in the sensor picture and rows in the Tracks table. This can take a few seconds.",
    };

  const chosen = tracks.filter((t) => selected.has(t.id));
  if (chosen.length === 0) {
    // Prefer a track that is still being observed.
    const incomplete = tracks.filter((t) => !t.classification || !t.response);
    const todo = incomplete.find((t) => !t.lost) ?? incomplete[0];
    if (!todo)
      return {
        step: null,
        title: "All tracks handled",
        detail: "Keep watching for new tracks, or press Finish exercise when you are done.",
      };
    return {
      step: 2,
      title: `Select a track: tick ${todo.id} in the Tracks table`,
      detail: "You can also click its dot in the picture. Shift-click selects several.",
    };
  }
  const label = chosen.length === 1 && chosen[0] ? chosen[0].id : `${chosen.length} tracks`;
  if (chosen.some((t) => !t.classification))
    return {
      step: 3,
      title: `Classify ${label}: what is it?`,
      detail: "In Decision, choose a classification and how sure you are, then press Submit classification.",
    };
  if (chosen.some((t) => !t.response))
    return {
      step: 4,
      title: `Choose a training response for ${label}`,
      detail: "Pick what to do: keep watching, ask for confirmation, report it, or log it as cleared.",
    };
  return {
    step: 5,
    title: `${label} done. Pick the next track`,
    detail: "Untick it, then select another track. You can change a decision at any time before finishing.",
  };
}
