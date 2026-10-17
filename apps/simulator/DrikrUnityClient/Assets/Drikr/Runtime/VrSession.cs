// Optional VR (OpenXR) for the Unity client, started only with -drikrVr. The XR loader is not
// initialised at startup (Assets/XR settings, InitManagerOnStart = false), so the desktop client
// is unchanged when the flag is absent, and falls back to the desktop when no headset or OpenXR
// runtime is present.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.XR;
using UnityEngine.XR.Management;

namespace Drikr
{
    public sealed class VrSession
    {
        public bool Active { get; private set; }
        public string FailureReason { get; private set; }

        public bool TryStart()
        {
            var manager = XRGeneralSettings.Instance != null ? XRGeneralSettings.Instance.Manager : null;
            if (manager == null)
            {
                FailureReason = "XR is not configured in this build.";
                return false;
            }
            if (manager.activeLoader == null) manager.InitializeLoaderSync();
            if (manager.activeLoader == null)
            {
                FailureReason = "No VR headset or OpenXR runtime was found.";
                return false;
            }
            manager.StartSubsystems();
            // Floor-level origin, so the sand table stands at waist height whatever the headset's start pose.
            var inputs = new List<XRInputSubsystem>();
            SubsystemManager.GetSubsystems(inputs);
            foreach (var input in inputs) input.TrySetTrackingOriginMode(TrackingOriginModeFlags.Floor);
            Active = true;
            return true;
        }

        public void Stop()
        {
            if (!Active) return;
            var manager = XRGeneralSettings.Instance.Manager;
            manager.StopSubsystems();
            manager.DeinitializeLoader();
            Active = false;
        }

        static InputDevice Device(XRNode node) => InputDevices.GetDeviceAtXRNode(node);

        public static bool Pose(XRNode node, out Vector3 position, out Quaternion rotation)
        {
            var d = Device(node);
            position = default;
            rotation = Quaternion.identity;
            if (!d.isValid) return false;
            var posUsage = node == XRNode.Head || node == XRNode.CenterEye ? CommonUsages.centerEyePosition : CommonUsages.devicePosition;
            var rotUsage = node == XRNode.Head || node == XRNode.CenterEye ? CommonUsages.centerEyeRotation : CommonUsages.deviceRotation;
            return d.TryGetFeatureValue(posUsage, out position) & d.TryGetFeatureValue(rotUsage, out rotation);
        }

        public static (bool trigger, bool primary, bool secondary) Buttons(XRNode hand)
        {
            var d = Device(hand);
            if (!d.isValid) return (false, false, false);
            d.TryGetFeatureValue(CommonUsages.triggerButton, out var t);
            d.TryGetFeatureValue(CommonUsages.primaryButton, out var p);
            d.TryGetFeatureValue(CommonUsages.secondaryButton, out var s);
            return (t, p, s);
        }

        /// <summary>Connected XR devices, for the log when diagnosing a headset.</summary>
        public static string DescribeDevices()
        {
            var list = new List<InputDevice>();
            InputDevices.GetDevices(list);
            return list.Count == 0 ? "none" : string.Join(", ", list.ConvertAll(d => d.name));
        }
    }
}
