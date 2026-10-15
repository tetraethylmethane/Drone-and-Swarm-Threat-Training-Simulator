// Two-step sign-in and pinned-CA certificate validation in the Unity client.
// The certificate tests run when DRIKR_TEST_TLS_DIR points at the output of scripts/generate-tls-cert.sh;
// the live HTTPS test also needs DRIKR_LIVE_HTTPS_API (e.g. https://localhost:8443/api/v1) and DRIKR_LIVE_PASSWORD.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Security;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine.TestTools;

namespace Drikr.Tests
{
    public class SecurityTests
    {
        sealed class FakeServer : HttpMessageHandler
        {
            public readonly List<(string Path, JObject Body, string Auth)> Calls = new List<(string, JObject, string)>();
            public Func<string, JObject, (int, object)> Respond;

            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage req, CancellationToken ct)
            {
                var body = req.Content == null ? new JObject() : JObject.Parse(await req.Content.ReadAsStringAsync());
                var path = req.RequestUri.AbsolutePath.Replace("/api/v1", "");
                Calls.Add((path, body, req.Headers.Authorization?.ToString()));
                var (status, payload) = Respond(path, body);
                return new HttpResponseMessage((HttpStatusCode)status)
                {
                    Content = new StringContent(JObject.FromObject(payload).ToString(), Encoding.UTF8, "application/json"),
                };
            }
        }

        static IEnumerator Await(Task t)
        {
            while (!t.IsCompleted) yield return null;
            if (t.IsFaulted) throw t.Exception!.GetBaseException();
        }

        // Awaitable, so the editor's main-thread synchronisation context is never blocked.
        static async Task<DrikrApiException> Throws(Func<Task> op)
        {
            try { await op(); }
            catch (DrikrApiException e) { return e; }
            Assert.Fail("expected a DrikrApiException");
            return null;
        }

        static object Error(string code) => new { error = new { code, message = code } };

        [UnityTest]
        public IEnumerator LoginWithVerificationCode()
        {
            var server = new FakeServer
            {
                Respond = (path, body) => path switch
                {
                    "/auth/login" => (200, new { mfa_required = true, mfa_token = "challenge-1", expires_at = "x" }),
                    "/auth/mfa/verify" when (string)body["code"] == "123456" => (200, new { mfa_required = false, access_token = "tok-1" }),
                    "/auth/mfa/verify" => (401, Error("mfa_code_invalid")),
                    _ => (200, new { items = new object[0], total = 0, limit = 100, offset = 0 }),
                },
            };
            yield return Await(Flow(server));
        }

        static async Task Flow(FakeServer server)
        {
            using var api = new DrikrApi("http://drikr.test/api/v1", server);
            Assert.IsTrue(await api.Login("trainee1", "pw"));
            Assert.IsTrue(api.MfaPending);
            Assert.IsFalse(api.SignedIn);

            var wrong = await Throws(() => api.VerifyMfa("000000"));
            Assert.AreEqual("mfa_code_invalid", wrong.Code);
            Assert.IsTrue(api.MfaPending, "a wrong code keeps the challenge");

            await api.VerifyMfa("123456");
            Assert.IsFalse(api.MfaPending);
            Assert.IsTrue(api.SignedIn);
            await api.Assignments();
            Assert.AreEqual("Bearer tok-1", server.Calls[server.Calls.Count - 1].Auth);
            Assert.AreEqual("challenge-1", (string)server.Calls[2].Body["mfa_token"]);
        }

        [UnityTest]
        public IEnumerator ExpiredChallengeRequiresPasswordAgain()
        {
            var server = new FakeServer
            {
                Respond = (path, _) => path == "/auth/login"
                    ? (200, (object)new { mfa_required = true, mfa_token = "challenge-1", expires_at = "x" })
                    : (401, Error("mfa_challenge_invalid")),
            };
            yield return Await(Expired(server));
        }

        static async Task Expired(FakeServer server)
        {
            using var api = new DrikrApi("http://drikr.test/api/v1", server);
            await api.Login("trainee1", "pw");
            var e = await Throws(() => api.VerifyMfa("123456"));
            Assert.AreEqual("mfa_challenge_invalid", e.Code);
            Assert.IsFalse(api.MfaPending);
        }

        [UnityTest]
        public IEnumerator LoginWithoutMfaStillSignsIn()
        {
            var server = new FakeServer { Respond = (_, __) => (200, new { mfa_required = false, access_token = "tok-2" }) };
            yield return Await(NoMfa(server));
        }

        static async Task NoMfa(FakeServer server)
        {
            using var api = new DrikrApi("http://drikr.test/api/v1", server);
            Assert.IsFalse(await api.Login("trainee2", "pw"));
            Assert.IsTrue(api.SignedIn);
        }

        static string TlsDir()
        {
            var dir = Environment.GetEnvironmentVariable("DRIKR_TEST_TLS_DIR");
            if (string.IsNullOrEmpty(dir) || !File.Exists(Path.Combine(dir, "ca.crt")))
                Assert.Ignore("Set DRIKR_TEST_TLS_DIR to the generate-tls-cert.sh output to run");
            return dir;
        }

        [Test]
        public void PinnedCaValidation()
        {
            var dir = TlsDir();
            var ca = DrikrApi.LoadCertificate(Path.Combine(dir, "ca.crt"));
            var server = DrikrApi.LoadCertificate(Path.Combine(dir, "server.crt"));
            Assert.IsTrue(DrikrApi.ValidateServer(ca, server, SslPolicyErrors.RemoteCertificateChainErrors));
            Assert.IsTrue(DrikrApi.ValidateServer(null, server, SslPolicyErrors.None), "system-trusted chains pass");
            Assert.IsFalse(DrikrApi.ValidateServer(null, server, SslPolicyErrors.RemoteCertificateChainErrors), "no pin, untrusted");
            Assert.IsFalse(DrikrApi.ValidateServer(server, server, SslPolicyErrors.RemoteCertificateChainErrors), "wrong pin");
            Assert.IsFalse(DrikrApi.ValidateServer(ca, server,
                SslPolicyErrors.RemoteCertificateChainErrors | SslPolicyErrors.RemoteCertificateNameMismatch), "name mismatch");
            Assert.IsFalse(DrikrApi.ValidateServer(ca, null, SslPolicyErrors.RemoteCertificateNotAvailable));
        }

        [UnityTest, Timeout(60000)]
        public IEnumerator LiveHttpsWithPinnedCa()
        {
            var dir = TlsDir();
            var url = Environment.GetEnvironmentVariable("DRIKR_LIVE_HTTPS_API");
            var pw = Environment.GetEnvironmentVariable("DRIKR_LIVE_PASSWORD");
            if (string.IsNullOrEmpty(url) || string.IsNullOrEmpty(pw)) Assert.Ignore("Set DRIKR_LIVE_HTTPS_API and DRIKR_LIVE_PASSWORD to run");
            yield return Await(LiveHttps(url, pw, Path.Combine(dir, "ca.crt")));
        }

        static async Task LiveHttps(string url, string password, string caPath)
        {
            using (var pinned = new DrikrApi(url, caCertPath: caPath))
            {
                Assert.IsFalse(await pinned.Login("trainee2", password));
                Assert.Greater((await pinned.PracticeScenarios()).Items.Count, 0);
                await pinned.Logout();
            }
            using (var unpinned = new DrikrApi(url))
            {
                var e = await Throws(() => unpinned.Login("trainee2", password));
                Assert.AreEqual(0, e.Status, "an untrusted certificate must fail the connection");
            }
        }
    }
}
