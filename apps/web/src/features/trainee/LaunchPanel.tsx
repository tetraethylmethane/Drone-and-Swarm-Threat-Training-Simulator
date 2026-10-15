import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/form";
import { KeyValues, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Alert } from "@/components/ui/status";
import { api, ApiError } from "@/lib/api";
import { formatClock } from "@/lib/format";
import { ENV_LABELS, label, SENSOR_LABELS } from "@/lib/labels";
import type { Briefing, SessionState, TraineeOptions } from "@/lib/types";
import { errorMessage } from "@/lib/useAsync";

const SeedSchema = z.coerce
  .number()
  .int("Use a whole number")
  .min(0, "Use 0 or more")
  .max(Number.MAX_SAFE_INTEGER);

export function BriefingPanel({ briefing }: { briefing: Briefing }) {
  const env = briefing.environment;
  return (
    <Panel>
      <PanelHeader title="Briefing" description={briefing.synthetic_notice} />
      <PanelBody className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div>
          <p className="whitespace-pre-line text-sm leading-relaxed">{briefing.briefing}</p>
          <h3 className="mt-5">Learning objectives</h3>
          <ol className="mt-1.5 list-decimal space-y-1 pl-5 text-sm">
            {briefing.learning_objectives.map((o) => (
              <li key={o.id}>{o.description}</li>
            ))}
          </ol>
        </div>
        <div className="space-y-4">
          <KeyValues
            items={[
              ["Terrain", label(ENV_LABELS, env.terrain)],
              ["Time of day", label(ENV_LABELS, env.time_of_day)],
              ["Weather", label(ENV_LABELS, env.weather)],
              ["Visibility", `${env.visibility_km} km`],
              ["Duration", formatClock(briefing.duration_s * 1000)],
              ["Pausing", briefing.allow_pause ? "Permitted" : "Not permitted"],
            ]}
          />
          <div>
            <h3 className="mb-1">Simulated sensors</h3>
            <ul className="space-y-0.5 text-sm">
              {Object.entries(briefing.sensors).map(([k, v]) => (
                <li key={k} className={v.enabled ? "" : "text-ink-subtle line-through"}>
                  {label(SENSOR_LABELS, k)}
                  {v.enabled ? (
                    <span className="text-ink-subtle"> · {(v.range_m / 1000).toFixed(1)} km range</span>
                  ) : (
                    " (off)"
                  )}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </PanelBody>
    </Panel>
  );
}

interface LaunchProps {
  options: TraineeOptions;
  defaults: { time_of_day: string; weather: string };
  body: { assignment_id?: string; scenario_id?: string };
  activeSessionId?: string | null;
  disabledReason?: string | null;
  difficultyLevel?: number;
}

export function LaunchPanel({
  options,
  defaults,
  body,
  activeSessionId,
  disabledReason,
  difficultyLevel,
}: LaunchProps) {
  const navigate = useNavigate();
  const [tod, setTod] = useState("");
  const [weather, setWeather] = useState("");
  const [seed, setSeed] = useState("");
  const [seedError, setSeedError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const anyOptions =
    options.time_of_day.length > 0 || options.weather.length > 0 || options.allow_custom_seed;

  async function launch() {
    setError(null);
    const selection: Record<string, unknown> = {};
    if (tod) selection.time_of_day = tod;
    if (weather) selection.weather = weather;
    if (seed.trim()) {
      const parsed = SeedSchema.safeParse(seed.trim());
      if (!parsed.success) {
        setSeedError(parsed.error.issues[0]?.message ?? "Invalid seed");
        return;
      }
      selection.seed = parsed.data;
    }
    setSeedError(null);
    setBusy(true);
    try {
      const s = await api.post<SessionState>("/sessions", { ...body, selection });
      navigate(`/exercise/${s.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.code === "session_in_progress") {
        const sid = (err.details as { session_id?: string } | undefined)?.session_id;
        if (sid) {
          navigate(`/exercise/${sid}`);
          return;
        }
      }
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel>
      <PanelHeader
        title="Launch"
        description={
          difficultyLevel ? `This attempt will run at difficulty level ${difficultyLevel} of 5.` : undefined
        }
      />
      <PanelBody className="space-y-4">
        {activeSessionId ? (
          <>
            <p className="text-sm text-ink-muted">An attempt is already in progress.</p>
            <Button onClick={() => navigate(`/exercise/${activeSessionId}`)}>Resume exercise</Button>
          </>
        ) : (
          <>
            {anyOptions ? (
              <div className="grid gap-3 sm:grid-cols-3">
                {options.time_of_day.length ? (
                  <Field label="Time of day">
                    <Select value={tod} onChange={(e) => setTod(e.target.value)}>
                      <option value="">As briefed ({label(ENV_LABELS, defaults.time_of_day)})</option>
                      {options.time_of_day.map((v) => (
                        <option key={v} value={v}>
                          {label(ENV_LABELS, v)}
                        </option>
                      ))}
                    </Select>
                  </Field>
                ) : null}
                {options.weather.length ? (
                  <Field label="Weather">
                    <Select value={weather} onChange={(e) => setWeather(e.target.value)}>
                      <option value="">As briefed ({label(ENV_LABELS, defaults.weather)})</option>
                      {options.weather.map((v) => (
                        <option key={v} value={v}>
                          {label(ENV_LABELS, v)}
                        </option>
                      ))}
                    </Select>
                  </Field>
                ) : null}
                {options.allow_custom_seed ? (
                  <Field
                    label="Scenario seed"
                    hint="Leave blank for the standard variation."
                    error={seedError}
                  >
                    <Input inputMode="numeric" value={seed} onChange={(e) => setSeed(e.target.value)} />
                  </Field>
                ) : null}
              </div>
            ) : (
              <p className="text-sm text-ink-muted">Your instructor has fixed all exercise options.</p>
            )}
            {disabledReason ? <Alert tone="warning">{disabledReason}</Alert> : null}
            {error ? <Alert tone="danger">{error}</Alert> : null}
            <Button onClick={launch} disabled={busy || Boolean(disabledReason)}>
              {busy ? "Preparing exercise" : "Prepare exercise"}
            </Button>
          </>
        )}
      </PanelBody>
    </Panel>
  );
}
