using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using NUnit.Framework;

namespace Drikr.Tests
{
    public class TrackPictureTests
    {
        static int _seq;

        static SimEvent Ev(string type, int t, object payload, string visibility = "trainee") => new SimEvent
        {
            EventId = $"G-{++_seq:000000}",
            Seq = _seq,
            TMs = t,
            AvailableAtMs = t,
            Type = type,
            Visibility = visibility,
            Origin = "generated",
            Payload = JObject.FromObject(payload),
        };

        [Test]
        public void ObservationsBuildTracksRegardlessOfOrder()
        {
            var events = new List<SimEvent>
            {
                Ev("track_observation", 4000, new { track_id = "TRK-001", sensor = "radar", synthetic = true, quality = 0.8, x_m = 20.0, y_m = 10.0, alt_m = 50.0 }),
                Ev("track_observation", 2000, new { track_id = "TRK-001", sensor = "radar", synthetic = true, quality = 0.7, x_m = 10.0, y_m = 5.0, alt_m = 50.0 }),
                Ev("track_observation", 3000, new { track_id = "TRK-001", sensor = "electro_optical", synthetic = true, quality = 0.6, x_m = 12.0, y_m = 6.0, class_hint = "bird_or_clutter" }),
            };
            foreach (var order in new[] { events, Enumerable.Reverse(events).ToList() })
            {
                var pic = new TrackPicture();
                pic.Apply(order);
                var t = pic.Tracks["TRK-001"];
                Assert.AreEqual(20f, t.Position.Value.X, 1e-4);
                Assert.AreEqual(2000, t.FirstSeenMs);
                Assert.AreEqual(3, t.Observations);
                Assert.AreEqual("bird_or_clutter", t.ClassHint);
                CollectionAssert.AreEqual(new[] { 2000, 3000, 4000 }, t.Trail.Select(p => p.TMs).ToArray());
            }
        }

        [Test]
        public void DuplicatesAreIgnored()
        {
            var e = Ev("track_observation", 1000, new { track_id = "TRK-002", sensor = "radar", synthetic = true, quality = 0.5, x_m = 0.0, y_m = 0.0 });
            var pic = new TrackPicture();
            Assert.AreEqual(1, pic.Apply(new[] { e }));
            Assert.AreEqual(0, pic.Apply(new[] { e, e }));
            Assert.AreEqual(1, pic.Tracks["TRK-002"].Observations);
        }

        [Test]
        public void LostAndRecovered()
        {
            var pic = new TrackPicture();
            pic.Apply(new[]
            {
                Ev("track_observation", 1000, new { track_id = "TRK-003", sensor = "radar", synthetic = true, quality = 0.5, x_m = 0.0, y_m = 0.0 }),
                Ev("track_lost", 9000, new { track_id = "TRK-003" }),
            });
            Assert.IsTrue(pic.Tracks["TRK-003"].Lost);
            pic.Apply(new[] { Ev("track_observation", 12000, new { track_id = "TRK-003", sensor = "radar", synthetic = true, quality = 0.5, x_m = 1.0, y_m = 1.0 }) });
            Assert.IsFalse(pic.Tracks["TRK-003"].Lost);
        }

        [Test]
        public void DecisionsAndConfirmations()
        {
            var pic = new TrackPicture();
            pic.Apply(new[]
            {
                Ev("track_observation", 1000, new { track_id = "TRK-004", sensor = "rf", synthetic = true, quality = 0.5, bearing_deg = 45.0, beacon = true }),
                Ev("classification_submitted", 2000, new { track_ids = new[] { "TRK-004" }, classification = "small_multirotor", confidence = "low", client_action_id = "a" }),
                Ev("response_submitted", 2500, new { track_ids = new[] { "TRK-004" }, response = "request_sensor_confirmation", client_action_id = "b" }),
            });
            var t = pic.Tracks["TRK-004"];
            Assert.IsTrue(t.Beacon);
            Assert.IsFalse(t.Position.HasValue); // RF gives bearing only
            Assert.AreEqual("small_multirotor", t.Classification);
            Assert.IsTrue(t.PendingConfirmation);
            pic.Apply(new[] { Ev("sensor_confirmation", 6500, new { track_id = "TRK-004", outcome = "hint_available", class_hint = "small_multirotor", quality = 0.9, synthetic = true }) });
            Assert.IsFalse(t.PendingConfirmation);
            Assert.AreEqual(0.9f, t.ClassHintQuality, 1e-4);
        }

