// Drikr Systems Unity client: a presentation-only visual adapter for the training simulator.
// All simulation state, timing and scoring stay on the server (ADR-001). This component signs in,
// polls the session feed, renders the trainee-visible track picture in 3D, and submits the
// predefined training actions. It contains no simulation or scoring logic.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.XR;
using UnityEngine.Accessibility;

namespace Drikr
{
    public sealed class DrikrClientApp : MonoBehaviour
    {
        enum Screen { Login, Home, Exercise, Result }

        const float PollIntervalRunning = 1f;
        const float PollIntervalIdle = 4f;

        // --- configuration and state ------------------------------------------------
        string _apiUrl = "http://localhost:8080/api/v1";
        string _username = "", _password = "", _mfaCode = "";
        string _caCertPath; // -drikrCa / DRIKR_CA_CERT: private training-network CA for HTTPS
        // -drikrVr: optional VR sand-table view (VrSession, VrControls); desktop when absent or unavailable
        VrSession _vr;
        VrControls _vrc;
        TextMesh _vrText;
        LineRenderer _vrRay;
        Camera _backdrop;
        string _vrPointed;
        bool VrActive => _vr != null && _vr.Active;
        Texture2D _logo;
        Screen _screen = Screen.Login;
        DrikrApi _api;
        string _error, _notice;
        bool _busy;

        List<Assignment> _assignments = new List<Assignment>();
        List<ScenarioSummary> _practice = new List<ScenarioSummary>();

        SessionState _state;
        Briefing _briefing;
        TrackPicture _picture = new TrackPicture();
        int _sinceMs;
        float _nextPoll, _syncRealtime;
        bool _polling, _connectionRetrying;
        readonly HashSet<string> _selected = new HashSet<string>();
        int _classIndex = -1, _confIndex = 1;
        string _resultText;
        Vector2 _scroll;

        // --- scene ---------------------------------------------------------------
        Camera _cam;
        Transform _world;
        readonly Dictionary<string, TrackView> _views = new Dictionary<string, TrackView>();
        float _yaw, _pitch = 40f, _distance = 480f;
        Material _matGround, _matRing, _matSite, _matTrail;
        GUIStyle _label, _small, _heading, _tag;

        sealed class TrackView
        {
            public GameObject Marker, Stalk, SelectRing;
            public LineRenderer Trail;
            public Material Mat;
        }

        static readonly Dictionary<string, Color> ClassColors = new Dictionary<string, Color>
        {
            { "unclassified", Hex("#7C817D") },
            { "unknown", Hex("#5B605C") },
            { "small_multirotor", Hex("#B4562B") },
            { "fixed_wing_uas", Hex("#2D4F73") },
            { "coordinated_swarm", Hex("#7A2E5C") },
            { "bird_or_clutter", Hex("#5D7A3A") },
        };

        static Color Hex(string h) => ColorUtility.TryParseHtmlString(h, out var c) ? c : Color.gray;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Bootstrap()
        {
            if (FindAnyObjectByType<DrikrClientApp>() != null) return;
            new GameObject("Drikr Client").AddComponent<DrikrClientApp>();
        }

        void Awake()
        {
            var args = Environment.GetCommandLineArgs();
            _apiUrl = ResolveApiUrl(args, Environment.GetEnvironmentVariable("DRIKR_API_URL"), _apiUrl);
            _caCertPath = ResolveArg(args, "-drikrCa", Environment.GetEnvironmentVariable("DRIKR_CA_CERT"), null);
            _logo = Resources.Load<Texture2D>("DrikrBrand/drikr-logo");
            // -drikrScreenReader: publish the accessibility tree even if no screen reader is detected
            // (for testing with UI Automation tools, or screen readers the OS does not report).
            if (Array.IndexOf(args, "-drikrScreenReader") >= 0)
                AssistiveSupport.screenReaderStatusOverride = AssistiveSupport.ScreenReaderStatusOverride.ForceEnabled;
            Application.targetFrameRate = 60;
            BuildScene();
            if (Array.IndexOf(args, "-drikrVr") >= 0) StartVr();
        }

        /// <summary>Command line `-drikrApi URL` wins, then DRIKR_API_URL, then the default.</summary>
        public static string ResolveApiUrl(string[] args, string env, string fallback) =>
            ResolveArg(args, "-drikrApi", env, fallback);

        public static string ResolveArg(string[] args, string flag, string env, string fallback)
        {
            for (var i = 0; i < args.Length - 1; i++)
                if (args[i] == flag) return args[i + 1];
            return string.IsNullOrWhiteSpace(env) ? fallback : env;
        }

        void OnDestroy()
        {
            _vr?.Stop();
            _api?.Dispose();
        }

        // ------------------------------------------------------------------------
        // Opt-in smoke test of the built player (CI / release verification):
        //   DrikrTrainingSimulator.exe -drikrSmoke <screenshot.png> -drikrApi <url>
        // Credentials come from DRIKR_SMOKE_USER / DRIKR_SMOKE_PASSWORD. Exit code 0 = pass.
        // ------------------------------------------------------------------------

