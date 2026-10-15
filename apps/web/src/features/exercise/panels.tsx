import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, Select, Textarea } from "@/components/ui/form";
import { Alert, Tag } from "@/components/ui/status";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { TRACK_CLASSIFICATIONS, TRAINING_RESPONSES } from "@/contracts/scenario";
import { formatClock } from "@/lib/format";
import {
  CLASSIFICATION_HELP,
  CLASSIFICATION_LABELS,
  CONFIDENCE_LABELS,
  label,
  RESPONSE_HELP,
  RESPONSE_LABELS,
  SENSOR_LABELS,
} from "@/lib/labels";
import { errorMessage } from "@/lib/useAsync";

import type { Picture, Track } from "./trackPicture";
import type { ActionBody } from "./useExercise";
import { colorFor } from "./visual";

const SENSOR_SHORT: Record<string, string> = { radar: "R", electro_optical: "O", rf: "RF" };

export function TrackTable({
  tracks,
  selected,
  onToggle,
  nowMs,
}: {
  tracks: Track[];
  selected: Set<string>;
  onToggle: (id: string, additive: boolean) => void;
  nowMs: number;
}) {
  if (!tracks.length) {
    return (
      <p className="px-4 py-6 text-sm text-ink-muted">
        No tracks yet. Synthetic observations appear here as the simulated sensors report them.
      </p>
    );
  }
  return (
    <Table aria-label="Tracks">
      <THead>
        <TR>
          <TH className="w-8">
            <span className="sr-only">Select</span>
          </TH>
          <TH>Track</TH>
          <TH>Sensors</TH>
          <TH>Last seen</TH>
          <TH>Optical hint</TH>
          <TH>Beacon</TH>
          <TH>My classification</TH>
          <TH>My response</TH>
        </TR>
      </THead>
      <TBody>
        {tracks.map((t) => {
          const isSel = selected.has(t.id);
          const age = Math.max(0, nowMs - t.lastSeenMs) / 1000;
          return (
            <TR key={t.id} className={isSel ? "bg-brand-soft/60" : t.lost ? "text-ink-subtle" : undefined}>
              <TD>
                <input
                  type="checkbox"
                  aria-label={`Select ${t.id}`}
                  checked={isSel}
                  onChange={() => onToggle(t.id, true)}
                  className="h-4 w-4 accent-[rgb(31_77_58)]"
                />
              </TD>
              <TD>
                <button
                  type="button"
                  className="flex items-center gap-2 font-medium text-ink hover:underline"
                  onClick={() => onToggle(t.id, false)}
                >
                  <span
                    aria-hidden="true"
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ background: colorFor(t.classification?.value) }}
                  />
                  {t.id}
                </button>
                {t.lost ? <span className="ml-1 text-2xs text-ink-subtle">lost</span> : null}
              </TD>
              <TD
                className="whitespace-nowrap text-xs text-ink-muted"
                title={[...t.sensors].map((s) => label(SENSOR_LABELS, s)).join(", ")}
              >
                {[...t.sensors]
                  .sort()
                  .map((s) => SENSOR_SHORT[s] ?? s)
                  .join(" · ")}
              </TD>
              <TD className="tabular whitespace-nowrap text-xs">
                {age < 1 ? "now" : `${age.toFixed(0)} s ago`}
              </TD>
              <TD className="text-xs">
                {t.pendingConfirmation ? (
                  <span className="text-ink-muted">Confirmation pending</span>
                ) : t.classHint ? (
                  <span>
                    {label(CLASSIFICATION_LABELS, t.classHint.value)}{" "}
                    <span className="text-ink-subtle">
                      ({t.classHint.quality.toFixed(2)}
                      {t.classHint.source === "confirmation" ? ", confirmed" : ""})
                    </span>
                  </span>
                ) : (
                  <span className="text-ink-subtle">None</span>
                )}
              </TD>
              <TD className="text-xs">
                {t.beacon ? "Observed" : <span className="text-ink-subtle">Not seen</span>}
              </TD>
              <TD className="text-xs">
                {t.classification ? (
                  <>
                    {label(CLASSIFICATION_LABELS, t.classification.value)}{" "}
                    <span className="text-ink-subtle">
                      ({label(CONFIDENCE_LABELS, t.classification.confidence)})
                    </span>
                  </>
                ) : (
                  <span className="text-ink-subtle">Not classified</span>
                )}
              </TD>
              <TD className="text-xs">
                {t.response ? (
                  label(RESPONSE_LABELS, t.response.value)
                ) : (
                  <span className="text-ink-subtle">None</span>
                )}
              </TD>
            </TR>
          );
        })}
      </TBody>
    </Table>
  );
}

