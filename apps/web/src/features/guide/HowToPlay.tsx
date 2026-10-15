import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/overlay";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import {
  CLASSIFICATION_HELP,
  CLASSIFICATION_LABELS,
  label,
  RESPONSE_HELP,
  RESPONSE_LABELS,
} from "@/lib/labels";
import { TRACK_CLASSIFICATIONS, TRAINING_RESPONSES } from "@/contracts/scenario";

export const GUIDE_PATH = "/trainee/how-to-play";
const SEEN_KEY = "drikr.guide.seen.v1";

const STEPS: [string, string][] = [
  [
    "Open an exercise",
    "From My exercises, or any scenario in the Practice library. Read the briefing, then press Prepare exercise.",
  ],
  ["Start", "Press Start exercise. The clock is kept by the training server."],
  [
    "Select a track",
    "Tracks are things in the sky. Tick one in the Tracks table, or click its dot in the picture.",
  ],
  ["Classify it", "Say what you think it is and how sure you are, then press Submit classification."],
  [
    "Respond",
    "Choose what to do about it: keep watching, ask for a closer look, report it, or log it as cleared.",
  ],
  ["Repeat and finish", "Handle each new track. Press Finish exercise, then Finish and score."],
  [
    "Learn from the review",
    "The after-action review shows your score, each decision, and what to practise next.",
  ],
];

const TIPS = [
  "Unsure? Choose Low confidence or Request sensor confirmation. Honest uncertainty scores better than a confident wrong answer.",
  "Speed counts: classify each track soon after it appears.",
  "Always classify a track before you report or clear it.",
  "Do not clear something you have only seen briefly; wait for a few observations.",
  "Colours in the picture show your own classification, never the true answer.",
];

/** The full guide, used on its own page. */
export function HowToPlayContent() {
  return (
    <div className="space-y-4">
      <Panel>
        <PanelHeader
          title="What you are doing"
          description="All tracks and sensors are simulated. Nothing here is real or controls anything."
        />
        <PanelBody>
          <p className="text-sm leading-relaxed">
            You watch a simulated sensor picture around a protected site. Small dots called{" "}
            <strong>tracks</strong> appear: each is something in the sky. For every track you decide{" "}
            <strong>what it is</strong> and <strong>what to do about it</strong>. When you finish, your
            decisions are scored and explained.
          </p>
        </PanelBody>
      </Panel>
      <Panel>
        <PanelHeader title="Step by step" />
        <PanelBody>
          <ol className="space-y-3">
            {STEPS.map(([title, text], i) => (
              <li key={title} className="flex gap-3">
                <span
                  aria-hidden="true"
                  className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand text-xs font-semibold text-brand-ink"
                >
                  {i + 1}
                </span>
                <span className="text-sm">
                  <span className="font-medium">{title}.</span> {text}
                </span>
              </li>
            ))}
          </ol>
        </PanelBody>
      </Panel>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="What it could be (Classify)" />
          <Table>
            <THead>
              <TR>
                <TH>Choice</TH>
                <TH>Means</TH>
              </TR>
            </THead>
            <TBody>
              {TRACK_CLASSIFICATIONS.map((c) => (
                <TR key={c}>
                  <TD className="whitespace-nowrap font-medium">{label(CLASSIFICATION_LABELS, c)}</TD>
                  <TD className="text-sm">{CLASSIFICATION_HELP[c]}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </Panel>
        <Panel>
          <PanelHeader title="What to do (Training response)" />
          <Table>
            <THead>
              <TR>
                <TH>Choice</TH>
                <TH>Means</TH>
              </TR>
            </THead>
            <TBody>
              {TRAINING_RESPONSES.map((r) => (
                <TR key={r}>
                  <TD className="whitespace-nowrap font-medium">{label(RESPONSE_LABELS, r)}</TD>
                  <TD className="text-sm">{RESPONSE_HELP[r]}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </Panel>
      </div>
      <Panel>
        <PanelHeader title="Reading the Tracks table" />
        <PanelBody>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            <li>
              <strong>Sensors</strong>: R radar, O optical camera, RF radio signal. More sensors usually means
              better evidence.
            </li>
            <li>
              <strong>Hint</strong>: what the sensors suggest, with a quality from 0 to 1. Below 0.5 is weak
              evidence.
            </li>
            <li>
              <strong>Beacon</strong>: the track broadcasts an identification signal (a cooperative drone).
            </li>
            <li>
              <strong>Lost</strong>: the sensors no longer see it. You can still classify it.
            </li>
          </ul>
        </PanelBody>
      </Panel>
      <Panel>
        <PanelHeader title="Tips for a good score" />
        <PanelBody>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {TIPS.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </PanelBody>
      </Panel>
    </div>
  );
}

export function HowToPlayPage() {
  return (
    <>
      <PageHeader
        title="How to play"
        description="A short guide to running an exercise. You can open it again at any time from the menu."
        actions={
          <Button asChild>
            <Link to="/trainee/practice">Try a practice exercise</Link>
          </Button>
        }
      />
      <HowToPlayContent />
    </>
  );
}

function seen(): boolean {
  try {
    return window.localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return true; // storage unavailable: do not nag on every visit
  }
}

function markSeen(): void {
  try {
    window.localStorage.setItem(SEEN_KEY, "1");
  } catch {
    /* storage unavailable */
  }
}

/** Short welcome shown once, on a trainee's first visit. */
export function FirstVisitGuide() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!seen()) setOpen(true);
  }, []);
  const close = () => {
    markSeen();
    setOpen(false);
  };
  return (
    <Dialog
      open={open}
      onOpenChange={(v) => (v ? setOpen(true) : close())}
      title="Welcome to the training simulator"
      description="Things appear in a simulated sky. For each one, you decide what it is and what to do."
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            Got it
          </Button>
          <Button asChild onClick={markSeen}>
            <Link to={GUIDE_PATH}>Read the full guide</Link>
          </Button>
        </>
      }
    >
      <ol className="list-decimal space-y-1.5 pl-5 text-sm">
        <li>Open an exercise and press Start exercise.</li>
        <li>Select a track (a dot) in the Tracks table.</li>
        <li>Classify it: what is it, and how sure are you?</li>
        <li>Choose a response: watch, confirm, report or clear.</li>
        <li>Finish, then read your score and feedback.</li>
      </ol>
      <p className="mt-3 text-xs text-ink-subtle">
        During an exercise, a Next step bar tells you what to do. The guide is always under How to play in the
        menu.
      </p>
    </Dialog>
  );
}