        async void Start()
        {
            var args = Environment.GetCommandLineArgs();
            var i = Array.IndexOf(args, "-drikrSmoke");
            if (i < 0) return;
            var shot = i + 1 < args.Length ? args[i + 1] : "drikr-smoke.png";
            try
            {
                await RunSmoke(shot);
                Debug.Log("DRIKR_SMOKE result=pass");
                Application.Quit(0);
            }
            catch (Exception e)
            {
                Debug.LogError("DRIKR_SMOKE result=fail " + e);
                Application.Quit(1);
            }
        }

        async Task RunSmoke(string screenshotPath)
        {
            _username = Environment.GetEnvironmentVariable("DRIKR_SMOKE_USER") ?? "trainee2";
            var pw = Environment.GetEnvironmentVariable("DRIKR_SMOKE_PASSWORD") ?? throw new Exception("DRIKR_SMOKE_PASSWORD not set");
            _api = new DrikrApi(_apiUrl, caCertPath: _caCertPath);
            if (await _api.Login(_username, pw)) throw new Exception("smoke user has MFA enabled; use an account without it");
            await LoadHome();
            var scenario = _practice.FirstOrDefault() ?? throw new Exception("no practice scenario available");
            await OpenSession(await _api.CreatePractice(scenario.Id));
            SetState(await _api.Transition(_state.Id, "start"));
            var deadline = Time.realtimeSinceStartup + 90f;
            while (_picture.Tracks.Values.Count(t => t.Position.HasValue) == 0)
            {
                if (Time.realtimeSinceStartup > deadline) throw new Exception("no positional track within 90 s");
                await Task.Delay(250); // Update() keeps polling the feed
            }
            await Task.Delay(8000); // let trails build up for the screenshot
            var first = _picture.Tracks.Values.First(t => t.Position.HasValue).Id;
            _selected.Add(first);
            SyncViews();
            await SubmitAction(TraineeAction.Classify(new[] { first }, "small_multirotor", "low"));
            await Task.Delay(1500);
            ScreenCapture.CaptureScreenshot(screenshotPath);
            await Task.Delay(1500);
            if (_views.Count == 0) throw new Exception("tracks were not rendered");
            if (_picture.GroundTruthEventsRejected != 0) throw new Exception("ground truth received");
            SetState(await _api.Transition(_state.Id, "complete"));
            await ShowResult();
            Debug.Log($"DRIKR_SMOKE tracks={_picture.Tracks.Count} rendered={_views.Count} result={_resultText?.Split('\n')[0]}");
        }

        // ------------------------------------------------------------------------
        // Scene construction (flat, unlit tactical display; no imported assets)
        // ------------------------------------------------------------------------

        static Material LoadMat(string name, Color color)
        {
            var baseMat = Resources.Load<Material>("DrikrMaterials/" + name);
            var m = baseMat != null ? new Material(baseMat) : new Material(Shader.Find("Unlit/Color"));
            m.color = color;
            return m;
        }

        void BuildScene()
        {
            _cam = Camera.main;
            if (_cam == null)
            {
                _cam = new GameObject("Main Camera").AddComponent<Camera>();
                _cam.tag = "MainCamera";
            }
            // Backdrop camera clears the whole window (including behind the control panel).
            var backdrop = _backdrop = new GameObject("Backdrop Camera").AddComponent<Camera>();
            backdrop.clearFlags = CameraClearFlags.SolidColor;
            backdrop.backgroundColor = Hex("#F6F5F1");
            backdrop.cullingMask = 0;
            backdrop.depth = _cam.depth - 1;
            _cam.clearFlags = CameraClearFlags.SolidColor;
            _cam.backgroundColor = Hex("#EEF0EE");
            _cam.farClipPlane = 5000f;
            _cam.fieldOfView = 45f;

            _matGround = LoadMat("Unlit", Hex("#DCE2D3"));
            _matRing = LoadMat("Unlit", Hex("#7C817D"));
            _matSite = LoadMat("Unlit", Hex("#1F4D3A"));
            _matTrail = LoadMat("Unlit", Hex("#7C817D"));

            _world = new GameObject("World").transform;
            var r = WorldMapping.AreaRadiusM * WorldMapping.Scale * 1.15f;
            var ground = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            ground.name = "Ground";
            ground.transform.SetParent(_world);
            ground.transform.localScale = new Vector3(r * 2, 0.05f, r * 2);
            ground.GetComponent<Renderer>().sharedMaterial = _matGround;
            Destroy(ground.GetComponent<Collider>());

            for (var km = 1; km <= 4; km++) MakeRing(km * 1000f * WorldMapping.Scale, 0.3f, _matRing, _world);

            var site = GameObject.CreatePrimitive(PrimitiveType.Cube);
            site.name = "Protected virtual site";
            site.transform.SetParent(_world);
            site.transform.localPosition = new Vector3(0, 4, 0);
            site.transform.localScale = new Vector3(14, 8, 14);
            site.GetComponent<Renderer>().sharedMaterial = _matSite;
            Destroy(site.GetComponent<Collider>());
            UpdateCamera();
        }

        static LineRenderer MakeRing(float radius, float y, Material mat, Transform parent)
        {
            var go = new GameObject($"Ring {radius}");
            go.transform.SetParent(parent);
            var lr = go.AddComponent<LineRenderer>();
            lr.sharedMaterial = mat;
            lr.loop = true;
            lr.useWorldSpace = false;
            lr.widthMultiplier = 1.2f;
            const int n = 128;
            lr.positionCount = n;
            for (var i = 0; i < n; i++)
            {
                var a = i * Mathf.PI * 2 / n;
                lr.SetPosition(i, new Vector3(Mathf.Cos(a) * radius, y, Mathf.Sin(a) * radius));
            }
            return lr;
        }

