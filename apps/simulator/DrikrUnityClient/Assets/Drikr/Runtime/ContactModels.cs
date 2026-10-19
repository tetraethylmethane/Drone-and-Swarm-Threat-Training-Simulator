// Low-poly 3D models for air contacts, built from primitives at true size in metres (forward = +z),
// so they need no third-party assets. The caller scales them: true size for the optical camera,
// enlarged as symbols on the overview. Which model is shown is decided by what the trainee or the
// simulated optical sensor reports, never by the hidden ground truth (security finding S-01).
using UnityEngine;

namespace Drikr
{
    public static class ContactModels
    {
        public const string Multirotor = "multirotor", FixedWing = "fixed_wing", Bird = "bird", Unknown = "unknown";

        /// <summary>The model for a classification or optical hint (null or unrecognised: unknown).</summary>
        public static string KindFor(string classification) => classification switch
        {
            "small_multirotor" => Multirotor,
            "coordinated_swarm" => Multirotor,
            "fixed_wing_uas" => FixedWing,
            "bird_or_clutter" => Bird,
            _ => Unknown,
        };

        /// <summary>Largest dimension in metres, for scaling a model to a symbol size.</summary>
        public static float SpanM(string kind) => kind switch
        {
            Multirotor => 0.65f,
            FixedWing => 2.4f,
            Bird => 1.6f,
            _ => 0.8f,
        };

        /// <summary>Overview symbol size (world units) per model: similar visual weight on the map.</summary>
        public static float SymbolUnits(string kind) => kind switch
        {
            Multirotor => 24f,
            FixedWing => 22f,
            Bird => 20f,
            _ => 12f,
        };

        public static GameObject Build(string kind, Material body, Material dark, int layer, bool symbol = false)
        {
            var root = new GameObject("model " + kind);
            switch (kind)
            {
                case Multirotor: BuildMultirotor(root.transform, body, dark); break;
                case FixedWing: BuildFixedWing(root.transform, body, dark); break;
                case Bird: BuildBird(root.transform, body, dark); break;
                default:
                    if (symbol) // a diamond, the usual mark for an unidentified contact
                        Part(root.transform, PrimitiveType.Cube, body, Vector3.zero, new Vector3(0.5f, 0.5f, 0.5f), new Vector3(45f, 0f, 45f));
                    else // an unresolved speck in the optical view
                        Part(root.transform, PrimitiveType.Sphere, dark, Vector3.zero, new Vector3(0.8f, 0.45f, 0.8f));
                    break;
            }
            foreach (var t in root.GetComponentsInChildren<Transform>(true)) t.gameObject.layer = layer;
            return root;
        }

        static Transform Part(Transform parent, PrimitiveType type, Material mat, Vector3 pos, Vector3 scale,
            Vector3 euler = default)
        {
            var go = GameObject.CreatePrimitive(type);
            Object.Destroy(go.GetComponent<Collider>());
            go.GetComponent<Renderer>().sharedMaterial = mat;
            go.transform.SetParent(parent, false);
            go.transform.localPosition = pos;
            go.transform.localRotation = Quaternion.Euler(euler);
            go.transform.localScale = scale;
            return go.transform;
        }

        static Transform Pivot(Transform parent, string name, Vector3 pos)
        {
            var p = new GameObject(name).transform;
            p.SetParent(parent, false);
            p.localPosition = pos;
            return p;
        }

        static void BuildMultirotor(Transform root, Material body, Material dark)
        {
            Part(root, PrimitiveType.Cube, body, Vector3.zero, new Vector3(0.16f, 0.07f, 0.22f));
            Part(root, PrimitiveType.Sphere, dark, new Vector3(0f, -0.03f, 0.1f), Vector3.one * 0.05f); // camera
            var anim = root.gameObject.AddComponent<ContactAnimator>();
            for (var i = 0; i < 4; i++)
            {
                var a = 45f + i * 90f;
                var dir = Quaternion.Euler(0f, a, 0f) * Vector3.forward;
                Part(root, PrimitiveType.Cube, dark, dir * 0.13f, new Vector3(0.025f, 0.02f, 0.26f), new Vector3(0f, a, 0f));
                var motor = dir * 0.25f;
                Part(root, PrimitiveType.Cylinder, dark, motor + Vector3.up * 0.02f, new Vector3(0.04f, 0.025f, 0.04f));
                var rotor = Pivot(root, "rotor", motor + Vector3.up * 0.05f);
                Part(rotor, PrimitiveType.Cube, dark, Vector3.zero, new Vector3(0.24f, 0.004f, 0.022f));
                Part(rotor, PrimitiveType.Cube, dark, Vector3.zero, new Vector3(0.022f, 0.004f, 0.24f));
                anim.Spin(rotor, i % 2 == 0 ? 1800f : -1800f);
            }
            for (var s = -1; s <= 1; s += 2)
                Part(root, PrimitiveType.Cube, dark, new Vector3(s * 0.07f, -0.08f, 0f), new Vector3(0.012f, 0.012f, 0.22f));
        }

