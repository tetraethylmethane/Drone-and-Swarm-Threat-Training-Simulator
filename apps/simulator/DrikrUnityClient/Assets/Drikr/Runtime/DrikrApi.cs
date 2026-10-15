// HTTP client for the simulation adapter protocol (bearer-token mode, no cookies or CSRF).
// The client is presentation-only: it never computes simulation state.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Security;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Drikr
{
    public sealed class DrikrApiException : Exception
    {
        public readonly int Status;
        public readonly string Code;

        public DrikrApiException(int status, string code, string message) : base(message)
        {
            Status = status;
            Code = code;
        }

        /// <summary>True when the outcome is unknown (network failure or server unavailable) and a retry is safe.</summary>
        public bool Retryable => Status == 0 || Status >= 500;
    }

    public sealed class DrikrApi : IDisposable
    {
        readonly HttpClient _http;
        string _mfaToken;
        public string BaseUrl { get; }
        public bool SignedIn => _http.DefaultRequestHeaders.Authorization != null;
        /// <summary>The password was accepted and a verification code is now needed.</summary>
        public bool MfaPending => _mfaToken != null;

        /// <param name="caCertPath">Optional PEM or DER file of the training network's private CA
        /// (scripts/generate-tls-cert.sh). Server certificates issued by it are trusted in addition to
        /// the operating system's roots. Host name checks always apply.</param>
        public DrikrApi(string baseUrl, HttpMessageHandler handler = null, string caCertPath = null)
        {
            BaseUrl = baseUrl.TrimEnd('/');
            if (handler == null && !string.IsNullOrEmpty(caCertPath))
            {
                var ca = LoadCertificate(caCertPath);
                handler = new HttpClientHandler
                {
                    ServerCertificateCustomValidationCallback = (_, cert, __, errors) => ValidateServer(ca, cert, errors),
                };
            }
            _http = handler == null ? new HttpClient() : new HttpClient(handler);
            _http.Timeout = TimeSpan.FromSeconds(30);
            _http.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        }

        async Task<T> Send<T>(HttpMethod method, string path, object body = null)
        {
            var req = new HttpRequestMessage(method, BaseUrl + path);
            if (body != null)
                req.Content = new StringContent(JsonConvert.SerializeObject(body), Encoding.UTF8, "application/json");
            HttpResponseMessage res;
            try
            {
                res = await _http.SendAsync(req).ConfigureAwait(true);
            }
            catch (Exception e) when (e is HttpRequestException || e is TaskCanceledException)
            {
                throw new DrikrApiException(0, "network_error", "The training server cannot be reached.");
            }
            var text = await res.Content.ReadAsStringAsync().ConfigureAwait(true);
            if (!res.IsSuccessStatusCode)
            {
                string code = "http_error", message = $"Request failed ({(int)res.StatusCode})";
                try
                {
                    var err = JObject.Parse(text)["error"];
                    code = (string)err?["code"] ?? code;
                    message = (string)err?["message"] ?? message;
                }
                catch (JsonException) { }
                throw new DrikrApiException((int)res.StatusCode, code, message);
            }
            return JsonConvert.DeserializeObject<T>(text);
        }

        /// <summary>Password step. Returns true when a verification code is needed (call <see cref="VerifyMfa"/>).</summary>
        public async Task<bool> Login(string username, string password)
        {
            _mfaToken = null;
            var res = await Send<JObject>(HttpMethod.Post, "/auth/login",
                new { username, password, mode = "token" });
            if ((bool?)res["mfa_required"] == true)
            {
                _mfaToken = (string)res["mfa_token"];
                return true;
            }
            UseToken((string)res["access_token"]);
            return false;
        }

        /// <summary>Second step: a 6-digit authenticator code or a recovery code.</summary>
        public async Task VerifyMfa(string code)
        {
            if (_mfaToken == null) throw new InvalidOperationException("No sign-in is waiting for a code");
            try
            {
                var res = await Send<JObject>(HttpMethod.Post, "/auth/mfa/verify", new { mfa_token = _mfaToken, code });
                _mfaToken = null;
                UseToken((string)res["access_token"]);
            }
            catch (DrikrApiException e) when (e.Code != "mfa_code_invalid")
            {
                _mfaToken = null; // expired or exhausted: the password step must be repeated
                throw;
            }
        }

        void UseToken(string token) =>
            _http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);

        public static X509Certificate2 LoadCertificate(string path)
        {
            var text = File.ReadAllText(path);
            const string begin = "-----BEGIN CERTIFICATE-----", end = "-----END CERTIFICATE-----";
            var i = text.IndexOf(begin, StringComparison.Ordinal);
            if (i < 0) return new X509Certificate2(File.ReadAllBytes(path)); // DER
            var j = text.IndexOf(end, i, StringComparison.Ordinal);
            var b64 = text.Substring(i + begin.Length, j - i - begin.Length);
            return new X509Certificate2(Convert.FromBase64String(string.Concat(b64.Where(c => !char.IsWhiteSpace(c)))));
        }

        /// <summary>
        /// Accept a server certificate that the system trusts, or one that chains to the pinned CA.
        /// Name mismatches and missing certificates are never accepted.
        /// </summary>
        public static bool ValidateServer(X509Certificate2 pinnedCa, X509Certificate cert, SslPolicyErrors errors)
        {
            if (errors == SslPolicyErrors.None) return true;
            if ((errors & ~SslPolicyErrors.RemoteCertificateChainErrors) != 0) return false;
            if (pinnedCa == null || cert == null) return false;
            using (var leaf = new X509Certificate2(cert))
            using (var chain = new X509Chain())
            {
                chain.ChainPolicy.RevocationMode = X509RevocationMode.NoCheck; // offline private CA has no CRL
                chain.ChainPolicy.VerificationFlags = X509VerificationFlags.AllowUnknownCertificateAuthority;
                chain.ChainPolicy.ExtraStore.Add(pinnedCa);
                if (!chain.Build(leaf) || chain.ChainElements.Count < 2) return false;
                var root = chain.ChainElements[chain.ChainElements.Count - 1].Certificate;
                return root.RawData.SequenceEqual(pinnedCa.RawData);
            }
        }

        public async Task Logout()
        {
            try { await Send<JObject>(HttpMethod.Post, "/auth/logout", new { }); }
            finally { _http.DefaultRequestHeaders.Authorization = null; }
        }

        public Task<Page<Assignment>> Assignments() => Send<Page<Assignment>>(HttpMethod.Get, "/assignments?limit=100");
        public Task<ItemList<ScenarioSummary>> PracticeScenarios() => Send<ItemList<ScenarioSummary>>(HttpMethod.Get, "/scenarios");
        public Task<SessionState> Session(string id) => Send<SessionState>(HttpMethod.Get, $"/sessions/{id}");

        public Task<SessionState> CreateAssigned(string assignmentId) =>
            Send<SessionState>(HttpMethod.Post, "/sessions", new { assignment_id = assignmentId, selection = new { } });

        public Task<SessionState> CreatePractice(string scenarioId) =>
            Send<SessionState>(HttpMethod.Post, "/sessions", new { scenario_id = scenarioId, selection = new { } });

        public Task<SessionState> Transition(string id, string op) => Send<SessionState>(HttpMethod.Post, $"/sessions/{id}/{op}", new { });

        public Task<FeedResponse> Feed(string id, int sinceMs) => Send<FeedResponse>(HttpMethod.Get, $"/sessions/{id}/feed?since_ms={sinceMs}");

        public Task<JObject> Result(string id) => Send<JObject>(HttpMethod.Get, $"/sessions/{id}/result");

        /// <summary>Submit with retries on unknown outcome; the same client_action_id makes retries idempotent.</summary>
        public async Task<ActionResponse> Submit(string sessionId, TraineeAction action, int attempts = 3)
        {
            for (var i = 0; ; i++)
            {
                try
                {
                    return await Send<ActionResponse>(HttpMethod.Post, $"/sessions/{sessionId}/actions", action);
                }
                catch (DrikrApiException e) when (e.Retryable && i < attempts - 1)
                {
                    await Task.Delay(500 * (i + 1));
                }
            }
        }

        public void Dispose() => _http.Dispose();
    }
}
