// Screen-reader support for the IMGUI panel.
//
// IMGUI draws pixels only, so assistive technology cannot see it. Every frame the panel registers
// each control it draws (role, label, value, state, rectangle) with this class, which mirrors them
// into a UnityEngine.Accessibility hierarchy. The player exposes that hierarchy to the operating
// system's screen reader (Windows UI Automation: Narrator, NVDA, JAWS; macOS: VoiceOver).
// Screen-reader actions (activate, focus) are queued and replayed into the next IMGUI pass, so they
// take exactly the same code path as a mouse click or key press.
using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.Accessibility;

namespace Drikr
{
    public enum A11yRole { Header, Text, Button, Toggle, TextField }

    /// <summary>One control as drawn in the current frame.</summary>
    public sealed class A11yItem
    {
        public string Key;
        public A11yRole Role;
        public string Label;
        public string Value;
        public string Hint;
        public bool Enabled = true;
        public bool Selected;
        public Rect ScreenRect;
    }

    public sealed class PanelAccessibility
    {
        readonly List<A11yItem> _frame = new List<A11yItem>();
        readonly Dictionary<string, int> _occurrences = new Dictionary<string, int>();
        readonly HashSet<string> _pendingInvoke = new HashSet<string>();
        List<A11yItem> _published = new List<A11yItem>();
        readonly Dictionary<string, AccessibilityNode> _nodes = new Dictionary<string, AccessibilityNode>();
        AccessibilityHierarchy _hierarchy;
        string _structure = "";
        bool _screenChanged;

        /// <summary>A text field the screen reader moved to; the panel gives it keyboard focus.</summary>
        public string PendingFocus { get; set; }

        /// <summary>Items published to the hierarchy in the last frame (read by tests).</summary>
        public IReadOnlyList<A11yItem> Published => _published;

        public static bool Active => AssistiveSupport.isScreenReaderEnabled;

        /// <summary>Panel text rewritten for speech: "·" separators and line breaks become pauses.</summary>
        public static string Speakable(string text)
        {
            if (string.IsNullOrEmpty(text)) return "";
            var lines = text.Split('\n')
                .Select(l => l.Replace("·", ",").Trim())
                .Where(l => l.Length > 0)
                .ToList();
            for (var i = 0; i < lines.Count - 1; i++)
                if (!char.IsPunctuation(lines[i][lines[i].Length - 1])) lines[i] += ".";
            var joined = string.Join(" ", lines);
            while (joined.Contains("  ")) joined = joined.Replace("  ", " ");
            return joined.Replace(" ,", ",");
        }

        /// <summary>Call at the start of each repaint pass.</summary>
        public void BeginFrame()
        {
            _frame.Clear();
            _occurrences.Clear();
        }

        /// <summary>Stable key: role + label + occurrence (labels repeat, e.g. one "Launch" per row).</summary>
        public string KeyFor(A11yRole role, string label)
        {
            var baseKey = role + "|" + label;
            _occurrences.TryGetValue(baseKey, out var n);
            _occurrences[baseKey] = n + 1;
            return baseKey + "|" + n;
        }

        public void Add(A11yItem item) => _frame.Add(item);

        /// <summary>True once if the screen reader activated this control since the last pass.</summary>
        public bool ConsumeInvoke(string key) => _pendingInvoke.Remove(key);

        /// <summary>Speak a short message (errors, confirmations, new tracks).</summary>
        public static void Announce(string message)
        {
            if (Active && !string.IsNullOrWhiteSpace(message))
                AssistiveSupport.notificationDispatcher.SendAnnouncement(message);
        }

        /// <summary>Signal that the whole screen changed (sign-in, home, exercise, result).</summary>
        public void ScreenChanged() => _screenChanged = true;

        /// <summary>Call at the end of each repaint pass: publish the frame to the OS screen reader.</summary>
        public void EndFrame()
        {
            if (!Active)
            {
                if (_hierarchy != null)
                {
                    AssistiveSupport.activeHierarchy = null;
                    _hierarchy = null;
                    _nodes.Clear();
                    _structure = "";
                }
                return;
            }
            var structure = string.Join("\n", _frame.Select(i => i.Key));
            if (_hierarchy == null || structure != _structure)
            {
                Rebuild();
                _structure = structure;
            }
            else
            {
                foreach (var item in _frame) Update(_nodes[item.Key], item);
            }
            _published = _frame.ToList();
            if (_screenChanged && _published.Count > 0)
            {
                AssistiveSupport.notificationDispatcher.SendScreenChanged(_nodes[_published[0].Key]);
                _screenChanged = false;
            }
        }

        void Rebuild()
        {
            var h = new AccessibilityHierarchy();
            _nodes.Clear();
            foreach (var item in _frame)
            {
                var node = h.AddNode(item.Label);
                var key = item.Key;
                var role = item.Role;
                node.invoked += () =>
                {
                    _pendingInvoke.Add(key);
                    return true;
                };
                node.focusChanged += (_, focused) =>
                {
                    if (focused && role == A11yRole.TextField) PendingFocus = key;
                };
                _nodes[key] = node;
                Update(node, item);
            }
            _hierarchy = h;
            AssistiveSupport.activeHierarchy = h;
            if (_frame.Count > 0)
                AssistiveSupport.notificationDispatcher.SendLayoutChanged(_nodes[_frame[0].Key]);
        }

        static void Update(AccessibilityNode node, A11yItem item)
        {
            if (node.label != item.Label) node.label = item.Label;
            var value = item.Value ?? "";
            if (node.value != value) node.value = value;
            var hint = item.Hint ?? "";
            if (node.hint != hint) node.hint = hint;
            var role = item.Role switch
            {
                A11yRole.Header => AccessibilityRole.Header,
                A11yRole.Button => AccessibilityRole.Button,
                A11yRole.Toggle => AccessibilityRole.Toggle,
                A11yRole.TextField => AccessibilityRole.TextField,
                _ => AccessibilityRole.StaticText,
            };
            if (node.role != role) node.role = role;
            var state = AccessibilityState.None;
            if (!item.Enabled) state |= AccessibilityState.Disabled;
            if (item.Selected) state |= AccessibilityState.Selected;
            if (node.state != state) node.state = state;
            if (node.frame != item.ScreenRect) node.frame = item.ScreenRect;
        }
    }
}