        void ApplyEnvironmentLook()
        {
            var env = _briefing?.Environment;
            if (env == null) return;
            var night = env.TimeOfDay == "night";
            var dusk = env.TimeOfDay == "dusk";
            _cam.backgroundColor = night ? Hex("#20262A") : dusk ? Hex("#E2DDD3") : Hex("#EEF0EE");
            var g = env.Terrain switch
            {
                "urban" => Hex("#DEDCD6"),
                "coastal" => Hex("#E2DDCB"),
                "industrial" => Hex("#DDD9CF"),
                _ => Hex("#DCE2D3"),
            };
            _matGround.color = night ? g * 0.28f : dusk ? g * 0.9f : g;
            _matRing.color = night ? Hex("#56636B") : Hex("#7C817D");
            _matSite.color = night ? Hex("#C9D3CD") : Hex("#1F4D3A");
        }

        TrackView ViewFor(string id)
        {
            if (_views.TryGetValue(id, out var v)) return v;
            v = new TrackView { Mat = LoadMat("Unlit", ClassColors["unclassified"]) };
            v.Marker = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            v.Marker.name = id; // raycast hit name identifies the track
            v.Marker.transform.SetParent(_world);
            v.Marker.transform.localScale = Vector3.one * 16f;
            v.Marker.GetComponent<Renderer>().sharedMaterial = v.Mat;
            v.Stalk = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            v.Stalk.transform.SetParent(_world);
            v.Stalk.GetComponent<Renderer>().sharedMaterial = v.Mat;
            Destroy(v.Stalk.GetComponent<Collider>());
            v.SelectRing = MakeRing(14f, 0.6f, _matSite, v.Marker.transform.parent).gameObject;
            var trailGo = new GameObject(id + " trail");
            trailGo.transform.SetParent(_world);
            v.Trail = trailGo.AddComponent<LineRenderer>();
            v.Trail.sharedMaterial = v.Mat;
            v.Trail.widthMultiplier = 1.5f;
            _views[id] = v;
            return v;
        }

        void SyncViews()
        {
            foreach (var t in _picture.Tracks.Values)
            {
                if (!t.Position.HasValue) continue;
                var v = ViewFor(t.Id);
                var p = t.Position.Value;
                var pos = WorldMapping.ToWorld(p.X, p.Y, p.Alt);
                var c = ClassColors.TryGetValue(t.Classification ?? "unclassified", out var cc) ? cc : ClassColors["unclassified"];
                v.Mat.color = t.Lost ? new Color(c.r, c.g, c.b) * 0.6f + Color.white * 0.4f : c;
                v.Marker.transform.localPosition = pos;
                v.Stalk.transform.localPosition = new Vector3(pos.x, pos.y / 2f, pos.z);
                v.Stalk.transform.localScale = new Vector3(1f, pos.y / 2f, 1f);
                v.SelectRing.transform.localPosition = new Vector3(pos.x, 0f, pos.z);
                v.SelectRing.SetActive(_selected.Contains(t.Id));
                v.Trail.positionCount = t.Trail.Count;
                for (var i = 0; i < t.Trail.Count; i++)
                    v.Trail.SetPosition(i, WorldMapping.ToWorld(t.Trail[i].X, t.Trail[i].Y, t.Trail[i].Alt));
            }
        }

        void ClearViews()
        {
            foreach (var v in _views.Values)
            {
                Destroy(v.Marker);
                Destroy(v.Stalk);
                Destroy(v.SelectRing);
                Destroy(v.Trail.gameObject);
            }
            _views.Clear();
        }

        void UpdateCamera()
        {
            if (VrActive) return; // the headset drives the camera
            // The 3D view occupies the area to the right of the 380 px control panel.
            var panel = Mathf.Clamp01(380f / Mathf.Max(1, UnityEngine.Screen.width));
            _cam.rect = new Rect(panel, 0f, 1f - panel, 1f);
            var rot = Quaternion.Euler(_pitch, _yaw, 0f);
            _cam.transform.position = rot * new Vector3(0, 0, -_distance);
            _cam.transform.LookAt(Vector3.zero);
        }

        // ------------------------------------------------------------------------
        // Frame loop: input, polling, rendering
        // ------------------------------------------------------------------------

        void Update()
        {
            if (VrActive) VrUpdate();
            else DesktopInput();

            if (_screen == Screen.Exercise && !_polling && Time.realtimeSinceStartup >= _nextPoll)
                _ = Poll();
        }

        void DesktopInput()
        {
            if (Input.GetMouseButton(1))
            {
                _yaw += Input.GetAxis("Mouse X") * 3f;
                _pitch = Mathf.Clamp(_pitch - Input.GetAxis("Mouse Y") * 3f, 10f, 85f);
            }
            var wheel = Input.mouseScrollDelta.y;
            if (Math.Abs(wheel) > 0.01f) _distance = Mathf.Clamp(_distance * (1f - wheel * 0.1f), 80f, 1200f);
            UpdateCamera();

            if (_screen == Screen.Exercise && Input.GetMouseButtonDown(0) && Input.mousePosition.x > 380)
            {
                if (Physics.Raycast(_cam.ScreenPointToRay(Input.mousePosition), out var hit, 5000f))
                    Toggle(hit.collider.gameObject.name, Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift));
            }
        }

