// VR presentation logic, testable without a headset (VrControls). The XR path itself (OpenXR,
// head and controller poses) needs hardware and is not covered here.
using NUnit.Framework;

namespace Drikr.Tests
{
    public class VrControlsTests
    {
        [Test]
        public void TheWholeAreaFitsTheSandTable()
        {
            var area = WorldMapping.AreaRadiusM * WorldMapping.Scale * 1.15f;
            var scale = VrControls.TableScale(area);
            Assert.That(area * scale, Is.EqualTo(VrControls.TableRadiusM).Within(1e-4));
            // A 4 km track position lands inside the table.
            var edge = WorldMapping.ToWorld(4000f, 0f, 50f).x * scale;
            Assert.That(edge, Is.LessThan(VrControls.TableRadiusM));
            Assert.That(VrControls.TableScale(0f), Is.EqualTo(1f));
        }

        [Test]
        public void ButtonsActOncePerPressNotWhileHeld()
        {
            var c = new VrControls(Vocabulary.Classifications);
            Assert.That(c.Edges(true, false, false), Is.EqualTo((true, false, false)));
            Assert.That(c.Edges(true, false, false), Is.EqualTo((false, false, false))); // held
            Assert.That(c.Edges(false, true, true), Is.EqualTo((false, true, true)));
            Assert.That(c.Edges(false, false, false), Is.EqualTo((false, false, false)));
        }

        [Test]
        public void ClassificationCyclesThroughTheVocabularyAndWraps()
        {
            var c = new VrControls(Vocabulary.Classifications);
            var seen = new System.Collections.Generic.List<string>();
            for (var i = 0; i < Vocabulary.Classifications.Length; i++)
            {
                seen.Add(c.Classification);
                c.NextClassification();
            }
            CollectionAssert.AreEqual(Vocabulary.Classifications, seen);
            Assert.That(c.Classification, Is.EqualTo(Vocabulary.Classifications[0]));
        }

        [Test]
        public void StatusTellsTheTraineeWhatIsSelectedAndHowToAct()
        {
            var c = new VrControls(Vocabulary.Classifications);
            var none = c.Status(new string[0], Vocabulary.Label, null, null);
            StringAssert.Contains("No track selected", none);
            StringAssert.Contains("B/Y: submit", none);
            var some = c.Status(new[] { "TRK-002", "TRK-001" }, Vocabulary.Label, "TRK-003", "Decision recorded.");
            StringAssert.StartsWith("Pointing at TRK-003", some);
            StringAssert.Contains("Selected: TRK-001, TRK-002", some);
            StringAssert.Contains("Decision recorded.", some);
        }
    }
}
