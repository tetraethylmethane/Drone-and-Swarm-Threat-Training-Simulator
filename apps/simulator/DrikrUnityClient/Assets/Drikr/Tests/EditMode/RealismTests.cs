// Contact models and the simulated optical view (ContactModels, OpticalView): the rules that keep
// them honest, testable without rendering.
using NUnit.Framework;

namespace Drikr.Tests
{
    public class RealismTests
    {
        [Test]
        public void TheModelFollowsTheReportedClassNotTheTruth()
        {
            // Only a classification or an optical hint chooses the model; with neither, it is unknown.
            Assert.That(ContactModels.KindFor("small_multirotor"), Is.EqualTo(ContactModels.Multirotor));
            Assert.That(ContactModels.KindFor("coordinated_swarm"), Is.EqualTo(ContactModels.Multirotor));
            Assert.That(ContactModels.KindFor("fixed_wing_uas"), Is.EqualTo(ContactModels.FixedWing));
            Assert.That(ContactModels.KindFor("bird_or_clutter"), Is.EqualTo(ContactModels.Bird));
            Assert.That(ContactModels.KindFor("unknown"), Is.EqualTo(ContactModels.Unknown));
            Assert.That(ContactModels.KindFor(null), Is.EqualTo(ContactModels.Unknown));
        }

        [Test]
        public void APoorSightingGivesACoarsePicture()
        {
            Assert.That(OpticalView.ResolutionFor(0.1f), Is.LessThan(OpticalView.ResolutionFor(0.5f)));
            Assert.That(OpticalView.ResolutionFor(0.5f), Is.LessThan(OpticalView.ResolutionFor(0.9f)));
            Assert.That(OpticalView.ResolutionFor(0f), Is.EqualTo(48));
        }

        [Test]
        public void TheZoomFillsHalfTheFrameUntilItsLimitThenTheContactShrinks()
        {
            var span = ContactModels.SpanM(ContactModels.Multirotor) * WorldMapping.Scale; // 0.65 m drone
            float Share(float range) =>
                span / (2f * range * UnityEngine.Mathf.Tan(OpticalView.FieldOfViewFor(span, range) * UnityEngine.Mathf.Deg2Rad / 2f));
            foreach (var range in new[] { 10f, 30f, 60f }) // 100 m to 600 m
                Assert.That(Share(range), Is.EqualTo(0.5f).Within(0.01f), $"range {range}");
            // At 4 km the zoom limit leaves a small drone a speck, as through a real camera.
            Assert.That(Share(400f), Is.LessThan(0.15f).And.GreaterThan(0.05f));
        }
    }
}