        // ------------------------------------------------------------------------
        // VR (sand table). Same selection and decisions as the desktop; input differs only.
        // ------------------------------------------------------------------------

        void StartVr()
        {
            _vr = new VrSession();
            if (!_vr.TryStart())
            {
                _notice = $"VR not started: {_vr.FailureReason} Running on the desktop.";
                Debug.Log("DRIKR_VR " + _notice);
                return;
            }
            var area = WorldMapping.AreaRadiusM * WorldMapping.Scale * 1.15f;
            _world.localScale = Vector3.one * VrControls.TableScale(area);
            _world.position = new Vector3(0f, 0.85f, 1.2f); // a table at waist height in front of the trainee
            var rig = new GameObject("VR rig").transform;
            _cam.transform.SetParent(rig, false);
            _cam.rect = new Rect(0f, 0f, 1f, 1f);
            _cam.nearClipPlane = 0.02f;
            _cam.farClipPlane = 50f;
            if (_backdrop != null) _backdrop.enabled = false;
            _vrc = new VrControls(Vocabulary.Classifications);
            _vrText = new GameObject("VR status").AddComponent<TextMesh>();
            _vrText.transform.position = new Vector3(0f, 1.55f, 1.9f);
            _vrText.characterSize = 0.02f;
            _vrText.fontSize = 48;
            _vrText.anchor = TextAnchor.UpperCenter;
            _vrText.color = Hex("#1F2421");
            _vrRay = new GameObject("VR pointer").AddComponent<LineRenderer>();
            _vrRay.sharedMaterial = _matRing;
            _vrRay.widthMultiplier = 0.004f;
            _vrRay.positionCount = 2;
            Debug.Log("DRIKR_VR started; devices: " + VrSession.DescribeDevices());
        }

        void VrUpdate()
        {
            if (VrSession.Pose(XRNode.CenterEye, out var hp, out var hr))
            {
                _cam.transform.localPosition = hp;
                _cam.transform.localRotation = hr;
            }
            _vrPointed = null;
            if (VrSession.Pose(XRNode.RightHand, out var p, out var r))
            {
                var dir = r * Vector3.forward;
                var end = p + dir * 3f;
                if (_screen == Screen.Exercise && Physics.Raycast(p, dir, out var hit, 3f)
                    && _picture.Tracks.ContainsKey(hit.collider.gameObject.name))
                {
                    _vrPointed = hit.collider.gameObject.name;
                    end = hit.point;
                }
                _vrRay.SetPosition(0, p);
                _vrRay.SetPosition(1, end);
                _vrRay.enabled = true;
            }
            else _vrRay.enabled = false;

            var (trigger, primary, secondary) = VrSession.Buttons(XRNode.RightHand);
            var (select, next, submit) = _vrc.Edges(trigger, primary, secondary);
            if (select && _vrPointed != null) Toggle(_vrPointed, additive: true);
            if (next) _vrc.NextClassification();
            var canAct = !_busy && _state != null && _state.Status == "running" && _selected.Count > 0;
            if (submit && canAct)
            {
                var action = TraineeAction.Classify(_selected, _vrc.Classification, Vocabulary.Confidences[_confIndex]);
                Run(() => SubmitAction(action));
            }
            var (leftTrigger, leftPrimary, _) = VrSession.Buttons(XRNode.LeftHand);
            var (nextResponse, sendResponse) = _vrc.LeftEdges(leftTrigger, leftPrimary);
            if (nextResponse) _vrc.NextResponse();
            if (sendResponse && canAct)
            {
                var action = TraineeAction.Respond(_selected, _vrc.Response);
                Run(() => SubmitAction(action));
            }
            _vrText.text = _vrc.Status(_selected, Vocabulary.Label, _vrPointed, _error ?? _notice);
        }

        void Toggle(string id, bool additive)
        {
            if (!_picture.Tracks.ContainsKey(id)) return;
            if (!additive)
            {
                var only = _selected.Count == 1 && _selected.Contains(id);
                _selected.Clear();
                if (!only) _selected.Add(id);
            }
            else if (!_selected.Remove(id)) _selected.Add(id);
            SyncViews();
        }

        async Task Poll()
        {
            if (_state == null) return;
            _polling = true;
            try
            {
                var feed = await _api.Feed(_state.Id, _sinceMs);
                _picture.Apply(feed.Events);
                _sinceMs = feed.State.SimTimeMs; // inclusive lower bound; duplicates removed by event id
                SetState(feed.State);
                _connectionRetrying = false;
                SyncViews();
                if (_state.Status == "completed") await ShowResult();
            }
            catch (DrikrApiException e)
            {
                if (e.Retryable || e.Status == 429) _connectionRetrying = true;
                else _error = e.Message;
            }
            finally
            {
                _polling = false;
                _nextPoll = Time.realtimeSinceStartup + (_state?.Status == "running" ? PollIntervalRunning : PollIntervalIdle);
            }
        }

        void SetState(SessionState s)
        {
            _state = s;
            if (s.Briefing != null && _briefing == null)
            {
                _briefing = s.Briefing;
                ApplyEnvironmentLook();
            }
            _syncRealtime = Time.realtimeSinceStartup;
        }