export function DecisionPanel({
  selected,
  disabled,
  onSubmit,
}: {
  selected: string[];
  disabled: boolean;
  onSubmit: (body: ActionBody) => Promise<unknown>;
}) {
  const [classification, setClassification] = useState("");
  const [confidence, setConfidence] = useState("medium");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const confId = useId();
  const none = selected.length === 0;

  async function send(body: ActionBody, done: string) {
    setBusy(true);
    setMessage(null);
    try {
      await onSubmit({ ...body, note: note.trim() || undefined });
      setMessage({ tone: "success", text: done });
      setNote("");
    } catch (err) {
      setMessage({ tone: "danger", text: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-ink-muted">
        {none ? "Select one or more tracks in the table or the view." : `Selected: ${selected.join(", ")}`}
      </p>
      <fieldset className="space-y-3" disabled={disabled || busy || none}>
        <legend className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">1. Classify</legend>
        <Field
          label="Classification"
          hint={classification ? CLASSIFICATION_HELP[classification] : "What do you think this track is?"}
        >
          <Select value={classification} onChange={(e) => setClassification(e.target.value)}>
            <option value="">Choose a classification</option>
            {TRACK_CLASSIFICATIONS.map((c) => (
              <option key={c} value={c}>
                {label(CLASSIFICATION_LABELS, c)}
              </option>
            ))}
          </Select>
        </Field>
        <div role="radiogroup" aria-labelledby={confId}>
          <p id={confId} className="mb-1.5 text-xs font-medium">
            Confidence
          </p>
          <div className="flex gap-1">
            {(["low", "medium", "high"] as const).map((c) => (
              <label
                key={c}
                className={`flex h-8 flex-1 cursor-pointer items-center justify-center rounded border text-xs ${
                  confidence === c
                    ? "border-brand bg-brand-soft font-medium text-brand"
                    : "border-border-strong bg-surface text-ink-muted"
                }`}
              >
                <input
                  type="radio"
                  name="confidence"
                  value={c}
                  checked={confidence === c}
                  onChange={() => setConfidence(c)}
                  className="sr-only"
                />
                {CONFIDENCE_LABELS[c]}
              </label>
            ))}
          </div>
        </div>
        <Button
          className="w-full"
          disabled={!classification}
          onClick={() =>
            send(
              { kind: "classify", track_ids: selected, classification, confidence },
              `Classification recorded for ${selected.length} track(s).`,
            )
          }
        >
          Submit classification
        </Button>
      </fieldset>

      <fieldset className="space-y-2 border-t border-border pt-4" disabled={disabled || busy || none}>
        <legend className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">
          2. Training response
        </legend>
        {TRAINING_RESPONSES.map((r) => (
          <Button
            key={r}
            variant="secondary"
            className="h-auto w-full flex-col items-start gap-0.5 whitespace-normal py-2 text-left"
            onClick={() =>
              send(
                { kind: "respond", track_ids: selected, response: r },
                `${label(RESPONSE_LABELS, r)} recorded.`,
              )
            }
          >
            <span className="text-sm font-medium">{label(RESPONSE_LABELS, r)}</span>
            <span className="text-xs font-normal text-ink-muted">{RESPONSE_HELP[r]}</span>
          </Button>
        ))}
        <Field label="Note (optional)" hint="Saved with the next decision you submit.">
          <Textarea
            maxLength={280}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="min-h-[56px]"
          />
        </Field>
      </fieldset>
      {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}
    </div>
  );
}

export function SensorPanel({ picture }: { picture: Picture }) {
  const sensors = [...picture.sensors.values()].sort((a, b) => a.sensor.localeCompare(b.sensor));
  return (
    <ul className="divide-y divide-border">
      {sensors.map((s) => (
        <li key={s.sensor} className="flex items-center justify-between gap-2 px-4 py-2 text-sm">
          <span>{label(SENSOR_LABELS, s.sensor)}</span>
          <span className="flex items-center gap-2">
            {s.status === "degraded" ? (
              <span className="text-2xs text-ink-subtle">
                detection ×{s.detection_factor.toFixed(2)}, noise ×{s.noise_factor.toFixed(1)}
                {s.extra_delay_s ? `, +${s.extra_delay_s}s delay` : ""}
              </span>
            ) : null}
            <Tag tone={s.status === "degraded" ? "warning" : "success"}>
              {s.status === "degraded" ? "Degraded" : "Nominal"}
            </Tag>
          </span>
        </li>
      ))}
      <li className="flex items-center justify-between px-4 py-2 text-sm">
        <span>Visibility</span>
        <span className="tabular">
          {picture.visibilityKm !== null ? `${picture.visibilityKm.toFixed(1)} km` : "—"}
        </span>
      </li>
    </ul>
  );
}

export function EventLog({ picture }: { picture: Picture }) {
  const rows = [
    ...picture.messages.map((m) => ({ id: m.id, t: m.t_ms, text: m.text, kind: "Message" })),
    ...picture.decisions.map((d) => {
      const p = d.payload as Record<string, unknown>;
      const ids = (p.track_ids as string[]).join(", ");
      const text =
        d.type === "classification_submitted"
          ? `${ids}: classified ${label(CLASSIFICATION_LABELS, p.classification as string)} (${label(CONFIDENCE_LABELS, p.confidence as string)})`
          : `${ids}: ${label(RESPONSE_LABELS, p.response as string)}`;
      return { id: d.event_id, t: d.t_ms, text, kind: "Decision" };
    }),
    ...picture.lifecycle.map((l) => ({
      id: l.event_id,
      t: l.t_ms,
      text:
        l.type.replace("session_", "Exercise ") +
        ((l.payload as { reason?: string }).reason ? ` (${(l.payload as { reason?: string }).reason})` : ""),
      kind: "Exercise",
    })),
  ].sort((a, b) => b.t - a.t);
  if (!rows.length) return <p className="px-4 py-3 text-sm text-ink-muted">No events yet.</p>;
  return (
    <ol
      className="max-h-64 divide-y divide-border overflow-y-auto"
      aria-live="polite"
      aria-relevant="additions"
    >
      {rows.slice(0, 60).map((r) => (
        <li key={r.id} className="grid grid-cols-[52px_72px_1fr] gap-2 px-4 py-1.5 text-xs">
          <span className="tabular text-ink-subtle">{formatClock(r.t)}</span>
          <span className="text-ink-muted">{r.kind}</span>
          <span className="text-ink">{r.text}</span>
        </li>
      ))}
    </ol>
  );
}
