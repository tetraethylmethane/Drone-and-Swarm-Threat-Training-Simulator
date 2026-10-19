// The environment around the protected virtual site: sky, sun, haze, terrain, the site itself and
// trees. Skies are CC0 HDRIs from Poly Haven and ground textures CC0 materials from ambientCG
// (THIRD_PARTY_NOTICES.md); everything else is generated here. One world unit is 10 m
// (WorldMapping.Scale). Inside 4 km the ground stays flat, so range rings and tracks are never hidden.
using UnityEngine;

namespace Drikr
{
    public sealed class Scenery
    {
        public const float FlatRadius = 430f;   // units: flat beyond the 4 km ring
        public const float OuterRadius = 900f;  // units: hills out to 9 km

        readonly Transform _world;
        readonly Light _sun;
        readonly MeshRenderer _ground;
        readonly MeshFilter _groundMesh;
        readonly System.Collections.Generic.List<(Transform t, float r)> _trees =
            new System.Collections.Generic.List<(Transform, float)>();
        readonly Transform _radar;
        readonly Material _lit;
        public Material Lit => _lit;

        /// <summary>Fog density (exponential squared, per world unit) for the optical camera.</summary>
        public float OpticalFogDensity { get; private set; }
        public Color FogColor { get; private set; } = new Color(0.8f, 0.83f, 0.86f);

        public Scenery(Transform world)
        {
            _world = world;
            _lit = Resources.Load<Material>("DrikrMaterials/Lit") ?? new Material(Shader.Find("Standard"));

            _sun = new GameObject("Sun").AddComponent<Light>();
            _sun.type = LightType.Directional;
            _sun.shadows = LightShadows.Soft;
            _sun.shadowStrength = 0.7f;
            RenderSettings.sun = _sun;
            QualitySettings.shadowDistance = 1400f;

            var ground = new GameObject("Terrain");
            ground.transform.SetParent(world, false);
            _groundMesh = ground.AddComponent<MeshFilter>();
            _groundMesh.sharedMesh = TerrainMesh(OuterRadius);
            _ground = ground.AddComponent<MeshRenderer>();
            _ground.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;

            _radar = BuildSite(world);
            BuildTrees(world);
        }

        public Material Mat(Color c, float smoothness = 0.25f)
        {
            var m = new Material(_lit) { color = c };
            m.SetFloat("_Glossiness", smoothness);
            return m;
        }

        // ------------------------------------------------------------------ terrain --

        static float Height(float x, float z)
        {
            var r = Mathf.Sqrt(x * x + z * z);
            var t = Mathf.Clamp01((r - FlatRadius) / (OuterRadius - FlatRadius));
            var ramp = t * t * (3f - 2f * t);
            var n = Mathf.PerlinNoise(x * 0.004f + 13.1f, z * 0.004f + 7.7f) * 0.7f
                    + Mathf.PerlinNoise(x * 0.012f + 3.3f, z * 0.012f + 1.9f) * 0.3f;
            return ramp * (12f + n * 55f) - 0.05f;
        }

        static Mesh TerrainMesh(float outer)
        {
            const int rings = 90, segs = 160;
            var verts = new Vector3[(rings + 1) * segs + 1];
            var uv = new Vector2[verts.Length];
            verts[0] = new Vector3(0f, -0.05f, 0f);
            for (var i = 1; i <= rings; i++)
            {
                var r = outer * Mathf.Pow(i / (float)rings, 1.3f);
                for (var j = 0; j < segs; j++)
                {
                    var a = j * Mathf.PI * 2f / segs;
                    float x = Mathf.Cos(a) * r, z = Mathf.Sin(a) * r;
                    verts[1 + (i - 1) * segs + j] = new Vector3(x, Height(x, z), z);
                }
            }
            for (var k = 0; k < verts.Length; k++) uv[k] = new Vector2(verts[k].x, verts[k].z) / 24f;
            var tris = new System.Collections.Generic.List<int>();
            for (var j = 0; j < segs; j++) tris.AddRange(new[] { 0, 1 + (j + 1) % segs, 1 + j });
            for (var i = 1; i < rings; i++)
                for (var j = 0; j < segs; j++)
                {
                    int a = 1 + (i - 1) * segs + j, b = 1 + (i - 1) * segs + (j + 1) % segs;
                    int c = a + segs, d = b + segs;
                    tris.AddRange(new[] { a, b, c, b, d, c });
                }
            var mesh = new Mesh { indexFormat = UnityEngine.Rendering.IndexFormat.UInt32, vertices = verts, uv = uv };
            mesh.SetTriangles(tris, 0);
            mesh.RecalculateNormals();
            mesh.RecalculateTangents();
            mesh.RecalculateBounds();
            return mesh;
        }

