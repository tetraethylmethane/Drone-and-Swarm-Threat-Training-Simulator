// Bookkeeping of the screen-reader layer. End-to-end behaviour with a real UI Automation client is
// checked against the built player by scripts/unity-a11y-check.ps1.
using NUnit.Framework;

namespace Drikr.Tests
{
    public class AccessibilityTests
    {
        [Test]
        public void KeysAreStableAndDistinguishRepeatedLabels()
        {
            var a = new PanelAccessibility();
            a.BeginFrame();
            var first = a.KeyFor(A11yRole.Button, "Launch");
            var second = a.KeyFor(A11yRole.Button, "Launch");
            var text = a.KeyFor(A11yRole.Text, "Launch");
            Assert.AreNotEqual(first, second);
            Assert.AreNotEqual(first, text);

            a.BeginFrame(); // next IMGUI pass: same controls, same keys
            Assert.AreEqual(first, a.KeyFor(A11yRole.Button, "Launch"));
            Assert.AreEqual(second, a.KeyFor(A11yRole.Button, "Launch"));
        }

        [Test]
        public void TextIsRewrittenForSpeech()
        {
            Assert.AreEqual("TRK-001 RF, no hint. mine: not classified, -",
                PanelAccessibility.Speakable("TRK-001 RF · no hint\n   mine: not classified · -"));
            Assert.AreEqual("Overall 73.3% (Passed). Pass mark 70%. Open the web application.",
                PanelAccessibility.Speakable("Overall 73.3% (Passed). Pass mark 70%.\nOpen the web application."));
            Assert.AreEqual("", PanelAccessibility.Speakable(null));
        }

        [Test]
        public void InvokesAreConsumedOnce()
        {
            var a = new PanelAccessibility();
            Assert.IsFalse(a.ConsumeInvoke("Button|Sign in|0"));
        }

        [Test]
        public void PublishesNothingWithoutAScreenReader()
        {
            var a = new PanelAccessibility();
            a.BeginFrame();
            a.Add(new A11yItem { Key = a.KeyFor(A11yRole.Header, "Sign in"), Role = A11yRole.Header, Label = "Sign in" });
            a.EndFrame();
            if (PanelAccessibility.Active) Assert.Ignore("a screen reader is running on this machine");
            Assert.AreEqual(0, a.Published.Count);
        }
    }
}
