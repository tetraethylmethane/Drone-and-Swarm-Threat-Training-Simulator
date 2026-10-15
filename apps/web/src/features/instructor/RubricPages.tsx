import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/form";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/overlay";
import { KeyValues, PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Alert, Tag } from "@/components/ui/status";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { DIMENSION_HELP, DIMENSION_LABELS, DIMENSION_ORDER, label, RESPONSE_LABELS } from "@/lib/labels";
import type { RubricSummary, ValidationIssue } from "@/lib/types";
import { errorMessage, useAsync } from "@/lib/useAsync";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Def = Record<string, any>;

export function RubricListPage() {
  const st = useAsync((sig) => api.get<{ items: RubricSummary[] }>("/rubrics", sig), []);
  return (
    <>
      <PageHeader
        title="Scoring rubrics"
        description="Versioned, transparent scoring rules. Every score records the rubric version it used, so editing a rubric never changes historical results."
      />
      <Panel>
        {st.loading ? (
          <LoadingState />
        ) : st.error ? (
          <ErrorState error={st.error} onRetry={st.reload} />
        ) : !st.data?.items.length ? (
          <EmptyState title="No rubrics" />
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Rubric</TH>
                <TH>Latest version</TH>
                <TH>Pass mark</TH>
                <TH>Weights</TH>
                <TH>
                  <span className="sr-only">Actions</span>
                </TH>
              </TR>
            </THead>
            <TBody>
              {st.data.items.map((r) => (
                <TR key={r.id}>
                  <TD>
                    <p className="font-medium">{r.name}</p>
                    <p className="text-xs text-ink-subtle">{r.key}</p>
                    {r.is_demo ? <Tag tone="info">Demonstration</Tag> : null}
                  </TD>
                  <TD>v{r.version}</TD>
                  <TD className="tabular">{r.pass_mark}%</TD>
                  <TD className="text-xs text-ink-muted">
                    {DIMENSION_ORDER.map((d) => `${DIMENSION_LABELS[d]!.split(" ")[0]} ${r.weights[d]}`).join(
                      " · ",
                    )}
                  </TD>
                  <TD className="text-right">
                    <Link className="text-sm text-brand hover:underline" to={`/instructor/rubrics/${r.id}`}>
                      Open
                    </Link>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Panel>
    </>
  );
}

function TreeView({ node, depth = 0 }: { node: Def; depth?: number }) {
  if (node.kind === "leaf") {
    return (
      <div
        className="rounded border border-border bg-surface-muted/50 px-3 py-2 text-sm"
        style={{ marginLeft: depth * 16 }}
      >
        <p>
          <span className="font-medium">Expected:</span>{" "}
          {(node.expected as string[]).map((r) => label(RESPONSE_LABELS, r)).join(" or ")}
          {node.acceptable?.length ? (
            <span className="text-ink-muted">
              {" "}
              · acceptable: {(node.acceptable as string[]).map((r) => label(RESPONSE_LABELS, r)).join(", ")}
            </span>
          ) : null}
        </p>
        <p className="text-xs text-ink-muted">{node.rationale}</p>
      </div>
    );
  }
  const c = node.condition;
  return (
    <div className="space-y-1.5" style={{ marginLeft: depth * 16 }}>
      <p className="text-sm">
        <span className="text-ink-subtle">If</span>{" "}
        <span className="font-medium">{String(c.fact).replace(/_/g, " ")}</span> {c.op}{" "}
        {JSON.stringify(c.value)}
      </p>
      <div className="space-y-1.5 border-l border-border pl-3">
        <p className="text-2xs uppercase tracking-wide text-ink-subtle">Yes</p>
        <TreeView node={node.if_true} depth={0} />
        <p className="text-2xs uppercase tracking-wide text-ink-subtle">No</p>
        <TreeView node={node.if_false} depth={0} />
      </div>
    </div>
  );
}

export function RubricDetailPage() {
  const { rubricId = "" } = useParams();
  const navigate = useNavigate();
  const st = useAsync((sig) => api.get<RubricSummary>(`/rubrics/${rubricId}`, sig), [rubricId]);
  const [draft, setDraft] = useState<Def | null>(null);
  const [json, setJson] = useState("");
  const [issues, setIssues] = useState<ValidationIssue[]>([]);
  const [msg, setMsg] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  if (st.loading) return <LoadingState rows={6} />;
  if (st.error || !st.data?.definition) return <ErrorState error={st.error} onRetry={st.reload} />;
  const r = st.data;
  const def = (draft ?? r.definition) as Def;
  const editing = draft !== null;
  const weightSum = DIMENSION_ORDER.reduce((a, d) => a + Number(def.weights[d] ?? 0), 0);

  const set = (path: string[], v: unknown) => {
    const next: Def = structuredClone(def);
    let o = next;
    for (const p of path.slice(0, -1)) o = o[p];
    o[path[path.length - 1]!] = v;
    setDraft(next);
  };

  async function saveVersion(definition: Def) {
    setBusy(true);
    setMsg(null);
    setIssues([]);
    try {
      const saved = await api.post<RubricSummary>(`/rubrics/key/${r.key}/versions`, { definition });
      setDraft(null);
      navigate(`/instructor/rubrics/${saved.id}`);
      setMsg({ tone: "success", text: `Saved as version ${saved.version}.` });
    } catch (err) {
      if (err instanceof ApiError && Array.isArray(err.details)) setIssues(err.details as ValidationIssue[]);
      setMsg({ tone: "danger", text: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow={
          <Link to="/instructor/rubrics" className="hover:underline">
            Scoring rubrics
          </Link>
        }
        title={`${r.name} (v${r.version})`}
        description={r.description}
        actions={
          editing ? (
            <>
              <Button variant="secondary" onClick={() => setDraft(null)}>
                Discard changes
              </Button>
              <Button disabled={busy || Math.abs(weightSum - 1) > 1e-6} onClick={() => saveVersion(def)}>
                Save as new version
              </Button>
            </>
          ) : (
            <Button variant="secondary" onClick={() => setDraft(structuredClone(r.definition as Def))}>
              Edit as new version
            </Button>
          )
        }
      />
      {msg ? (
        <Alert tone={msg.tone} className="mb-3">
          {msg.text}
        </Alert>
      ) : null}
      {issues.length ? (
        <Alert tone="danger" className="mb-3" title="Rubric failed validation">
          <ul className="list-disc pl-4 text-xs">
            {issues.map((i) => (
              <li key={i.path + i.message}>
                {i.path}: {i.message}
              </li>
            ))}
          </ul>
        </Alert>
      ) : null}
      <Tabs defaultValue="weights">
        <TabsList className="mb-4">
          <TabsTrigger value="weights">Weights and thresholds</TabsTrigger>
          <TabsTrigger value="tree">Decision tree</TabsTrigger>
          <TabsTrigger value="procedure">Procedure rules</TabsTrigger>
          <TabsTrigger value="json" onClick={() => setJson(JSON.stringify(def, null, 2))}>
            Definition (JSON)
          </TabsTrigger>
          <TabsTrigger value="history">Versions</TabsTrigger>
        </TabsList>
        <TabsContent value="weights" className="grid gap-4 lg:grid-cols-2">
          <Panel>
            <PanelHeader
              title="Dimension weights"
              description={`Must sum to 1.0. Current total: ${weightSum.toFixed(3)}.`}
            />
            <Table>
              <THead>
                <TR>
                  <TH>Dimension</TH>
                  <TH className="w-28">Weight</TH>
                </TR>
              </THead>
              <TBody>
                {DIMENSION_ORDER.map((d) => (
                  <TR key={d}>
                    <TD>
                      <p className="font-medium">{DIMENSION_LABELS[d]}</p>
                      <p className="text-xs text-ink-subtle">{DIMENSION_HELP[d]}</p>
                    </TD>
                    <TD>
                      {editing ? (
                        <Input
                          aria-label={`${DIMENSION_LABELS[d]} weight`}
                          type="number"
                          step="0.01"
                          min={0}
                          max={1}
                          value={def.weights[d]}
                          onChange={(e) => set(["weights", d], Number(e.target.value))}
                        />
                      ) : (
                        <span className="tabular">{def.weights[d]}</span>
                      )}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            {editing && Math.abs(weightSum - 1) > 1e-6 ? (
              <p className="px-4 py-2 text-xs text-danger">Weights must sum to 1.0 before saving.</p>
            ) : null}
          </Panel>
          <Panel>
            <PanelHeader title="Thresholds" />
            <PanelBody className="space-y-3">
              {editing ? (
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Pass mark (%)">
                    <Input
                      type="number"
                      value={def.pass_mark}
                      onChange={(e) => set(["pass_mark"], Number(e.target.value))}
                    />
                  </Field>
                  <Field label="Weak-evidence threshold (0–1)">
                    <Input
                      type="number"
                      step="0.05"
                      value={def.uncertainty.evidence_threshold}
                      onChange={(e) => set(["uncertainty", "evidence_threshold"], Number(e.target.value))}
                    />
                  </Field>
                  <Field label="Timing: full credit within (s)">
                    <Input
                      type="number"
                      value={def.timing.target_s}
                      onChange={(e) => set(["timing", "target_s"], Number(e.target.value))}
                    />
                  </Field>
                  <Field label="Timing: no credit after (s)">
                    <Input
                      type="number"
                      value={def.timing.max_s}
                      onChange={(e) => set(["timing", "max_s"], Number(e.target.value))}
                    />
                  </Field>
                </div>
              ) : (
                <KeyValues
                  items={[
                    ["Pass mark", `${def.pass_mark}%`],
                    [
                      "Timing",
                      `Full credit within ${def.timing.target_s} s; none after ${def.timing.max_s} s; linear in between`,
                    ],
                    ...Object.entries(def.timing_overrides ?? {}).map(
                      ([k, v]) =>
                        [
                          `Timing (${k.replace(/_/g, " ")})`,
                          `${(v as Def).target_s} s / ${(v as Def).max_s} s`,
                        ] as [string, string],
                    ),
                    ["Weak evidence", `Classification evidence below ${def.uncertainty.evidence_threshold}`],
                    [
                      "Uncertainty credit",
                      `low ${def.uncertainty.credit_low_confidence}, medium ${def.uncertainty.credit_medium_confidence}, high and correct ${def.uncertainty.credit_high_confidence_correct}, high and wrong ${def.uncertainty.credit_high_confidence_wrong}`,
                    ],
                    [
                      "Partial credit",
                      (def.partial_credit as Def[])
                        .map((p) => `${p.true_class} as ${p.given}: ${p.credit}`)
                        .join("; ") || "None",
                    ],
                  ]}
                />
              )}
            </PanelBody>
          </Panel>
        </TabsContent>
        <TabsContent value="tree">
          <Panel>
            <PanelHeader
              title="Decision tree"
              description="Determines the expected training response for each track from simulated ground truth. Edit the tree in the JSON tab."
            />
            <PanelBody>
              <TreeView node={def.decision_tree} />
            </PanelBody>
          </Panel>
        </TabsContent>
        <TabsContent value="procedure">
          <Panel>
            <PanelHeader title="Procedure rules" />
            <ul className="divide-y divide-border">
              {(def.procedure_rules as Def[]).map((p) => (
                <li key={p.kind} className="px-4 py-2.5 text-sm">
                  <p className="font-medium">{p.description}</p>
                  <p className="text-xs text-ink-subtle">
                    {p.kind}
                    {p.evidence_threshold !== undefined
                      ? ` · evidence threshold ${p.evidence_threshold}`
                      : ""}
                    {p.min_observations !== undefined ? ` · minimum ${p.min_observations} observations` : ""}
                  </p>
                </li>
              ))}
            </ul>
          </Panel>
        </TabsContent>
        <TabsContent value="json">
          <Panel>
            <PanelHeader
              title="Definition (JSON)"
              description="Save validates the full rubric (weights, tree node ids, operators) and creates a new version."
            />
            <PanelBody className="space-y-3">
              <Textarea
                aria-label="Rubric definition JSON"
                spellCheck={false}
                className="min-h-[480px] text-xs"
                value={json}
                onChange={(e) => setJson(e.target.value)}
              />
              <Button
                disabled={busy}
                onClick={() => {
                  try {
                    saveVersion(JSON.parse(json));
                  } catch (err) {
                    setMsg({ tone: "danger", text: errorMessage(err) });
                  }
                }}
              >
                Save JSON as new version
              </Button>
            </PanelBody>
          </Panel>
        </TabsContent>
        <TabsContent value="history">
          <Panel>
            <PanelHeader title="Versions" />
            <Table>
              <THead>
                <TR>
                  <TH>Version</TH>
                  <TH>Created</TH>
                  <TH>
                    <span className="sr-only">Actions</span>
                  </TH>
                </TR>
              </THead>
              <TBody>
                {r.versions?.map((v) => (
                  <TR key={v.id}>
                    <TD>v{v.version}</TD>
                    <TD className="text-xs">{formatDateTime(v.created_at)}</TD>
                    <TD className="text-right">
                      {v.id === r.id ? (
                        <span className="text-xs text-ink-subtle">Viewing</span>
                      ) : (
                        <Link
                          className="text-sm text-brand hover:underline"
                          to={`/instructor/rubrics/${v.id}`}
                        >
                          Open
                        </Link>
                      )}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </Panel>
        </TabsContent>
      </Tabs>
    </>
  );
}