        static void BuildFixedWing(Transform root, Material body, Material dark)
        {
            Part(root, PrimitiveType.Capsule, body, Vector3.zero, new Vector3(0.16f, 0.7f, 0.16f), new Vector3(90f, 0f, 0f));
            Part(root, PrimitiveType.Cube, body, new Vector3(0f, 0.04f, 0.12f), new Vector3(2.4f, 0.025f, 0.28f));
            Part(root, PrimitiveType.Cube, body, new Vector3(0f, 0.02f, -0.62f), new Vector3(0.7f, 0.02f, 0.16f));
            Part(root, PrimitiveType.Cube, body, new Vector3(0f, 0.13f, -0.64f), new Vector3(0.02f, 0.24f, 0.18f));
            var prop = Pivot(root, "propeller", new Vector3(0f, 0f, -0.74f));
            Part(prop, PrimitiveType.Cube, dark, Vector3.zero, new Vector3(0.36f, 0.03f, 0.01f));
            root.gameObject.AddComponent<ContactAnimator>().Spin(prop, 2400f, Vector3.forward);
        }

        static void BuildBird(Transform root, Material body, Material dark)
        {
            Part(root, PrimitiveType.Capsule, body, Vector3.zero, new Vector3(0.14f, 0.22f, 0.14f), new Vector3(90f, 0f, 0f));
            Part(root, PrimitiveType.Sphere, body, new Vector3(0f, 0.04f, 0.24f), Vector3.one * 0.1f);
            Part(root, PrimitiveType.Cube, dark, new Vector3(0f, 0.03f, 0.3f), new Vector3(0.02f, 0.02f, 0.06f)); // beak
            Part(root, PrimitiveType.Cube, body, new Vector3(0f, 0f, -0.26f), new Vector3(0.16f, 0.015f, 0.16f)); // tail
            var anim = root.gameObject.AddComponent<ContactAnimator>();
            for (var s = -1; s <= 1; s += 2)
            {
                var hinge = Pivot(root, "wing", new Vector3(s * 0.06f, 0.02f, 0.02f));
                Part(hinge, PrimitiveType.Cube, body, new Vector3(s * 0.37f, 0f, 0f), new Vector3(0.74f, 0.012f, 0.24f));
                Part(hinge, PrimitiveType.Cube, dark, new Vector3(s * 0.72f, 0f, -0.02f), new Vector3(0.12f, 0.01f, 0.18f));
                anim.Flap(hinge, s);
            }
        }
    }

    /// <summary>Spins rotors and propellers, flaps wings.</summary>
    public sealed class ContactAnimator : MonoBehaviour
    {
        readonly System.Collections.Generic.List<(Transform t, float speed, Vector3 axis)> _spin =
            new System.Collections.Generic.List<(Transform, float, Vector3)>();
        readonly System.Collections.Generic.List<(Transform t, int side)> _flap =
            new System.Collections.Generic.List<(Transform, int)>();
        float _phase;

        public void Spin(Transform t, float degPerSecond, Vector3? axis = null) =>
            _spin.Add((t, degPerSecond, axis ?? Vector3.up));

        public void Flap(Transform hinge, int side) => _flap.Add((hinge, side));

        void Awake() => _phase = Random.value * 10f;

        void Update()
        {
            var dt = Time.deltaTime;
            foreach (var (t, speed, axis) in _spin) t.Rotate(axis, speed * dt, Space.Self);
            var a = Mathf.Sin((Time.time + _phase) * Mathf.PI * 2f * 2.2f) * 32f;
            foreach (var (t, side) in _flap) t.localRotation = Quaternion.Euler(0f, 0f, side * a);
        }
    }
}