        // --------------------------------------------------------------- site, trees --

        Transform BuildSite(Transform world)
        {
            var concrete = Resources.Load<Material>("DrikrMaterials/Ground_urban");
            var pad = Prim(world, PrimitiveType.Cube, concrete ?? Mat(new Color(0.7f, 0.7f, 0.68f)),
                new Vector3(0f, 0.02f, 0f), new Vector3(22f, 0.08f, 22f));
            pad.name = "Protected virtual site pad";
            var walls = Mat(new Color(0.78f, 0.76f, 0.7f));
            var roofs = Mat(new Color(0.34f, 0.37f, 0.35f));
            foreach (var (p, s) in new[]
                     {
                         (new Vector3(-5f, 0f, -4f), new Vector3(6f, 2.2f, 4f)),
                         (new Vector3(5f, 0f, -5f), new Vector3(4f, 1.6f, 5f)),
                         (new Vector3(-4f, 0f, 6f), new Vector3(5f, 1.4f, 3f)),
                     })
            {
                Prim(world, PrimitiveType.Cube, walls, p + Vector3.up * s.y / 2f, s);
                Prim(world, PrimitiveType.Cube, roofs, p + Vector3.up * (s.y + 0.05f), new Vector3(s.x + 0.2f, 0.1f, s.z + 0.2f));
            }
            var steel = Mat(new Color(0.42f, 0.45f, 0.44f), 0.5f);
            Prim(world, PrimitiveType.Cylinder, steel, new Vector3(5f, 2f, 5f), new Vector3(0.3f, 2f, 0.3f)); // mast
            var radar = new GameObject("Radar antenna").transform;
            radar.SetParent(world, false);
            radar.localPosition = new Vector3(5f, 4.1f, 5f);
            Prim(radar, PrimitiveType.Cube, steel, new Vector3(0f, 0.4f, 0f), new Vector3(2.6f, 0.9f, 0.12f));
            Prim(radar, PrimitiveType.Cylinder, steel, Vector3.zero, new Vector3(0.6f, 0.15f, 0.6f));
            return radar;
        }

        void BuildTrees(Transform world)
        {
            var trunk = Mat(new Color(0.33f, 0.26f, 0.19f));
            var leaves = Mat(new Color(0.24f, 0.36f, 0.2f), 0.1f);
            var rng = new System.Random(20261019);
            for (var k = 0; k < 420; k++)
            {
                var r = 30f + (float)rng.NextDouble() * (OuterRadius - 60f);
                var a = (float)rng.NextDouble() * Mathf.PI * 2f;
                float x = Mathf.Cos(a) * r, z = Mathf.Sin(a) * r;
                var h = 1.2f + (float)rng.NextDouble() * 1.6f;
                var y = Height(x, z);
                _trees.Add((Prim(world, PrimitiveType.Cylinder, trunk, new Vector3(x, y + h * 0.3f, z),
                    new Vector3(0.18f, h * 0.3f, 0.18f)), r));
                _trees.Add((Prim(world, PrimitiveType.Sphere, leaves, new Vector3(x, y + h * 0.8f, z),
                    new Vector3(h * 0.7f, h * 0.8f, h * 0.7f)), r));
            }
        }