        int DisplayMs()
        {
            if (_state == null) return 0;
            if (_state.Status != "running") return _state.SimTimeMs;
            var est = _state.SimTimeMs + (int)((Time.realtimeSinceStartup - _syncRealtime) * 1000);
            return Math.Min(Math.Min(est, _state.SimTimeMs + 2000), _state.DurationMs);
        }

        async void Run(Func<Task> op)
        {
            if (_busy) return;
            _busy = true;
            _error = null;
            try { await op(); }
            catch (DrikrApiException e) { _error = e.Message; }
            catch (Exception e) { _error = e.Message; Debug.LogException(e); }
            finally { _busy = false; }
        }

        async Task OpenSession(SessionState created)
        {
            ClearViews();
            _picture = new TrackPicture();
            _selected.Clear();
            _sinceMs = 0;
            _briefing = null;
            var full = await _api.Session(created.Id);
            SetState(full);
            _screen = Screen.Exercise;
            _nextPoll = 0;
        }

        async Task LoadHome()
        {
            _assignments = (await _api.Assignments()).Items;
            _practice = (await _api.PracticeScenarios()).Items.Where(s => s.SelfGuided).ToList();
            _screen = Screen.Home;
        }

        async Task ShowResult()
        {
            var r = await _api.Result(_state.Id);
            var overall = r["overall"]?.Type == Newtonsoft.Json.Linq.JTokenType.Null ? "insufficient data" : $"{(float)r["overall"]:0.0}%";
            var passed = r["passed"]?.Type == Newtonsoft.Json.Linq.JTokenType.Boolean && (bool)r["passed"] ? "Passed" : "Not passed";
            _resultText = $"Overall {overall} ({passed}). Pass mark {(float)r["pass_mark"]:0}%.\n" +
                          "Open the web application for the full after-action review.";
            _screen = Screen.Result;
        }

        // ------------------------------------------------------------------------
        // IMGUI panel (left side). Keyboard: Tab moves between controls.
        // ------------------------------------------------------------------------

        GUISkin _skin;
        GUIStyle _plate;

        static Texture2D Tex(string hex)
        {
            var t = new Texture2D(1, 1) { hideFlags = HideFlags.HideAndDontSave };
            t.SetPixel(0, 0, Hex(hex));
            t.Apply();
            return t;
        }

        /// <summary>Flat skin using the web client's interface design tokens (docs/design/brand-and-design-system.md).</summary>
        void Styles()
        {
            if (_skin != null) return;
            var ink = Hex("#1B1F1D");
            var muted = Hex("#545A56");
            _skin = Instantiate(GUI.skin);
            _skin.box.normal.background = Tex("#FFFFFF");
            _skin.box.padding = new RectOffset(14, 14, 12, 12);
            _skin.label.normal.textColor = ink;
            foreach (var st in new[] { _skin.button })
            {
                st.normal.background = Tex("#EFEEE9");
                st.hover.background = Tex("#E3ECE6");
                st.active.background = Tex("#1F4D3A");
                st.onNormal.background = Tex("#1F4D3A");
                st.onHover.background = Tex("#183D2E");
                st.onActive.background = Tex("#183D2E");
                st.focused.background = Tex("#E3ECE6");
                st.normal.textColor = st.hover.textColor = st.focused.textColor = ink;
                st.active.textColor = st.onNormal.textColor = st.onHover.textColor = st.onActive.textColor = Color.white;
                st.fontSize = 12;
                st.padding = new RectOffset(8, 8, 6, 6);
                st.border = new RectOffset(0, 0, 0, 0);
            }
            _skin.textField.normal.background = Tex("#F6F5F1");
            _skin.textField.focused.background = Tex("#E3ECE6");
            _skin.textField.hover.background = Tex("#F6F5F1");
            _skin.textField.normal.textColor = _skin.textField.focused.textColor = _skin.textField.hover.textColor = ink;
            _skin.textField.padding = new RectOffset(6, 6, 5, 5);
            _skin.toggle.normal.textColor = _skin.toggle.onNormal.textColor = ink;
            _skin.toggle.hover.textColor = _skin.toggle.onHover.textColor = Hex("#1F4D3A");
            _skin.verticalScrollbar.normal.background = Tex("#EFEEE9");
            _skin.verticalScrollbarThumb.normal.background = Tex("#C6C2B8");

            _label = new GUIStyle(_skin.label) { wordWrap = true, fontSize = 13 };
            _small = new GUIStyle(_label) { fontSize = 11 };
            _small.normal.textColor = muted;
            _heading = new GUIStyle(_label) { fontSize = 16, fontStyle = FontStyle.Bold };
            _tag = new GUIStyle(_label) { fontSize = 11, fontStyle = FontStyle.Bold };
            _plate = new GUIStyle(_tag) { padding = new RectOffset(5, 5, 2, 2), wordWrap = false };
            _plate.normal.background = Tex("#FFFFFF");
            _plate.normal.textColor = ink;
        }

        // --- accessibility -------------------------------------------------------------
        // Every panel control goes through these wrappers: they draw exactly as GUILayout does and
        // register the control with PanelAccessibility, which publishes it to the screen reader.
        readonly PanelAccessibility _a11y = new PanelAccessibility();
        Screen _a11yScreen = (Screen)(-1);
        string _announcedError, _announcedNotice, _announcedStatus;
        readonly HashSet<string> _announcedTracks = new HashSet<string>();

