// VR presentation logic (no XR dependency, so it is unit-tested in EditMode).
//
// In VR the tactical picture is shown as a sand table: the whole 4 km area shrunk to a table in
// front of the trainee, so tracks stay readable and nobody moves through kilometres of space. The
// right controller points at tracks; the trigger selects, the primary button (A/X) chooses the
// classification and the secondary button (B/Y) submits it. Every decision goes to the server
// exactly as from the desktop panel: VR adds input and presentation only (ADR-001).
using System;
using System.Collections.Generic;
using System.Linq;

namespace Drikr
{
    public sealed class VrControls
    {
        /// <summary>Radius of the sand table in metres.</summary>
        public const float TableRadiusM = 1.0f;

        /// <summary>Uniform scale for the world root so the whole area fits the table.</summary>
        public static float TableScale(float areaRadiusWorldUnits) =>
            areaRadiusWorldUnits > 0 ? TableRadiusM / areaRadiusWorldUnits : 1f;

        public int ClassIndex { get; private set; }

        readonly string[] _classes;
        bool _trigger, _primary, _secondary;

        public VrControls(string[] classes)
        {
            if (classes == null || classes.Length == 0) throw new ArgumentException("no classifications");
            _classes = classes;
        }

        public string Classification => _classes[ClassIndex];

        public void NextClassification() => ClassIndex = (ClassIndex + 1) % _classes.Length;

        /// <summary>Button presses this frame (true once per press, not while held).</summary>
        public (bool select, bool next, bool submit) Edges(bool trigger, bool primary, bool secondary)
        {
            var result = (trigger && !_trigger, primary && !_primary, secondary && !_secondary);
            _trigger = trigger;
            _primary = primary;
            _secondary = secondary;
            return result;
        }

        /// <summary>The text shown above the table.</summary>
        public string Status(IEnumerable<string> selected, Func<string, string> label, string pointedAt, string notice)
        {
            var sel = selected.OrderBy(s => s, StringComparer.Ordinal).ToList();
            var lines = new List<string>
            {
                sel.Count == 0 ? "No track selected" : "Selected: " + string.Join(", ", sel),
                "Classification: " + label(Classification),
                "Trigger: select   A/X: change   B/Y: submit",
            };
            if (!string.IsNullOrEmpty(pointedAt)) lines.Insert(0, "Pointing at " + pointedAt);
            if (!string.IsNullOrEmpty(notice)) lines.Add(notice);
            return string.Join("\n", lines);
        }
    }
}