        static Transform Prim(Transform parent, PrimitiveType type, Material m, Vector3 pos, Vector3 scale)
        {
            var go = GameObject.CreatePrimitive(type);
            Object.Destroy(go.GetComponent<Collider>());
            go.GetComponent<Renderer>().sharedMaterial = m;
            go.transform.SetParent(parent, false);
            go.transform.localPosition = pos;
            go.transform.localScale = scale;
            return go.transform;
        }

        /// <summary>VR sand table: the ground ends at the table's edge (just beyond 4 km).</summary>
        public void UseTableMode()
        {
            _groundMesh.sharedMesh = TerrainMesh(FlatRadius * 1.04f);
            foreach (var (t, r) in _trees) t.gameObject.SetActive(r < FlatRadius);
        }

        public void Update() => _radar.Rotate(Vector3.up, 90f * Time.deltaTime, Space.Self);

        // ---------------------------------------------------------------- conditions --

        /// <summary>Sky, sun, ambient light and haze for the scenario's environment.</summary>
        public void Apply(EnvironmentInfo env, Camera overview)
        {
            var night = env?.TimeOfDay == "night";
            var dusk = env?.TimeOfDay == "dusk";
            var weather = env?.Weather ?? "clear";
            var dull = weather == "fog" || weather == "rain" || weather == "haze";
            var sky = night ? "Sky_night" : dull ? "Sky_overcast" : dusk ? "Sky_dusk" : "Sky_day";
            var skyMat = Resources.Load<Material>("DrikrMaterials/" + sky);
            if (skyMat != null)
            {
                RenderSettings.skybox = skyMat;
                overview.clearFlags = CameraClearFlags.Skybox;
            }
            RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Skybox;
            RenderSettings.ambientIntensity = night ? 0.6f : 1f;

            _sun.transform.rotation = Quaternion.Euler(night ? 35f : dusk ? 9f : 48f, night ? 150f : dusk ? 250f : 130f, 0f);
            _sun.color = night ? new Color(0.62f, 0.7f, 0.9f) : dusk ? new Color(1f, 0.74f, 0.52f) : new Color(1f, 0.96f, 0.9f);
            _sun.intensity = night ? 0.25f : dull ? 0.55f : dusk ? 0.85f : 1.15f;
            _sun.shadowStrength = dull ? 0.35f : 0.75f;
            DynamicGI.UpdateEnvironment();

            var terrain = env?.Terrain ?? "rural";
            var ground = Resources.Load<Material>("DrikrMaterials/Ground_" + terrain)
                         ?? Resources.Load<Material>("DrikrMaterials/Ground_rural");
            if (ground != null) _ground.sharedMaterial = ground;

            // Haze: the overview is a sensor picture, so it gets only a light atmosphere; the
            // optical camera gets the full visibility (OpticalView).
            var visUnits = Mathf.Max(0.3f, env?.VisibilityKm ?? 15f) * 1000f * WorldMapping.Scale;
            OpticalFogDensity = 2f / visUnits;
            FogColor = night ? new Color(0.08f, 0.1f, 0.13f) : dull ? new Color(0.72f, 0.74f, 0.76f)
                : dusk ? new Color(0.86f, 0.76f, 0.66f) : new Color(0.78f, 0.84f, 0.9f);
            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.ExponentialSquared;
            RenderSettings.fogColor = FogColor;
            RenderSettings.fogDensity = OverviewFogDensity / WorldScale;
        }

        public float OverviewFogDensity => Mathf.Min(OpticalFogDensity, 0.0011f);

        /// <summary>Fog is per world distance; in VR the world is shrunk to the table.</summary>
        public float WorldScale => Mathf.Max(1e-6f, _world.lossyScale.x);
    }
}
