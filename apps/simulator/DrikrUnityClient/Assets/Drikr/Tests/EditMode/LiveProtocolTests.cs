// Live end-to-end test of the adapter protocol from Unity against a running API.
// Runs only when DRIKR_LIVE_API (e.g. http://localhost:8080/api/v1) and DRIKR_LIVE_PASSWORD are set;
// uses the seeded demo trainee "trainee2".
using System;
using System.Collections;
using System.Linq;
using System.Threading.Tasks;
using NUnit.Framework;
using UnityEngine.TestTools;

namespace Drikr.Tests
{
    public class LiveProtocolTests
    {
        static IEnumerator Await(Task t)
        {
            while (!t.IsCompleted) yield return null;
            if (t.IsFaulted) throw t.Exception!.GetBaseException();
        }

        [UnityTest, Timeout(180000)]
        public IEnumerator FullExerciseOverTheAdapterProtocol()
        {
            var url = Environment.GetEnvironmentVariable("DRIKR_LIVE_API");
            var pw = Environment.GetEnvironmentVariable("DRIKR_LIVE_PASSWORD");
            if (string.IsNullOrEmpty(url) || string.IsNullOrEmpty(pw)) Assert.Ignore("Set DRIKR_LIVE_API and DRIKR_LIVE_PASSWORD to run");
            yield return Await(Run(url, pw));
        }

        static async Task Run(string url, string password)
        {
            using var api = new DrikrApi(url);
            await api.Login("trainee2", password);
            var scenario = (await api.PracticeScenarios()).Items.First(s => s.Key == "demo-perimeter-basics");
            var session = await api.CreatePractice(scenario.Id);
            Assert.AreEqual("created", session.Status);
            Assert.IsNotNull(session.Briefing);
            await api.Transition(session.Id, "start");

            var picture = new TrackPicture();
            var since = 0;
            var deadline = DateTime.UtcNow.AddSeconds(60);
            while (picture.Tracks.Count == 0 && DateTime.UtcNow < deadline)
            {
                await Task.Delay(1000);
                var feed = await api.Feed(session.Id, since);
                Assert.IsFalse(feed.Events.Any(e => e.Visibility == "ground_truth"), "ground truth leaked to the client");
                Assert.IsTrue(feed.Events.Where(e => e.Type == "track_observation").All(e => (bool)e.Payload["synthetic"]));
                picture.Apply(feed.Events);
                since = feed.State.SimTimeMs;
            }
            Assert.Greater(picture.Tracks.Count, 0, "no track observed within 60 s");
            var track = picture.Tracks.Keys.First();

            var action = TraineeAction.Classify(new[] { track }, "small_multirotor", "low");
            var first = await api.Submit(session.Id, action);
            var retry = await api.Submit(session.Id, action); // same client_action_id
            Assert.IsFalse(first.Duplicate);
            Assert.IsTrue(retry.Duplicate);
            Assert.AreEqual(first.Event.EventId, retry.Event.EventId);
            await api.Submit(session.Id, TraineeAction.Respond(new[] { track }, "report_to_exercise_control"));

            var done = await api.Transition(session.Id, "complete");
            Assert.AreEqual("completed", done.Status);
            var result = await api.Result(session.Id);
            Assert.AreEqual("scored", (string)result["status"]);
            await api.Logout();
        }
    }
}
