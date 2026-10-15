# Trainee guide

All tracks, sensor readings and events in this application are synthetic training data inside a
virtual exercise.

## 1. Sign in

Use the username and temporary password from your administrator. You must choose a new password at
first sign-in (at least 12 characters, using three of: lowercase, uppercase, digit, symbol).

**Verification codes.** If your account uses multi-factor authentication, sign-in asks for a 6-digit
code from your authenticator app after the password. If you do not have your phone, enter one of
your recovery codes instead; each works once. To set up an authenticator, or to create new recovery
codes, open **Account and security**. If your organisation requires MFA for your role, that page
opens automatically until you have set it up.

## 2. Find your exercises

**My exercises** lists assignments from your instructor with status, attempts used and best score.
**Practice library** lists scenarios your organisation allows for self-guided practice.

## 3. Read the briefing and launch

Open an exercise to read the instructor's instructions, the briefing, the learning objectives, the
environment and the simulated sensors. If your instructor allows it, choose time of day, weather or a
scenario seed. The panel states the difficulty level of this attempt. Select **Prepare exercise**.

## 4. Run the exercise

1. Select **Start exercise**. The clock is kept by the training server.
2. Tracks appear in the **sensor picture** (3D view or plan view) and in the **Tracks** table as the
   simulated sensors report them: R radar, O optical, RF radio frequency. *Optical hint* is an
   uncertain suggestion with a quality value; *Beacon* means a simulated cooperative beacon was
   received.
3. Select one or more tracks (checkboxes, or click; Shift-click to add).
4. **Classify** with a confidence level. Use *Low* when evidence is weak.
5. Choose a **training response**: continue monitoring, request sensor confirmation (an improved hint
   arrives after about 4 s), report to exercise control, or log as cleared.
6. Watch **Simulated sensor status** for degradation and the **Exercise log** for messages.
7. **Pause** if permitted. If your connection drops, the clock stops after about 15 s and the
   exercise pauses itself; select **Resume** when you return. Decisions already submitted are kept.
8. Select **Finish exercise** when done, or the exercise ends at its time limit.

## 5. Review your result

The after-action review shows your overall score, each dimension and how it was calculated, the
objectives, and feedback. With detailed feedback you also see the ground truth per track, the event
timeline and error analysis, and can download a PDF. Shared instructor reviews appear under
**Instructor review**.

## 6. Track your progress

**My progress** charts your scored sessions over time, shows difficulty adjustments with the reason
for each, and lists all attempts.