        /// <summary>Accessibility items published in the last frame (used by tests and diagnostics).</summary>
        public IReadOnlyList<A11yItem> AccessibleItems => _a11y.Published;

        static bool Repainting => Event.current.type == EventType.Repaint;

        void Register(A11yRole role, string key, string label, string value = null, bool selected = false, string hint = null)
        {
            if (!Repainting) return;
            _a11y.Add(new A11yItem
            {
                Key = key,
                Role = role,
                Label = PanelAccessibility.Speakable(label),
                Value = value,
                Hint = hint,
                Enabled = GUI.enabled,
                Selected = selected,
                ScreenRect = GUIUtility.GUIToScreenRect(GUILayoutUtility.GetLastRect()),
            });
        }

        void Heading(string text)
        {
            var key = _a11y.KeyFor(A11yRole.Header, text);
            GUILayout.Label(text, _heading);
            Register(A11yRole.Header, key, text);
        }

        void Text(string text, GUIStyle style, params GUILayoutOption[] options)
        {
            var key = _a11y.KeyFor(A11yRole.Text, text);
            GUILayout.Label(text, style, options);
            Register(A11yRole.Text, key, text);
        }

        bool Button(string label, string hint = null)
        {
            var key = _a11y.KeyFor(A11yRole.Button, label);
            var clicked = GUILayout.Button(label);
            Register(A11yRole.Button, key, label, hint: hint);
            if (_a11y.ConsumeInvoke(key))
            {
                if (GUI.enabled) clicked = true;
                else PanelAccessibility.Announce(label + " is not available now.");
            }
            return clicked;
        }

        /// <summary>A checkbox; <paramref name="id"/> keeps the screen-reader node stable while the text changes.</summary>
        bool Toggle(bool value, string id, string label, GUIStyle style)
        {
            var key = _a11y.KeyFor(A11yRole.Toggle, id);
            var now = GUILayout.Toggle(value, label, style);
            Register(A11yRole.Toggle, key, label, now ? "checked" : "not checked", now);
            if (_a11y.ConsumeInvoke(key) && GUI.enabled) now = !value;
            return now;
        }

        /// <summary>One choice of a single-choice group, drawn as a toggle button (replaces SelectionGrid/Toolbar).</summary>
        bool Option(bool selected, string group, string label, int perRow)
        {
            var key = _a11y.KeyFor(A11yRole.Toggle, group + ": " + label);
            var width = (324f - 4f * (perRow - 1)) / perRow; // equal cells, like the SelectionGrid it replaces
            var pressed = GUILayout.Toggle(selected, label, GUI.skin.button, GUILayout.Width(width)) && !selected;
            Register(A11yRole.Toggle, key, $"{group}: {label}", selected ? "selected" : "not selected", selected);
            if (_a11y.ConsumeInvoke(key) && GUI.enabled) pressed = true;
            return pressed;
        }

        string Field(string label, string value, int maxLength, bool password = false)
        {
            GUILayout.Label(label, _small); // read as the field's name, not as separate text
            var key = _a11y.KeyFor(A11yRole.TextField, label);
            GUI.SetNextControlName(key);
            var now = password ? GUILayout.PasswordField(value, '*', maxLength) : GUILayout.TextField(value, maxLength);
            Register(A11yRole.TextField, key, label, password ? $"{now.Length} characters entered" : now);
            if (_a11y.PendingFocus == key || _a11y.ConsumeInvoke(key))
            {
                GUI.FocusControl(key);
                _a11y.PendingFocus = null;
            }
            return now;
        }

        void AnnounceChanges()
        {
            if (_screen != _a11yScreen)
            {
                _a11yScreen = _screen;
                _a11y.ScreenChanged();
            }
            if (_error != _announcedError)
            {
                _announcedError = _error;
                if (!string.IsNullOrEmpty(_error)) PanelAccessibility.Announce("Error: " + _error);
            }
            if (_notice != _announcedNotice)
            {
                _announcedNotice = _notice;
                PanelAccessibility.Announce(_notice);
            }
            if (_screen != Screen.Exercise || _state == null)
            {
                _announcedTracks.Clear();
                _announcedStatus = null;
                return;
            }
            if (_state.Status != _announcedStatus)
            {
                _announcedStatus = _state.Status;
                PanelAccessibility.Announce("Exercise " + Vocabulary.Label(_state.Status));
            }
            var fresh = _picture.Tracks.Keys.Where(id => _announcedTracks.Add(id)).OrderBy(id => id).ToList();
            if (fresh.Count > 0) PanelAccessibility.Announce("New track " + string.Join(", ", fresh));
        }

