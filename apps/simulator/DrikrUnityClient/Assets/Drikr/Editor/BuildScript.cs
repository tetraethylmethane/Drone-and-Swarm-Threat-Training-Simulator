// Reproducible batch-mode build:
//   Unity.exe -batchmode -nographics -quit -projectPath <project> -executeMethod Drikr.EditorTools.BuildScript.BuildWindows
//   (also BuildLinux, BuildMacOS, BuildAll)
// Generates the material and scene assets, applies offline-safe player settings and builds
// desktop players into Builds/<platform>.
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Drikr.EditorTools
{
    public static class BuildScript
    {
        const string MaterialDir = "Assets/Drikr/Resources/DrikrMaterials";
        const string ScenePath = "Assets/Drikr/Scenes/Main.unity";
        // Official Drikr Systems artwork, copied unchanged from assets/brand/ (see docs/design).
        const string LogoPath = "Assets/Drikr/Resources/DrikrBrand/drikr-logo.png";
        const string IconPath = "Assets/Drikr/Brand/drikr-mark-256.png";

        static void ConfigureTexture(string path)
        {
            if (!(AssetImporter.GetAtPath(path) is TextureImporter imp)) return;
            imp.textureType = TextureImporterType.Default;
            imp.alphaIsTransparency = true;
            imp.mipmapEnabled = false;
            imp.npotScale = TextureImporterNPOTScale.None;
            imp.wrapMode = TextureWrapMode.Clamp;
            imp.textureCompression = TextureImporterCompression.Uncompressed; // keep the logo edges crisp
            imp.SaveAndReimport();
        }

        [MenuItem("Drikr/Prepare assets")]
        public static void PrepareAssets()
        {
            Directory.CreateDirectory(MaterialDir);
            var path = MaterialDir + "/Unlit.mat";
            if (AssetDatabase.LoadAssetAtPath<Material>(path) == null)
            {
                // Resources reference keeps the shader in the player build (Shader.Find alone would not).
                AssetDatabase.CreateAsset(new Material(Shader.Find("Unlit/Color")), path);
            }

            Directory.CreateDirectory(Path.GetDirectoryName(ScenePath)!);
            if (!File.Exists(ScenePath))
            {
                var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                var cam = new GameObject("Main Camera").AddComponent<Camera>();
                cam.tag = "MainCamera";
                new GameObject("Drikr Client").AddComponent<DrikrClientApp>();
                EditorSceneManager.SaveScene(scene, ScenePath);
            }
            AssetDatabase.SaveAssets();
            ConfigureTexture(LogoPath);
            ConfigureTexture(IconPath);
            var icon = AssetDatabase.LoadAssetAtPath<Texture2D>(IconPath);
            if (icon != null) PlayerSettings.SetIcons(NamedBuildTarget.Unknown, new[] { icon }, IconKind.Any);

            PlayerSettings.companyName = "Drikr Systems";
            PlayerSettings.productName = "Drikr Training Simulator";
            PlayerSettings.bundleVersion = "1.0.0";
            PlayerSettings.runInBackground = true; // keep polling (heartbeat) when the window loses focus
            PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
            PlayerSettings.defaultScreenWidth = 1440;
            PlayerSettings.defaultScreenHeight = 900;
            PlayerSettings.resizableWindow = true;
            PlayerSettings.enableCrashReportAPI = false;
            PlayerSettings.insecureHttpOption = InsecureHttpOption.AlwaysAllowed; // localhost / closed training networks
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
        }

        public static void BuildWindows() =>
            Build(BuildTarget.StandaloneWindows64, "Builds/Windows/DrikrTrainingSimulator.exe");

        public static void BuildLinux() =>
            Build(BuildTarget.StandaloneLinux64, "Builds/Linux/DrikrTrainingSimulator.x86_64");

        /// <summary>Universal (Intel and Apple silicon) .app. Unsigned: sign and notarise on a Mac for distribution.</summary>
        public static void BuildMacOS()
        {
            // UnityEditor.OSXStandalone exists only when the macOS module is installed, so set the
            // architecture by reflection to keep this script compiling on machines without it.
            var settings = System.AppDomain.CurrentDomain.GetAssemblies()
                .Select(a => a.GetType("UnityEditor.OSXStandalone.UserBuildSettings")).FirstOrDefault(t => t != null);
            var arch = settings?.GetProperty("architecture");
            if (arch != null) arch.SetValue(null, System.Enum.Parse(arch.PropertyType, "x64ARM64"));
            Debug.Log($"DRIKR_BUILD macOS architecture={(arch != null ? arch.GetValue(null) : "default")}");
            Build(BuildTarget.StandaloneOSX, "Builds/macOS/DrikrTrainingSimulator.app");
        }

        /// <summary>Every desktop target whose build module is installed (CI and release builds).</summary>
        public static void BuildAll()
        {
            var targets = new (BuildTarget Target, System.Action Run)[]
            {
                (BuildTarget.StandaloneWindows64, BuildWindows),
                (BuildTarget.StandaloneLinux64, BuildLinux),
                (BuildTarget.StandaloneOSX, BuildMacOS),
            };
            foreach (var (target, run) in targets)
            {
                if (BuildPipeline.IsBuildTargetSupported(BuildTargetGroup.Standalone, target)) run();
                else Debug.Log($"DRIKR_BUILD target={target} result=Skipped reason=module-not-installed");
            }
        }

        static void Build(BuildTarget target, string output)
        {
            PrepareAssets();
            if (!BuildPipeline.IsBuildTargetSupported(BuildTargetGroup.Standalone, target))
            {
                Debug.LogError($"DRIKR_BUILD target={target} result=Failed reason=module-not-installed");
                EditorApplication.Exit(1);
                return;
            }
            var options = new BuildPlayerOptions
            {
                scenes = new[] { ScenePath },
                locationPathName = output,
                target = target,
                targetGroup = BuildTargetGroup.Standalone,
                options = BuildOptions.None,
            };
            // Build-time checks (OpenXR's included) look at the active target, so make it this one.
            if (EditorUserBuildSettings.activeBuildTarget != target)
                EditorUserBuildSettings.SwitchActiveBuildTarget(BuildTargetGroup.Standalone, target);
            var restoreXr = XrSetup.ForBuild(target); // VR only in the Windows x64 player (ADR-013)
            BuildReport report;
            try
            {
                report = BuildPipeline.BuildPlayer(options);
            }
            finally
            {
                restoreXr();
                AssetDatabase.SaveAssets();
            }
            var s = report.summary;
            Debug.Log($"DRIKR_BUILD target={target} result={s.result} size={s.totalSize} errors={s.totalErrors} warnings={s.totalWarnings} output={s.outputPath}");
            if (s.result != BuildResult.Succeeded) EditorApplication.Exit(1);
        }
    }
}
