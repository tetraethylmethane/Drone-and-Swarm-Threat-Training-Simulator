/** Response types mirroring apps/api/drikr_api/serializers.py. */

export type Role = "administrator" | "instructor" | "trainee";

export interface Me {
  id: string;
  username: string;
  display_name: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
  locked: boolean;
  mfa_enabled: boolean;
  deactivated_at: string | null;
  anonymised_at: string | null;
  unit?: string | null;
  permissions: string[];
  /** The role requires multi-factor authentication (administrator setting). */
  mfa_required: boolean;
  /** Required but not yet set up: the API refuses everything except account endpoints. */
  mfa_enrollment_required: boolean;
}

export interface UserOut extends Omit<Me, "permissions" | "mfa_required" | "mfa_enrollment_required"> {
  created_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Environment {
  terrain: string;
  time_of_day: "day" | "dusk" | "night";
  weather: "clear" | "haze" | "rain" | "fog";
  visibility_km: number;
  wind_mps: number;
}

export interface Briefing {
  name: string;
  description: string;
  briefing: string;
  learning_objectives: { id: string; description: string }[];
  environment: Environment;
  sensors: Record<string, { enabled: boolean; range_m: number; update_interval_s: number }>;
  duration_s: number;
  allow_pause: boolean;
  synthetic_notice: string;
}

export interface ScenarioSummary {
  id: string;
  key: string;
  version: number;
  name: string;
  description: string;
  status: "published" | "archived";
  is_demo: boolean;
  self_guided: boolean;
  environment: Environment;
  duration_s: number;
  difficulty: { level: number; adaptive_allowed: boolean; min_level: number; max_level: number };
  objective_count: number;
  entity_group_count: number;
  rubric: { id: string; key: string; version: number };
  digest: string;
  created_at: string;
  version_count?: number;
  briefing?: Briefing;
}

export interface ScenarioDetail extends ScenarioSummary {
  definition: Record<string, unknown>;
  versions: { id: string; version: number; status: string; created_at: string }[];
}

export interface ValidationIssue {
  path: string;
  code: string;
  message: string;
  severity: "error" | "warning";
}

export interface ValidationReport {
  valid: boolean;
  issues: ValidationIssue[];
  preview: {
    seed: number;
    difficulty_level: number;
    duration_ms: number;
    digest: string;
    engine_version: string;
    stats: {
      entities: number;
      entities_by_class: Record<string, number>;
      tracks: number;
      tracks_by_class: Record<string, number>;
      observations: number;
      events: number;
    };
  } | null;
}

export interface RubricSummary {
  id: string;
  key: string;
  version: number;
  name: string;
  description: string;
  weights: Record<string, number>;
  pass_mark: number;
  digest: string;
  is_demo: boolean;
  created_at: string;
  definition?: Record<string, unknown>;
  versions?: { id: string; version: number; created_at: string }[];
}

export interface UserRef {
  id: string;
  username: string;
  display_name: string;
}

export interface TraineeOptions {
  time_of_day: string[];
  weather: string[];
  allow_custom_seed: boolean;
}

export interface AssignmentProgress {
  state: "not_started" | "in_progress" | "attempted" | "completed" | "cancelled";
  attempts_used: number;
  attempts_remaining: number;
  best_overall: number | null;
  active_session_id: string | null;
  next_difficulty_level: number;
  sessions: {
    id: string;
    attempt_number: number;
    status: string;
    difficulty_level: number;
    overall: number | null;
    passed: boolean | null;
    completed_at: string | null;
  }[];
}

export interface Assignment {
  id: string;
  title: string;
  instructions: string;
  status: "active" | "cancelled";
  scenario: { id: string; key: string; version: number; name: string };
  trainee: UserRef;
  assigned_by: UserRef;
  trainee_options: TraineeOptions;
  difficulty_mode: "fixed" | "adaptive";
  difficulty_level: number;
  min_level: number;
  max_level: number;
  max_attempts: number;
  feedback_level: "summary" | "detailed";
  due_at: string | null;
  created_at: string;
  progress?: AssignmentProgress;
  briefing?: Briefing;
}

export type SessionStatus = "created" | "running" | "paused" | "completed" | "aborted";

export interface SessionState {
  id: string;
  status: SessionStatus;
  mode: "assigned" | "self_guided";
  attempt_number: number;
  trainee: UserRef;
  scenario: { id: string; key: string; version: number; name: string };
  rubric: { id: string; key: string; version: number };
  assignment_id: string | null;
  seed: number;
  difficulty_level: number;
  selection: Record<string, unknown>;
  sim_time_ms: number;
  duration_ms: number;
  remaining_ms: number;
  allow_pause: boolean;
  pause_reason: string | null;
  pause_count: number;
  completion_reason: string | null;
  engine_version: string;
  timeline_digest: string;
  config_digest: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  result: {
    status: string;
    overall: number | null;
    passed: boolean | null;
    rubric_version: number;
    scoring_engine_version: string;
  } | null;
  briefing?: Briefing;
}

export interface SimEvent {
  event_id: string;
  seq: number;
  t_ms: number;
  available_at_ms: number;
  type: string;
  visibility: "trainee" | "ground_truth" | "system";
  origin: "generated" | "trainee" | "system";
  payload: Record<string, unknown>;
}

export interface FeedResponse {
  state: SessionState;
  events: SimEvent[];
}

export interface DimensionResult {
  label: string;
  applicable: boolean;
  score: number | null;
  weight: number;
  effective_weight: number;
  contribution: number;
  summary: string;
  items?: { track_id: string | null; credit: number; reason: string; rule?: string; objective_id?: string }[];
}

export interface ResultItem {
  track_id: string;
  entity_id: string;
  true_class: string;
  cooperative: boolean;
  behavior: string;
  swarm_member: boolean;
  closest_range_m: number | null;
  beacon_observed: boolean;
  first_available_s: number | null;
  first_classification_s: number | null;
  final_classification: string | null;
  final_confidence: string | null;
  final_response: string | null;
  expected_responses: string[];
  acceptable_responses: string[];
  decision_leaf: string;
  decision_path: {
    node: string;
    fact?: string;
    op?: string;
    value?: unknown;
    actual?: unknown;
    result?: boolean;
    leaf?: boolean;
  }[];
  evidence_at_decision: number | null;
  decisions: number;
  /** Recorded events behind this item (scoring-1.2.0 and later; absent in older results). */
  evidence_events?: {
    seq: number;
    event_id: string;
    t_s: number | null;
    kind: "classification" | "response" | "sensor_confirmation";
    value: string | null;
    confidence: string | null;
  }[];
}

export interface ScoreResult {
  status: "scored" | "insufficient_data";
  overall: number | null;
  passed: boolean | null;
  pass_mark: number;
  scoring_engine_version: string;
  rubric: { key: string; version: number; digest: string };
  explanation: string;
  dimensions: Record<string, DimensionResult>;
  objectives: {
    id: string;
    description: string;
    kind: string;
    status: "met" | "not_met" | "not_assessable";
    detail: string;
  }[];
  feedback: { strengths: string[]; improvements: string[] };
  counts: { observable_tracks: number; classified_tracks: number; ignored_decisions: number };
  feedback_level: "summary" | "detailed";
  items?: ResultItem[];
  errors?: Record<string, Record<string, unknown>[]>;
  error_counts?: Record<string, number>;
  procedure?: {
    rule: string;
    description: string;
    opportunities: number;
    violations: { track_id: string; t_s: number; detail: string }[];
  }[];
  input_digest?: string;
  end_ms?: number;
  weights?: Record<string, number>;
}

export interface Review {
  session_id: string;
  reviewer: UserRef;
  status: "pending" | "in_review" | "reviewed" | "follow_up";
  notes?: string;
  strengths: string;
  improvements: string;
  focus_objectives: string[];
  shared_with_trainee: boolean;
  updated_at: string;
}

export interface ProgressPoint {
  session_id: string;
  trainee: { id: string; display_name: string };
  scenario_key: string;
  scenario_version: number;
  scenario_name: string;
  mode: string;
  difficulty_level: number;
  completed_at: string;
  overall: number;
  passed: boolean;
  rubric_version: number;
  dimensions: Record<string, number | null>;
  objective_status: string | null;
}

export interface DifficultyAdjustment {
  id: string;
  trainee_id: string;
  assignment_id: string | null;
  scenario_key: string;
  session_id: string | null;
  from_level: number;
  to_level: number;
  change: "increase" | "decrease" | "hold";
  confidence: "low" | "medium" | "high";
  reason: string;
  created_at: string;
}