        void OnGUI()
        {
            Styles();
            GUI.skin = _skin;
            _a11y.BeginFrame();
            if (Repainting && PanelAccessibility.Active) AnnounceChanges();
            GUILayout.BeginArea(new Rect(10, 10, 360, UnityEngine.Screen.height - 20), GUI.skin.box);
            if (_logo != null)
            {
                const float h = 20f;
                GUILayout.Label(new GUIContent(_logo, "Drikr Systems"), GUIStyle.none,
                    GUILayout.Height(h), GUILayout.Width(h * _logo.width / _logo.height));
                Text("Drikr Systems training simulator (Unity client)", _small);
            }
            else
            {
                Text("Drikr Systems · Training simulator (Unity client)", _small);
            }
            GUILayout.Space(4);
            _scroll = GUILayout.BeginScrollView(_scroll);
            switch (_screen)
            {
                case Screen.Login: DrawLogin(); break;
                case Screen.Home: DrawHome(); break;
                case Screen.Exercise: DrawExercise(); break;
                case Screen.Result: DrawResult(); break;
            }
            if (!string.IsNullOrEmpty(_error)) Text("Error: " + _error, _tag);
            if (!string.IsNullOrEmpty(_notice)) Text(_notice, _small);
            GUILayout.EndScrollView();
            GUILayout.EndArea();
            if (_screen == Screen.Exercise) DrawTrackLabels(); // visual duplicates of the track list
            if (Repainting) _a11y.EndFrame();
        }

        void DrawLogin()
        {
            if (_api != null && _api.MfaPending)
            {
                DrawMfaStep();
                return;
            }
            Heading("Sign in");
            _apiUrl = Field("Training server API", _apiUrl, 512);
            _username = Field("Username", _username, 64);
            _password = Field("Password", _password, 256, password: true);
            GUI.enabled = !_busy && _username.Length > 0 && _password.Length > 0;
            if (Button(_busy ? "Signing in" : "Sign in"))
                Run(async () =>
                {
                    _api?.Dispose();
                    _api = new DrikrApi(_apiUrl, caCertPath: _caCertPath);
                    var needsCode = await _api.Login(_username.Trim().ToLowerInvariant(), _password);
                    _password = "";
                    if (!needsCode) await LoadHome();
                    else _notice = "Enter your verification code.";
                });
            GUI.enabled = true;
            GUILayout.Space(6);
            Text("Authorised training use only. All tracks, sensor readings and events are synthetic.", _small);
        }

        void DrawMfaStep()
        {
            Heading("Verification code");
            Text("Enter the 6-digit code from your authenticator app, or a recovery code.", _small);
            _mfaCode = Field("Code", _mfaCode, 16);
            GUI.enabled = !_busy && _mfaCode.Trim().Length >= 6;
            if (Button(_busy ? "Verifying" : "Verify and sign in"))
                Run(async () =>
                {
                    var code = _mfaCode.Trim();
                    _mfaCode = "";
                    await _api.VerifyMfa(code);
                    _notice = null;
                    await LoadHome();
                });
            GUI.enabled = !_busy;
            if (Button("Use a different account"))
            {
                _api.Dispose();
                _api = null;
                _mfaCode = "";
                _error = null;
                _notice = null;
            }
            GUI.enabled = true;
        }

        void DrawHome()
        {
            Heading("My exercises");
            if (_assignments.Count == 0) Text("No exercises assigned.", _small);
            foreach (var a in _assignments)
            {
                GUILayout.BeginHorizontal();
                Text($"{a.Title}\n{a.Scenario?.Name} · {Vocabulary.Label(a.Progress?.State)}", _small, GUILayout.Width(230));
                var active = a.Progress?.ActiveSessionId;
                GUI.enabled = !_busy && (active != null || (a.Progress?.AttemptsRemaining ?? 0) > 0);
                if (Button(active != null ? "Resume" : "Launch", a.Title))
                    Run(async () => await OpenSession(active != null ? await _api.Session(active) : await _api.CreateAssigned(a.Id)));
                GUI.enabled = true;
                GUILayout.EndHorizontal();
            }
            GUILayout.Space(8);
            Heading("Practice library");
            foreach (var s in _practice)
            {
                GUILayout.BeginHorizontal();
                Text(s.Name, _small, GUILayout.Width(230));
                GUI.enabled = !_busy;
                if (Button("Practise", s.Name))
                    Run(async () =>
                    {
                        try { await OpenSession(await _api.CreatePractice(s.Id)); }
                        catch (DrikrApiException e) when (e.Code == "session_in_progress")
                        {
                            _notice = "A practice attempt is already in progress; finish it from the web application.";
                        }
                    });
                GUI.enabled = true;
                GUILayout.EndHorizontal();
            }
            GUILayout.Space(8);
            if (Button("Refresh")) Run(LoadHome);
            if (Button("Sign out")) Run(async () => { await _api.Logout(); _screen = Screen.Login; });
        }

        static string Clock(int ms)
        {
            var s = Math.Max(0, ms / 1000);
            return $"{s / 60:00}:{s % 60:00}";
        }

