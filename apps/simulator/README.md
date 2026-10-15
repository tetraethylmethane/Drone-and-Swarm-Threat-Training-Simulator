# Simulator: Unity client

`DrikrUnityClient/` is a Unity 6 (6000.3.26f1) desktop client for the training simulator, built
for Windows, Linux and macOS. It is a **visual adapter**: it signs in, polls the session feed,
renders the trainee-visible track picture in 3D and submits the predefined training actions. It
contains **no simulation, timing or scoring logic**. The authoritative logical simulation stays on
the server (`packages/simcore`, ADR-001), so the browser client and the Unity client show the same
picture for the same session and are scored identically.

## Platforms

| Platform | Output | Status |
|---|---|---|
| Windows x64 | `Builds/Windows/DrikrTrainingSimulator.exe` | Built and tested here: EditMode tests, smoke test over HTTPS, screen-reader check |
| Linux x86_64 | `Builds/Linux/DrikrTrainingSimulator.x86_64` | Built here; smoke test passes in Ubuntu 24.04 (Xvfb, software OpenGL) over HTTPS (`scripts/unity-linux-smoke.sh`) |
| macOS (universal: Intel and Apple silicon, macOS 12 or later) | `Builds/macOS/DrikrTrainingSimulator.app` | Built here on Windows; bundle and universal binary checked. **Not yet run on a Mac.** Unsigned: sign and notarise on a Mac before distributing, or users must allow it in System Settings → Privacy & Security |

Building for Linux and macOS needs Unity's "Linux Build Support (Mono)" and "Mac Build Support
(Mono)" modules for 6000.3.26f1.

## Layout

| Path | Purpose |
|---|---|
| `Assets/Drikr/Runtime/Contracts.cs` | DTOs mirroring the JSON contract (`packages/contracts/schemas`) |
| `Assets/Drikr/Runtime/DrikrApi.cs` | Adapter protocol over HTTP(S): bearer tokens, MFA step, pinned CA, idempotent action retries |
| `Assets/Drikr/Runtime/TrackPicture.cs` | Pure projection of trainee-visible events; same rules as the web adapter |
| `Assets/Drikr/Runtime/DrikrClientApp.cs` | Procedural scene, camera, IMGUI panel, polling loop, opt-in smoke mode |
| `Assets/Drikr/Runtime/PanelAccessibility.cs` | Publishes the panel to the operating system's screen reader |
| `Assets/Drikr/Editor/BuildScript.cs` | Batch-mode asset preparation and Windows, Linux, macOS builds |
| `Assets/Drikr/Tests/EditMode/` | Unit, contract, security, accessibility and live protocol tests |

Packages: `com.unity.nuget.newtonsoft-json` 3.2.1, `com.unity.test-framework` 1.6.0 and a minimal
set of engine modules (including `accessibility`). Unity Analytics, Cloud Diagnostics and all Unity
services are disabled; no imported 3D assets are used (primitives and unlit flat colours only).

## Build and test locally (batch mode)

```bash
U="C:/Program Files/Unity 6000.3.26f1/Editor/Unity.exe"
P="<repo>/apps/simulator/DrikrUnityClient"

# EditMode tests. Live tests run only when these are set (stack running, demo users seeded):
#   DRIKR_LIVE_API        plain-HTTP API (e.g. the dev API, http://127.0.0.1:8000/api/v1)
#   DRIKR_LIVE_HTTPS_API  HTTPS API (docker-compose.tls.yml), with DRIKR_TEST_TLS_DIR=<repo>/deploy/tls
DRIKR_LIVE_API=http://127.0.0.1:8000/api/v1 DRIKR_LIVE_PASSWORD=<demo password> \
DRIKR_LIVE_HTTPS_API=https://localhost:8443/api/v1 DRIKR_TEST_TLS_DIR=<repo>/deploy/tls \
  "$U" -batchmode -nographics -projectPath "$P" -runTests -testPlatform EditMode -testResults "$P/Logs/editmode-results.xml"

# Players: BuildWindows, BuildLinux, BuildMacOS, or BuildAll (every target whose module is installed)
"$U" -batchmode -nographics -quit -projectPath "$P" -executeMethod Drikr.EditorTools.BuildScript.BuildAll

# Smoke tests against a running stack (exit code 0 = pass)
DRIKR_SMOKE_USER=trainee2 DRIKR_SMOKE_PASSWORD=<demo password> \
  ./Builds/Windows/DrikrTrainingSimulator.exe -drikrApi https://localhost:8443/api/v1 \
  -drikrCa <repo>/deploy/tls/ca.crt -drikrSmoke shot.png
DRIKR_SMOKE_PASSWORD=<demo password> bash scripts/unity-linux-smoke.sh        # Linux player in Docker

# Screen-reader check through Windows UI Automation (see "Accessibility")
DRIKR_A11Y_PASSWORD=<demo password> powershell -File scripts/unity-a11y-check.ps1 \
  -Exe Builds/Windows/DrikrTrainingSimulator.exe -Ca deploy/tls/ca.crt
```

