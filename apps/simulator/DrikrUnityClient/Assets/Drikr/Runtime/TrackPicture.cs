// The trainee's track picture: a pure projection of trainee-visible events.
// Same rules as apps/web/src/features/exercise/trackPicture.ts, so both visual
// clients show the same picture for the same event log.
using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace Drikr
{
    public struct TrackPoint
    {
        public int TMs;
        public float X, Y;
        public float? Alt;
    }

    public sealed class Track
    {
        public string Id;
        public int FirstSeenMs, LastSeenMs;
        public int Observations;
        public readonly HashSet<string> Sensors = new HashSet<string>();
        public TrackPoint? Position;
        public readonly List<TrackPoint> Trail = new List<TrackPoint>();
        public float? Bearing;
        public string ClassHint;
        public float ClassHintQuality;
        public int ClassHintMs = -1;
        public bool Beacon, Lost, PendingConfirmation;
        public string Classification, Confidence, Response;
    }

    public sealed class TrackPicture
    {
        public const int TrailLength = 12;
        readonly HashSet<string> _seen = new HashSet<string>();
        public readonly SortedDictionary<string, Track> Tracks = new SortedDictionary<string, Track>(StringComparer.Ordinal);
        public readonly Dictionary<string, string> SensorStatus = new Dictionary<string, string>();
        public readonly List<string> Messages = new List<string>();
        public float? VisibilityKm;
        public int GroundTruthEventsRejected { get; private set; }

        /// <summary>Apply events in any order; duplicates (same event_id) are ignored.</summary>
        public int Apply(IEnumerable<SimEvent> events)
        {
            var fresh = events.Where(e => e != null && _seen.Add(e.EventId)).OrderBy(e => e.TMs).ThenBy(e => e.Seq).ToList();
            foreach (var e in fresh) ApplyOne(e);
            return fresh.Count;
        }

        Track Get(string id, int tMs)
        {
            if (!Tracks.TryGetValue(id, out var t))
            {
                t = new Track { Id = id, FirstSeenMs = tMs, LastSeenMs = tMs };
                Tracks[id] = t;
            }
            return t;
        }

        static float? F(JObject p, string k) => p[k] == null || p[k].Type == JTokenType.Null ? (float?)null : p[k].Value<float>();

        void ApplyOne(SimEvent e)
        {
            var p = e.Payload ?? new JObject();
            if (Vocabulary.GroundTruthTypes.Contains(e.Type) || e.Visibility == "ground_truth")
            {
                GroundTruthEventsRejected++; // defensive: the server never sends these during an exercise
                return;
            }
            switch (e.Type)
            {
                case "track_observation":
                {
                    var t = Get((string)p["track_id"], e.TMs);
                    t.Observations++;
                    t.Sensors.Add((string)p["sensor"]);
                    t.FirstSeenMs = Math.Min(t.FirstSeenMs, e.TMs);
                    if (e.TMs >= t.LastSeenMs) { t.LastSeenMs = e.TMs; t.Lost = false; }
                    var x = F(p, "x_m");
                    var y = F(p, "y_m");
                    if (x.HasValue && y.HasValue)
                    {
                        var pt = new TrackPoint { TMs = e.TMs, X = x.Value, Y = y.Value, Alt = F(p, "alt_m") ?? t.Position?.Alt };
                        if (!t.Position.HasValue || e.TMs >= t.Position.Value.TMs) t.Position = pt;
                        t.Trail.Add(pt);
                        t.Trail.Sort((a, b) => a.TMs.CompareTo(b.TMs));
                        if (t.Trail.Count > TrailLength) t.Trail.RemoveRange(0, t.Trail.Count - TrailLength);
                    }
                    var bearing = F(p, "bearing_deg");
                    if (bearing.HasValue) t.Bearing = bearing;
                    if (p["beacon"]?.Type == JTokenType.Boolean && (bool)p["beacon"]) t.Beacon = true;
                    var hint = p["class_hint"]?.Type == JTokenType.String ? (string)p["class_hint"] : null;
                    if (hint != null && e.TMs >= t.ClassHintMs)
                    {
                        t.ClassHint = hint;
                        t.ClassHintQuality = F(p, "quality") ?? 0f;
                        t.ClassHintMs = e.TMs;
                    }
                    break;
                }
                case "sensor_confirmation":
                    if (Tracks.TryGetValue((string)p["track_id"], out var ct))
                    {
                        ct.PendingConfirmation = false;
                        if ((string)p["outcome"] == "hint_available")
                        {
                            ct.ClassHint = (string)p["class_hint"];
                            ct.ClassHintQuality = F(p, "quality") ?? 0f;
                            ct.ClassHintMs = e.TMs;
                        }
                    }
                    break;
                case "track_lost":
                    if (Tracks.TryGetValue((string)p["track_id"], out var lt) && e.TMs >= lt.LastSeenMs) lt.Lost = true;
                    break;
                case "sensor_status":
                    SensorStatus[(string)p["sensor"]] = (string)p["status"];
                    break;
                case "environment_update":
                    VisibilityKm = F(p, "visibility_km");
                    break;
                case "exercise_message":
                    Messages.Add((string)p["message"]);
                    break;
                case "classification_submitted":
                    foreach (var id in p["track_ids"].Values<string>())
                        if (Tracks.TryGetValue(id, out var c)) { c.Classification = (string)p["classification"]; c.Confidence = (string)p["confidence"]; }
                    break;
                case "response_submitted":
                    foreach (var id in p["track_ids"].Values<string>())
                        if (Tracks.TryGetValue(id, out var r))
                        {
                            r.Response = (string)p["response"];
                            if (r.Response == "request_sensor_confirmation") r.PendingConfirmation = true;
                        }
                    break;
            }
        }
    }

    /// <summary>Maps contract coordinates (metres, site at origin, +y north, alt up) to Unity world space.</summary>
    public static class WorldMapping
    {
        public const float Scale = 0.1f; // world units per metre
        public const float AreaRadiusM = 4000f;

        public static UnityEngine.Vector3 ToWorld(float xM, float yM, float? altM) =>
            new UnityEngine.Vector3(xM * Scale, Math.Max(2f, (altM ?? 50f) * Scale), yM * Scale);
    }
}