        [Test]
        public void GroundTruthIsNeverRendered()
        {
            var pic = new TrackPicture();
            pic.Apply(new[]
            {
                Ev("entity_spawned", 0, new { entity_id = "x", entity_class = "small_multirotor" }, "ground_truth"),
                Ev("track_assigned", 0, new { track_id = "TRK-009", entity_id = "x" }, "ground_truth"),
            });
            Assert.AreEqual(0, pic.Tracks.Count);
            Assert.AreEqual(2, pic.GroundTruthEventsRejected);
        }

        [Test]
        public void WorldMappingUsesNorthAsPositiveZ()
        {
            var v = WorldMapping.ToWorld(1000f, 2000f, 100f);
            Assert.AreEqual(100f, v.x, 1e-4);
            Assert.AreEqual(10f, v.y, 1e-4);
            Assert.AreEqual(200f, v.z, 1e-4);
            Assert.AreEqual(2f, WorldMapping.ToWorld(0, 0, 0).y, 1e-4); // markers never sink into the ground
        }

        [Test]
        public void ApiUrlResolution()
        {
            Assert.AreEqual("http://a/api/v1", DrikrClientApp.ResolveApiUrl(new[] { "x.exe", "-drikrApi", "http://a/api/v1" }, "http://b", "http://c"));
            Assert.AreEqual("http://b", DrikrClientApp.ResolveApiUrl(new[] { "x.exe" }, "http://b", "http://c"));
            Assert.AreEqual("http://c", DrikrClientApp.ResolveApiUrl(new string[0], null, "http://c"));
        }
    }

    /// <summary>The C# contract must agree with the exported JSON Schemas (packages/contracts/schemas).</summary>
    public class ContractTests
    {
        static readonly string SchemaDir = Path.GetFullPath(Path.Combine(UnityEngine.Application.dataPath, "../../../../packages/contracts/schemas"));

        static string[] EnumOf(string file, string name)
        {
            var schema = JObject.Parse(File.ReadAllText(Path.Combine(SchemaDir, file)));
            return schema["$defs"][name]["enum"].Values<string>().OrderBy(x => x).ToArray();
        }

        [Test]
        public void VocabularyMatchesSchema()
        {
            CollectionAssert.AreEqual(EnumOf("trainee-action.schema.json", "TrackClassification"), Vocabulary.Classifications.OrderBy(x => x).ToArray());
            CollectionAssert.AreEqual(EnumOf("trainee-action.schema.json", "Confidence"), Vocabulary.Confidences.OrderBy(x => x).ToArray());
            CollectionAssert.AreEqual(EnumOf("trainee-action.schema.json", "TrainingResponse"), Vocabulary.Responses.OrderBy(x => x).ToArray());
        }

        [Test]
        public void ActionSerialisesWithSchemaFieldNames()
        {
            var schema = JObject.Parse(File.ReadAllText(Path.Combine(SchemaDir, "trainee-action.schema.json")));
            var allowed = ((JObject)schema["properties"]).Properties().Select(p => p.Name).ToHashSet();
            var required = schema["required"].Values<string>();
            var json = JObject.Parse(JsonConvert.SerializeObject(TraineeAction.Classify(new[] { "TRK-001" }, "unknown", "low")));
            CollectionAssert.IsSubsetOf(json.Properties().Select(p => p.Name).ToArray(), allowed.ToArray());
            CollectionAssert.IsSubsetOf(required.ToArray(), json.Properties().Select(p => p.Name).ToArray());
            var respond = JObject.Parse(JsonConvert.SerializeObject(TraineeAction.Respond(new[] { "TRK-001" }, "log_as_cleared")));
            Assert.IsNull(respond["classification"]);
            Assert.AreEqual("respond", (string)respond["kind"]);
        }
    }
}
