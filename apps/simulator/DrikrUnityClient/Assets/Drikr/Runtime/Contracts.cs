// Data transfer objects for the Drikr session API (docs/architecture/api-contracts.md).
// Field names follow the JSON contract exactly (snake_case). The client never receives
// ground truth during an exercise; it only renders what the server releases.
using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Drikr
{
    public sealed class SimEvent
    {
        [JsonProperty("event_id")] public string EventId;
        [JsonProperty("seq")] public int Seq;
        [JsonProperty("t_ms")] public int TMs;
        [JsonProperty("available_at_ms")] public int AvailableAtMs;
        [JsonProperty("type")] public string Type;
        [JsonProperty("visibility")] public string Visibility;
        [JsonProperty("origin")] public string Origin;
        [JsonProperty("payload")] public JObject Payload;
    }

    public sealed class EnvironmentInfo
    {
        [JsonProperty("terrain")] public string Terrain;
        [JsonProperty("time_of_day")] public string TimeOfDay;
        [JsonProperty("weather")] public string Weather;
        [JsonProperty("visibility_km")] public float VisibilityKm;
    }

    public sealed class Briefing
    {
        [JsonProperty("name")] public string Name;
        [JsonProperty("briefing")] public string Text;
        [JsonProperty("environment")] public EnvironmentInfo Environment;
        [JsonProperty("duration_s")] public int DurationS;
        [JsonProperty("allow_pause")] public bool AllowPause;
        [JsonProperty("synthetic_notice")] public string SyntheticNotice;
    }

    public sealed class ScenarioRef
    {
        [JsonProperty("id")] public string Id;
        [JsonProperty("key")] public string Key;
        [JsonProperty("version")] public int Version;
        [JsonProperty("name")] public string Name;
    }

    public sealed class ResultSummary
    {
        [JsonProperty("status")] public string Status;
        [JsonProperty("overall")] public float? Overall;
        [JsonProperty("passed")] public bool? Passed;
    }

    public sealed class SessionState
    {
        [JsonProperty("id")] public string Id;
        [JsonProperty("status")] public string Status;
        [JsonProperty("mode")] public string Mode;
        [JsonProperty("scenario")] public ScenarioRef Scenario;
        [JsonProperty("difficulty_level")] public int DifficultyLevel;
        [JsonProperty("seed")] public long? Seed; // null while the session is in progress
        [JsonProperty("sim_time_ms")] public int SimTimeMs;
        [JsonProperty("duration_ms")] public int DurationMs;
        [JsonProperty("allow_pause")] public bool AllowPause;
        [JsonProperty("pause_reason")] public string PauseReason;
        [JsonProperty("completion_reason")] public string CompletionReason;
        [JsonProperty("result")] public ResultSummary Result;
        [JsonProperty("briefing")] public Briefing Briefing;
    }

    public sealed class FeedResponse
    {
        [JsonProperty("state")] public SessionState State;
        [JsonProperty("events")] public List<SimEvent> Events = new List<SimEvent>();
    }

    public sealed class ActionResponse
    {
        [JsonProperty("event")] public SimEvent Event;
        [JsonProperty("duplicate")] public bool Duplicate;
        [JsonProperty("confirmations")] public List<SimEvent> Confirmations = new List<SimEvent>();
        [JsonProperty("state")] public SessionState State;
    }

    public sealed class ScenarioSummary
    {
        [JsonProperty("id")] public string Id;
        [JsonProperty("key")] public string Key;
        [JsonProperty("name")] public string Name;
        [JsonProperty("self_guided")] public bool SelfGuided;
    }

    public sealed class AssignmentProgress
    {
        [JsonProperty("state")] public string State;
        [JsonProperty("active_session_id")] public string ActiveSessionId;
        [JsonProperty("attempts_remaining")] public int AttemptsRemaining;
    }

    public sealed class Assignment
    {
        [JsonProperty("id")] public string Id;
        [JsonProperty("title")] public string Title;
        [JsonProperty("scenario")] public ScenarioRef Scenario;
        [JsonProperty("progress")] public AssignmentProgress Progress;
    }

    public sealed class Page<T>
    {
        [JsonProperty("items")] public List<T> Items = new List<T>();
        [JsonProperty("total")] public int Total;
    }

    public sealed class ItemList<T>
    {
        [JsonProperty("items")] public List<T> Items = new List<T>();
    }

    /// <summary>Predefined training actions only (brief §2). Mirrors trainee-action.schema.json.</summary>
    public sealed class TraineeAction
    {
        [JsonProperty("client_action_id")] public string ClientActionId;
        [JsonProperty("kind")] public string Kind;
        [JsonProperty("track_ids")] public List<string> TrackIds;
        [JsonProperty("classification", NullValueHandling = NullValueHandling.Ignore)] public string Classification;
        [JsonProperty("confidence", NullValueHandling = NullValueHandling.Ignore)] public string Confidence;
        [JsonProperty("response", NullValueHandling = NullValueHandling.Ignore)] public string Response;
        [JsonProperty("note", NullValueHandling = NullValueHandling.Ignore)] public string Note;

        public static TraineeAction Classify(IEnumerable<string> tracks, string classification, string confidence) =>
            new TraineeAction
            {
                ClientActionId = System.Guid.NewGuid().ToString(),
                Kind = "classify",
                TrackIds = new List<string>(tracks),
                Classification = classification,
                Confidence = confidence,
            };

        public static TraineeAction Respond(IEnumerable<string> tracks, string response) =>
            new TraineeAction
            {
                ClientActionId = System.Guid.NewGuid().ToString(),
                Kind = "respond",
                TrackIds = new List<string>(tracks),
                Response = response,
            };
    }

    public static class Vocabulary
    {
        public static readonly string[] Classifications =
            { "small_multirotor", "fixed_wing_uas", "coordinated_swarm", "bird_or_clutter", "unknown" };

        public static readonly string[] Confidences = { "low", "medium", "high" };

        public static readonly string[] Responses =
            { "continue_monitoring", "request_sensor_confirmation", "report_to_exercise_control", "log_as_cleared" };

        public static readonly HashSet<string> GroundTruthTypes = new HashSet<string>
            { "entity_spawned", "entity_state", "entity_exited", "track_assigned", "observation_missed" };

        // Same wording as apps/web/src/lib/labels.ts.
        static readonly Dictionary<string, string> Labels = new Dictionary<string, string>
        {
            { "small_multirotor", "Small multirotor" },
            { "fixed_wing_uas", "Fixed-wing UAS" },
            { "coordinated_swarm", "Coordinated swarm" },
            { "bird_or_clutter", "Bird or clutter" },
            { "electro_optical", "Optical" },
            { "rf", "RF" },
        };

        public static string Label(string value)
        {
            if (string.IsNullOrEmpty(value)) return "-";
            if (Labels.TryGetValue(value, out var l)) return l;
            return char.ToUpperInvariant(value[0]) + value.Substring(1).Replace('_', ' ');
        }
    }
}
