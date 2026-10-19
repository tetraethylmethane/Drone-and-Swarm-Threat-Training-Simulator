// Simulated optical (EO) sensor view of the selected track: a narrow camera on the site's sensor
// mast, zoomed so the contact fills about half the frame height. The model it sees follows the
// optical sensor's own class hint (which can be wrong), never the hidden ground truth (S-01). Image
// resolution falls with the hint's quality and the scenario's visibility is applied in full, so a
// poor sighting looks poor.
using UnityEngine;

namespace Drikr
{
    public sealed class OpticalView
    {
        /// <summary>True-size models, seen only by this camera.</summary>
        public const int Layer = 8;
        /// <summary>Enlarged symbols on the overview, hidden from this camera.</summary>
        public const int SymbolLayer = 9;

        readonly Scenery _scenery;
        readonly Camera _cam;
        RenderTexture _rt;
        float _savedFog;

        public bool Active { get; private set; }
        public Texture Texture => _rt;

        public OpticalView(Scenery scenery)
        {
            _scenery = scenery;
            _cam = new GameObject("Optical sensor camera").AddComponent<Camera>();
            _cam.enabled = false; // rendered on demand
            _cam.cullingMask = (1 << 0) | (1 << Layer);
            _cam.clearFlags = CameraClearFlags.Skybox;
            Camera.onPreRender += Before;
            Camera.onPostRender += After;
        }

        /// <summary>Frame width in pixels for an optical hint quality (0..1): coarse when poor.</summary>
        public static int ResolutionFor(float quality) =>
            quality < 0.25f ? 48 : quality < 0.4f ? 96 : quality < 0.55f ? 160 : quality < 0.7f ? 256 : 400;

        /// <summary>Narrowest field of view (degrees): the zoom limit of a typical long-range EO camera.
        /// Beyond the range where a contact can fill half the frame, it appears smaller.</summary>
        public const float MinFieldOfView = 0.1f;

        /// <summary>Field of view (degrees) that makes a target of this span fill half the frame height,
        /// within the camera's zoom limit.</summary>
        public static float FieldOfViewFor(float spanWorld, float distanceWorld) =>
            Mathf.Clamp(2f * Mathf.Rad2Deg * Mathf.Atan(spanWorld * 2f / (2f * Mathf.Max(distanceWorld, 1e-4f))),
                MinFieldOfView, 40f);

        public void Show(Vector3 sensor, Vector3 target, float spanWorld, float quality)
        {
            var w = ResolutionFor(quality);
            var h = Mathf.RoundToInt(w * 9f / 16f);
            if (_rt == null || _rt.width != w)
            {
                if (_rt != null) _rt.Release();
                _rt = new RenderTexture(w, h, 24)
                {
                    filterMode = w < 256 ? FilterMode.Point : FilterMode.Bilinear,
                    name = "Optical sensor",
                };
            }
            var to = target - sensor;
            var dist = to.magnitude;
            _cam.targetTexture = _rt;
            _cam.transform.SetPositionAndRotation(sensor, Quaternion.LookRotation(to));
            _cam.fieldOfView = FieldOfViewFor(spanWorld, dist);
            _cam.nearClipPlane = Mathf.Max(dist * 0.25f, 1e-4f);
            _cam.farClipPlane = dist * 6f;
            _cam.Render();
            Active = true;
        }

        public void Hide() => Active = false;

        void Before(Camera c)
        {
            if (c != _cam) return;
            _savedFog = RenderSettings.fogDensity;
            RenderSettings.fogDensity = _scenery.OpticalFogDensity / _scenery.WorldScale;
        }

        void After(Camera c)
        {
            if (c == _cam) RenderSettings.fogDensity = _savedFog;
        }
    }
}
