// VR presentation logic (no XR dependency, so it is unit-tested in EditMode).
//
// In VR the tactical picture is shown as a sand table: the whole 4 km area shrunk to a table in
// front of the trainee, so tracks stay readable and nobody moves through kilometres of space. The
// right controller points at tracks; the trigger selects, the primary button (A) chooses the
// classification and the secondary button (B) submits it. The left controller sends training
// responses: the trigger chooses the response and the primary button (X) sends it. Every decision
// goes to the server exactly as from the desktop panel: VR adds input and presentation only (ADR-001).
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
        public int ResponseIndex { get; private set; }

        readonly string[] _classes;
        readonly string[] _responses;
        bool _trigger, _primary, _secondary, _leftTrigger, _leftPrimary;

        public VrControls(string[] classes, string[] responses = null)
        {
            if (classes == null || classes.Length == 0) throw new ArgumentException("no classifications");
            _classes = classes;
            _responses = responses ?? Vocabulary.Responses;
        }

        public string Classification => _classes[ClassIndex];
        public string Response => _responses[ResponseIndex];

        public void NextClassification() => ClassIndex = (ClassIndex + 1) % _classes.Length;
        public void NextResponse() => ResponseIndex = (ResponseIndex + 1) % _responses.Length;

        /// <summary>Left-hand presses this frame: choose the next response, send it.</summary>
        public (bool nextResponse, bool sendResponse) LeftEdges(bool trigger, bool primary)
        {
            var result = (trigger && !_leftTrigger, primary && !_leftPrimary);
            _leftTrigger = trigger;
            _leftPrimary = primary;
            return result;
        }

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
                "Response: " + label(Response),
                "Right trigger: select   A: change   B: submit",
                "Left trigger: change response   Left X: send response",
            };
            if (!string.IsNullOrEmpty(pointedAt)) lines.Insert(0, "Pointing at " + pointedAt);
            if (!string.IsNullOrEmpty(notice)) lines.Add(notice);
            return string.Join("\n", lines);
        }
    }
}
