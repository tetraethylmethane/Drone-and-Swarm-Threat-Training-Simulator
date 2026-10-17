// Configures optional VR for the standalone players (batch mode):
//   Unity.exe -batchmode -projectPath <project> -executeMethod Drikr.EditorTools.XrSetup.Configure -quit
// OpenXR is the loader; it is NOT initialised at startup, so the desktop client is unchanged and
// VR starts only with -drikrVr (VrSession). Common controller profiles are enabled.
using UnityEditor;
using UnityEditor.XR.Management;
using UnityEditor.XR.Management.Metadata;
using UnityEngine;
using UnityEngine.XR.Management;
using UnityEngine.XR.OpenXR;
using UnityEngine.XR.OpenXR.Features.Interactions;

namespace Drikr.EditorTools
{
    public static class XrSetup
    {
        const string Folder = "Assets/XR";
        const string SettingsPath = Folder + "/XRGeneralSettingsPerBuildTarget.asset";

        public static void Configure()
        {
            if (!AssetDatabase.IsValidFolder(Folder)) AssetDatabase.CreateFolder("Assets", "XR");
            if (!EditorBuildSettings.TryGetConfigObject(XRGeneralSettings.k_SettingsKey, out XRGeneralSettingsPerBuildTarget perTarget)
                || perTarget == null)
            {
                perTarget = AssetDatabase.LoadAssetAtPath<XRGeneralSettingsPerBuildTarget>(SettingsPath);
                if (perTarget == null)
                {
                    perTarget = ScriptableObject.CreateInstance<XRGeneralSettingsPerBuildTarget>();
                    AssetDatabase.CreateAsset(perTarget, SettingsPath);
                }
                EditorBuildSettings.AddConfigObject(XRGeneralSettings.k_SettingsKey, perTarget, true);
            }

            var group = BuildTargetGroup.Standalone;
            if (!perTarget.HasSettingsForBuildTarget(group)) perTarget.CreateDefaultSettingsForBuildTarget(group);
            if (!perTarget.HasManagerSettingsForBuildTarget(group)) perTarget.CreateDefaultManagerSettingsForBuildTarget(group);
            var general = perTarget.SettingsForBuildTarget(group);
            general.InitManagerOnStart = false; // VR only on request (-drikrVr)
            XRPackageMetadataStore.AssignLoader(general.Manager, typeof(OpenXRLoader).FullName, group);

            var openxr = OpenXRSettings.GetSettingsForBuildTargetGroup(group);
            UnityEditor.XR.OpenXR.Features.FeatureHelpers.RefreshFeatures(group);
            Enable<KHRSimpleControllerProfile>(openxr);
            Enable<OculusTouchControllerProfile>(openxr);
            Enable<ValveIndexControllerProfile>(openxr);
            Enable<HTCViveControllerProfile>(openxr);

            EditorUtility.SetDirty(perTarget);
            EditorUtility.SetDirty(general);
            if (openxr != null) EditorUtility.SetDirty(openxr);
            AssetDatabase.SaveAssets();
            Debug.Log($"DRIKR_XR configured: loader OpenXR, InitManagerOnStart={general.InitManagerOnStart}, " +
                      $"loaders={general.Manager.activeLoaders.Count}");
        }

        /// <summary>
        /// The OpenXR plugin supports only Windows x64 among this project's players (its build
        /// validation rejects the universal macOS player). XR settings are shared by the whole
        /// Standalone group, so other targets are built with the loader removed: they are desktop
        /// only. Returns an action that restores the configuration.
        /// </summary>
        public static System.Action ForBuild(BuildTarget target)
        {
            if (target == BuildTarget.StandaloneWindows64) return () => { };
            if (!EditorBuildSettings.TryGetConfigObject(XRGeneralSettings.k_SettingsKey, out XRGeneralSettingsPerBuildTarget perTarget)
                || perTarget == null || !perTarget.HasManagerSettingsForBuildTarget(BuildTargetGroup.Standalone))
                return () => { };
            var manager = perTarget.SettingsForBuildTarget(BuildTargetGroup.Standalone).Manager;
            var loader = typeof(OpenXRLoader).FullName;
            if (!XRPackageMetadataStore.RemoveLoader(manager, loader, BuildTargetGroup.Standalone)) return () => { };
            Debug.Log($"DRIKR_XR target={target}: built without VR (OpenXR supports Windows x64 only here)");
            return () => XRPackageMetadataStore.AssignLoader(manager, loader, BuildTargetGroup.Standalone);
        }

        static void Enable<T>(OpenXRSettings settings) where T : UnityEngine.XR.OpenXR.Features.OpenXRFeature
        {
            var f = settings != null ? settings.GetFeature<T>() : null;
            if (f != null) f.enabled = true;
            else Debug.LogWarning($"DRIKR_XR feature not found: {typeof(T).Name}");
        }
    }
}