## Continuous integration

`.github/workflows/unity.yml` runs the EditMode tests and builds all three players. Unity's licence
terms require an activated licence wherever the editor runs, so CI cannot run without one. There
are two ways to provide it:

**A. GitHub-hosted runners (GameCI containers).** Add repository secrets:

| Licence | Secrets |
|---|---|
| Unity Personal | `UNITY_LICENSE` (the full contents of `Unity_lic.ulf`, found at `C:\ProgramData\Unity\Unity_lic.ulf` after activating in Unity Hub), `UNITY_EMAIL`, `UNITY_PASSWORD` |
| Unity Plus / Pro | `UNITY_SERIAL`, `UNITY_EMAIL`, `UNITY_PASSWORD` |

The workflow then runs `game-ci/unity-test-runner` and `game-ci/unity-builder` (pinned versions)
with the `unityci/editor` 6000.3.26f1 images, and uploads each player as an artifact.

**B. A self-hosted Windows runner** on a licensed workstation (no secrets):
1. Install Unity 6000.3.26f1 with Linux and Mac Build Support (Mono).
2. Register the machine as a GitHub Actions runner with the extra label `unity`.
3. Set the repository variable `UNITY_SELF_HOSTED=true` (and `UNITY_EXE` if Unity is installed
   elsewhere).

The job runs exactly the batch-mode commands above.

With neither configured, the jobs are skipped and the run shows a notice saying which secrets are
missing. The workflow passes `actionlint`. It has not run on GitHub yet, because this repository
has no remote.

## Running

```bash
DrikrTrainingSimulator.exe -drikrApi https://drikr-training.local:8443/api/v1 -drikrCa ca.crt
./DrikrTrainingSimulator.x86_64 -drikrApi ... -drikrCa ca.crt             # Linux
open DrikrTrainingSimulator.app --args -drikrApi ... -drikrCa ca.crt      # macOS
```

`-drikrCa` (or `DRIKR_CA_CERT`) names the training network's CA certificate from
`scripts/generate-tls-cert.sh`. Certificates it issued are trusted in addition to the system
roots, and host names are always checked. Leave it out when the server certificate comes from a CA
the workstation already trusts.

If the account uses multi-factor authentication, the sign-in screen asks for the 6-digit code (or a
recovery code) after the password. Setting up MFA is done in the web application.

The API URL can also be set with `DRIKR_API_URL` or edited on the sign-in screen. Sign in as a
trainee, then launch an assigned exercise or a practice scenario. Select tracks in the panel's
track list or click them in the view (Shift adds); right-drag to orbit, scroll to zoom. The
after-action review remains in the web application; the Unity client shows the overall result after
finishing.

## Accessibility

The panel is published to the operating system's screen reader through Unity's accessibility API
(`PanelAccessibility.cs`):
- every heading, text, button, checkbox, option and text field has a role, a name, its state
  (disabled, checked, selected) and its position;
- passwords are exposed only as a character count;
- activating an element runs the same code as a click, and activating a text field gives it the
  keyboard;
- new tracks, status changes, confirmations and errors are announced;
- the exercise clock is one element whose text updates, not a stream of new elements.

Everything the 3D view offers by mouse (track selection) is also in the panel.

| Platform | Screen reader | Status |
|---|---|---|
| Windows | Narrator, NVDA, JAWS (UI Automation) | **Verified** with a UI Automation client (`scripts/unity-a11y-check.ps1`). It signs in by focusing fields and typing, starts a practice exercise, selects a track, classifies it, finishes and reads the result, without any pointer input |
| macOS | VoiceOver | Unity's macOS player includes the NSAccessibility bridge for this API. **Not tested on a Mac** |
| Linux | Orca | **Not supported**: Unity's Linux player has no AT-SPI bridge. Use the web application |

The player publishes the tree when the operating system reports a running screen reader. Start it
with `-drikrScreenReader` to publish it regardless, for screen readers Windows does not report, or
for testing.

Not yet done: a session with screen-reader users, and a manual pass with each screen reader. The
web application remains the most complete accessible interface: the AAR, charts and
administration exist only there.

## Limitations

* No VR. The adapter protocol allows a future XR client.
* macOS builds are unsigned and have not been run on a Mac (see Platforms).
* `insecureHttpOption` is set to allow plain HTTP for `localhost` and closed training networks.
  Use HTTPS (`docker-compose.tls.yml`) for anything else.
* The client's Mono runtime cannot validate ECDSA certificate chains; the certificate script
  therefore issues RSA-3072 certificates. An organisation CA used with `-drikrCa` must also be RSA.
