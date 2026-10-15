/** Human-readable labels for contract enum values. Keys must match packages/contracts. */

export const CLASSIFICATION_LABELS: Record<string, string> = {
  small_multirotor: "Small multirotor",
  fixed_wing_uas: "Fixed-wing UAS",
  coordinated_swarm: "Coordinated swarm",
  bird_or_clutter: "Bird or clutter",
  unknown: "Unknown",
};

/** Plain-language meaning of each classification, for the guide and the decision panel. */
export const CLASSIFICATION_HELP: Record<string, string> = {
  small_multirotor: "A small drone with rotors, like a quadcopter. Slow, can hover, often low and close.",
  fixed_wing_uas:
    "A drone shaped like a small aircraft. Faster, flies in straight lines or wide loops, cannot hover.",
  coordinated_swarm: "Several drones moving together in a pattern. Their tracks appear and move as a group.",
  bird_or_clutter:
    "Not a drone: a bird, weather or a false radar return. Erratic, short-lived or no RF signal.",
  unknown: "You cannot tell yet. Better than guessing; you can change it later.",
};

export const RESPONSE_LABELS: Record<string, string> = {
  continue_monitoring: "Continue monitoring",
  request_sensor_confirmation: "Request sensor confirmation",
  report_to_exercise_control: "Report to exercise control",
  log_as_cleared: "Log as cleared",
};

export const RESPONSE_HELP: Record<string, string> = {
  continue_monitoring: "Keep the track under observation without further action.",
  request_sensor_confirmation:
    "Ask the simulated optical sensor for a closer look. A result arrives after about 4 seconds.",
  report_to_exercise_control: "Report the track to the virtual exercise control cell.",
  log_as_cleared: "Record the track as cleared (benign or clutter).",
};

export const CONFIDENCE_LABELS: Record<string, string> = { low: "Low", medium: "Medium", high: "High" };

export const SENSOR_LABELS: Record<string, string> = {
  radar: "Radar (simulated)",
  electro_optical: "Optical (simulated)",
  rf: "RF (simulated)",
};

export const STATUS_LABELS: Record<string, string> = {
  created: "Ready to start",
  running: "Running",
  paused: "Paused",
  completed: "Completed",
  aborted: "Aborted",
  not_started: "Not started",
  in_progress: "In progress",
  attempted: "Attempted",
  cancelled: "Cancelled",
  pending: "Pending",
  in_review: "In review",
  reviewed: "Reviewed",
  follow_up: "Follow-up required",
  met: "Met",
  not_met: "Not met",
  not_assessable: "Not assessable",
};

export const DIMENSION_ORDER = [
  "recognition",
  "timing",
  "consistency",
  "uncertainty",
  "objectives",
  "procedure",
] as const;

export const DIMENSION_LABELS: Record<string, string> = {
  recognition: "Recognition accuracy",
  timing: "Decision timing",
  consistency: "Rubric consistency",
  uncertainty: "Handling of uncertainty",
  objectives: "Objective completion",
  procedure: "Procedural compliance",
};

export const DIMENSION_HELP: Record<string, string> = {
  recognition:
    "Share of observed tracks whose final classification matched the simulated ground truth (partial credit per rubric).",
  timing:
    "How quickly each track was first classified after it became visible. Full credit within the rubric target time.",
  consistency: "Whether the final training response for each track matched the rubric decision tree.",
  uncertainty:
    "For tracks classified on weak evidence: credit for low confidence or for requesting confirmation first.",
  objectives: "Share of the exercise learning objectives that were met.",
  procedure:
    "Compliance with procedural rules such as classifying before reporting and confirming before clearing.",
};

export const ENV_LABELS: Record<string, string> = {
  urban: "Urban",
  rural: "Rural",
  coastal: "Coastal",
  industrial: "Industrial",
  day: "Daytime",
  dusk: "Dusk",
  night: "Night",
  clear: "Clear",
  haze: "Haze",
  rain: "Rain",
  fog: "Fog",
};

export const ROLE_LABELS: Record<string, string> = {
  administrator: "Administrator",
  instructor: "Instructor",
  trainee: "Trainee",
};

export function label(map: Record<string, string>, key: string | null | undefined, fallback = "—"): string {
  if (!key) return fallback;
  return map[key] ?? key.replace(/_/g, " ");
}