        void DrawExercise()
        {
            if (_state == null) return;
            Heading(_state.Scenario?.Name ?? "Exercise");
            // The clock changes every second: one stable node whose value is updated, not a new node.
            var clockKey = _a11y.KeyFor(A11yRole.Text, "exercise status");
            var status = $"{Clock(DisplayMs())} / {Clock(_state.DurationMs)} · {Vocabulary.Label(_state.Status)} · difficulty {_state.DifficultyLevel}{(_state.Seed.HasValue ? $" · seed {_state.Seed}" : "")}";
            GUILayout.Label(status, _label);
            Register(A11yRole.Text, clockKey, "Exercise status: " + status, status);
            Text("Synthetic training data. Not real sensor measurements.", _small);
            if (_connectionRetrying) Text("Connection interrupted; retrying. The exercise pauses itself after about 15 s.", _tag);
            if (_state.Status == "paused" && _state.PauseReason == "connection_lost") Text("Paused after a lost connection. Resume when ready.", _tag);

            GUILayout.BeginHorizontal();
            GUI.enabled = !_busy;
            if (_state.Status == "created" && Button("Start exercise")) Run(async () => SetState(await _api.Transition(_state.Id, "start")));
            if (_state.Status == "running" && _state.AllowPause && Button("Pause")) Run(async () => SetState(await _api.Transition(_state.Id, "pause")));
            if (_state.Status == "paused" && Button("Resume")) Run(async () => SetState(await _api.Transition(_state.Id, "resume")));
            if ((_state.Status == "running" || _state.Status == "paused") && Button("Finish"))
                Run(async () => { SetState(await _api.Transition(_state.Id, "complete")); await ShowResult(); });
            GUI.enabled = true;
            GUILayout.EndHorizontal();

            if (_state.Status == "created" && _briefing != null) Text(_briefing.Text, _small);

            GUILayout.Space(6);
            Text($"Tracks ({_picture.Tracks.Count}). Select them here or click in the view (Shift adds). Right-drag to orbit, scroll to zoom.", _small);
            foreach (var t in _picture.Tracks.Values.OrderBy(x => x.Id))
            {
                var sensors = string.Join("·", t.Sensors.OrderBy(x => x).Select(x => x == "electro_optical" ? "O" : x == "radar" ? "R" : "RF"));
                var hint = t.PendingConfirmation ? "confirmation pending" : t.ClassHint != null ? $"{Vocabulary.Label(t.ClassHint)} ({t.ClassHintQuality:0.00})" : "no hint";
                var mine = t.Classification != null ? $"{Vocabulary.Label(t.Classification)}/{t.Confidence}" : "not classified";
                var sel = _selected.Contains(t.Id);
                var now = Toggle(sel, "track " + t.Id, $"{t.Id}{(t.Lost ? " (lost)" : "")} {sensors} · {hint}{(t.Beacon ? " · beacon" : "")}\n   mine: {mine} · {Vocabulary.Label(t.Response)}", _small);
                if (now != sel) { if (now) _selected.Add(t.Id); else _selected.Remove(t.Id); SyncViews(); }
            }

            GUILayout.Space(6);
            Text("1. Classify", _tag);
            var classes = Vocabulary.Classifications;
            for (var i = 0; i < classes.Length; i += 2)
            {
                GUILayout.BeginHorizontal();
                for (var j = i; j < Math.Min(i + 2, classes.Length); j++)
                    if (Option(_classIndex == j, "Classification", Vocabulary.Label(classes[j]), 2)) _classIndex = j;
                GUILayout.EndHorizontal();
            }
            GUILayout.BeginHorizontal();
            var levels = new[] { "Low", "Medium", "High" };
            for (var j = 0; j < levels.Length; j++)
                if (Option(_confIndex == j, "Confidence", levels[j], 3)) _confIndex = j;
            GUILayout.EndHorizontal();
            var canAct = !_busy && _state.Status == "running" && _selected.Count > 0;
            GUI.enabled = canAct && _classIndex >= 0;
            if (Button("Submit classification", "Applies to the selected tracks"))
            {
                var action = TraineeAction.Classify(_selected, Vocabulary.Classifications[_classIndex], Vocabulary.Confidences[_confIndex]);
                Run(() => SubmitAction(action));
            }
            GUI.enabled = true;
            Text("2. Training response", _tag);
            GUI.enabled = canAct;
            foreach (var r in Vocabulary.Responses)
                if (Button(Vocabulary.Label(r), "Applies to the selected tracks"))
                {
                    var action = TraineeAction.Respond(_selected, r);
                    Run(() => SubmitAction(action));
                }
            GUI.enabled = true;

            GUILayout.Space(6);
            Text("Simulated sensor status", _tag);
            foreach (var kv in _picture.SensorStatus.OrderBy(k => k.Key)) Text($"{Vocabulary.Label(kv.Key)}: {kv.Value}", _small);
            if (_picture.VisibilityKm.HasValue) Text($"Visibility {_picture.VisibilityKm:0.0} km", _small);
            foreach (var m in _picture.Messages.AsEnumerable().Reverse().Take(4)) Text(m, _small);
        }

        async Task SubmitAction(TraineeAction action)
        {
            var res = await _api.Submit(_state.Id, action);
            _picture.Apply(new[] { res.Event });
            SetState(res.State);
            SyncViews();
            _notice = res.Duplicate ? "Already recorded." : "Decision recorded.";
        }

        void DrawResult()
        {
            Heading("Exercise complete");
            Text(_resultText ?? "", _label);
            if (Button("Back to exercises")) Run(async () => { ClearViews(); await LoadHome(); });
        }

        void DrawTrackLabels()
        {
            foreach (var t in _picture.Tracks.Values)
            {
                if (!t.Position.HasValue || !_views.TryGetValue(t.Id, out var v)) continue;
                var sp = _cam.WorldToScreenPoint(v.Marker.transform.position + Vector3.up * 12f);
                if (sp.z <= 0) continue;
                var size = _plate.CalcSize(new GUIContent(t.Id));
                GUI.Label(new Rect(sp.x + 10, UnityEngine.Screen.height - sp.y - 10, size.x, size.y), t.Id, _plate);
            }
        }
    }
}
