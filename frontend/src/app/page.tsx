"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BookOpenCheck,
  CheckCircle2,
  ExternalLink,
  FileText,
  Gavel,
  Loader2,
  RefreshCw,
  Scale,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  XCircle,
} from "lucide-react";
import { api } from "@/lib/api";
import type {
  AuditResponse,
  ComplianceGap,
  ContractDocument,
  FilingPackage,
  JurisdictionStatus,
  RadarStatus,
  RegulatoryEvent,
  RemediationPatch,
} from "@/lib/types";

const STATE_NAMES: Record<string, string> = { TX: "Texas", CA: "California", NY: "New York", FED: "Federal" };

const RADAR_STYLES: Record<RadarStatus, { ring: string; dot: string; label: string }> = {
  GREEN: { ring: "border-emerald-500/40 bg-emerald-500/5", dot: "bg-emerald-400", label: "Compliant" },
  AMBER: { ring: "border-amber-500/40 bg-amber-500/5", dot: "bg-amber-400", label: "Review" },
  RED: { ring: "border-rose-500/40 bg-rose-500/5", dot: "bg-rose-500", label: "Violation" },
  UNKNOWN: { ring: "border-slate-700 bg-slate-800/30", dot: "bg-slate-500", label: "No rules" },
};

const RULE_LABEL: Record<string, string> = {
  FEE_CAP: "fee cap",
  USURY_CAP: "rate ceiling",
  DISCLOSURE_MANDATE: "disclosure",
  REPORTING_DEADLINE: "reporting",
  PREPAYMENT_PENALTY: "prepayment",
  TERM_LIMIT: "loan term",
};

type Tone = "slate" | "rose" | "amber" | "emerald" | "sky";

function Pill({ children, tone = "slate" }: { children: React.ReactNode; tone?: Tone }) {
  const tones: Record<Tone, string> = {
    slate: "bg-slate-800 text-slate-300 border-slate-700",
    rose: "bg-rose-500/10 text-rose-300 border-rose-500/30",
    amber: "bg-amber-500/10 text-amber-300 border-amber-500/30",
    emerald: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
    sky: "bg-sky-500/10 text-sky-300 border-sky-500/30",
  };
  return <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium tracking-wide ${tones[tone]}`}>{children}</span>;
}

function severityTone(s: ComplianceGap["severity"]): Tone {
  return s === "CRITICAL" ? "rose" : s === "WARNING" ? "amber" : "emerald";
}

function RadarCard({ s, active, onClick }: { s: JurisdictionStatus; active: boolean; onClick: () => void }) {
  const st = RADAR_STYLES[s.status];
  return (
    <button
      onClick={onClick}
      className={`group flex flex-col gap-2 rounded-xl border p-4 text-left transition hover:border-slate-400/60 ${st.ring} ${active ? "ring-2 ring-sky-400/60" : ""}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-2xl font-semibold tracking-tight">{s.jurisdiction}</span>
        <span className={`h-3 w-3 rounded-full ${st.dot} ${s.status === "RED" ? "animate-pulse" : ""}`} />
      </div>
      <div className="text-sm text-slate-400">{STATE_NAMES[s.jurisdiction]}</div>
      <div className="mt-1 flex items-center gap-2 text-xs">
        <span className="font-medium text-slate-200">{st.label}</span>
        <span className="text-slate-500">·</span>
        <span className="text-slate-400">{s.active_rules} rules</span>
      </div>
      <div className="flex flex-wrap gap-2 text-xs">
        {s.critical_count > 0 && <Pill tone="rose">{s.critical_count} critical</Pill>}
        {s.warning_count > 0 && <Pill tone="amber">{s.warning_count} warning</Pill>}
        {s.compliant_count > 0 && <Pill tone="emerald">{s.compliant_count} passed</Pill>}
        {s.critical_count === 0 && s.warning_count === 0 && s.status !== "UNKNOWN" && <Pill tone="emerald">clean</Pill>}
      </div>
    </button>
  );
}

function highlightNumbers(text: string, tone: "rose" | "emerald") {
  const parts = text.split(/(\$\s?\d[\d,]*(?:\.\d+)?|\d+(?:\.\d+)?\s?(?:percent|%)|(?:five|ten|fifteen|sixteen|twenty-five|thirty-six)\s(?:percent|per centum|cents)|\(\d+\)\s*(?:calendar\s)?(?:hours?|days?)|\d+(?:st|nd|rd|th)?\s*(?:hours?|days?|months?)|_{3,})/gi);
  const cls = tone === "rose" ? "bg-rose-500/25 text-rose-100" : "bg-emerald-500/25 text-emerald-100";
  return parts.map((p, i) =>
    /^(\$\s?\d|\d+(?:\.\d+)?\s?(?:percent|%)|(?:five|ten|fifteen|sixteen|twenty-five|thirty-six)\s|\(\d+\)|\d+(?:st|nd|rd|th)?\s*(?:hours?|days?|months?)|_{3,})/i.test(p) ? (
      <mark key={i} className={`rounded px-0.5 ${cls}`}>
        {p}
      </mark>
    ) : (
      <span key={i}>{p}</span>
    ),
  );
}

function GroundingBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1 text-xs ${ok ? "text-emerald-300" : "text-rose-300"}`}>
      {ok ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
      {label}
    </span>
  );
}

function VerificationBadge({ ev }: { ev: RegulatoryEvent | undefined }) {
  if (!ev) return null;
  const v = ev.verification;
  const tone: Tone = v.status === "MATCH" ? "emerald" : v.status === "PARTIAL" ? "amber" : v.status === "MISMATCH" ? "rose" : "slate";
  return (
    <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
      <BookOpenCheck className="h-3.5 w-3.5 text-slate-500" />
      <Pill tone={tone}>source {v.status.toLowerCase()}</Pill>
      <span>machine confidence {Math.round(v.confidence * 100)}%</span>
      <span className="text-slate-500">·</span>
      <span className={v.verified_by ? "text-emerald-300" : "text-amber-300"}>{v.verified_by ? `human-verified by ${v.verified_by}` : "not yet human-verified"}</span>
      {v.source_url && (
        <a href={v.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sky-300 hover:underline">
          primary source <ExternalLink className="h-3 w-3" />
        </a>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [documents, setDocuments] = useState<ContractDocument[]>([]);
  const [doc, setDoc] = useState<ContractDocument | null>(null);
  const [events, setEvents] = useState<RegulatoryEvent[]>([]);
  const [audit, setAudit] = useState<AuditResponse | null>(null);
  const [mode, setMode] = useState<string>("");
  const [stateFilter, setStateFilter] = useState<string | null>(null);
  const [selectedGapId, setSelectedGapId] = useState<string | null>(null);
  const [patch, setPatch] = useState<RemediationPatch | null>(null);
  const [override, setOverride] = useState<string>("");
  const [auditor, setAuditor] = useState<string>("bryce.f");
  const [filings, setFilings] = useState<FilingPackage[]>([]);
  const [busy, setBusy] = useState<"boot" | "audit" | "patch" | "apply" | null>("boot");
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [showPassed, setShowPassed] = useState(false);

  const runAudit = useCallback(async (document: ContractDocument) => {
    setBusy("audit");
    setError(null);
    try {
      const res = await api.audit(document);
      setAudit(res);
      setMode(res.analysis_mode);
      setSelectedGapId((prev) => {
        const open = res.gaps.filter((g) => g.severity !== "COMPLIANT");
        if (prev && open.some((g) => g.gap_id === prev)) return prev;
        const first = open.find((g) => g.severity === "CRITICAL") ?? open[0];
        return first?.gap_id ?? null;
      });
      setPatch(null);
      setOverride("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [docs, ev, h] = await Promise.all([api.documents(), api.events(), api.health()]);
        setDocuments(docs);
        setEvents(ev);
        setMode(h.mode);
        const first = docs[0];
        setDoc(first);
        if (first) await runAudit(first);
        else setBusy(null);
      } catch (e) {
        setError(`Backend unreachable. Start it with "uvicorn main:app --port 8000" in /backend. (${(e as Error).message})`);
        setBusy(null);
      }
    })();
  }, [runAudit]);

  const selectDocument = async (id: string) => {
    const d = documents.find((x) => x.document_id === id);
    if (!d) return;
    setDoc(d);
    setFilings([]);
    setStateFilter(null);
    await runAudit(d);
  };

  const allGaps = audit?.gaps ?? [];
  const gaps = useMemo(() => {
    const rank = { CRITICAL: 0, WARNING: 1, COMPLIANT: 2 } as const;
    const open = allGaps
      .filter((g) => g.severity !== "COMPLIANT")
      .sort((a, b) => rank[a.severity] - rank[b.severity] || a.jurisdiction.localeCompare(b.jurisdiction) || a.target_clause_id.localeCompare(b.target_clause_id));
    return stateFilter ? open.filter((g) => g.jurisdiction === stateFilter) : open;
  }, [allGaps, stateFilter]);
  const passed = useMemo(() => {
    const ok = allGaps.filter((g) => g.severity === "COMPLIANT");
    return stateFilter ? ok.filter((g) => g.jurisdiction === stateFilter) : ok;
  }, [allGaps, stateFilter]);

  const selected: ComplianceGap | null = useMemo(() => gaps.find((g) => g.gap_id === selectedGapId) ?? gaps[0] ?? null, [gaps, selectedGapId]);
  const selectedEvent = useMemo(() => (selected ? events.find((e) => e.statute_citation === selected.statute_citation) : undefined), [events, selected]);

  const generatePatch = async () => {
    if (!selected || !doc) return;
    setBusy("patch");
    setError(null);
    try {
      const p = await api.preview(selected.gap_id, doc.document_id);
      setPatch(p);
      setOverride(p.redlined_text);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const applyPatch = async (decision: "APPROVE" | "REJECT") => {
    if (!selected || !doc) return;
    setBusy("apply");
    setError(null);
    try {
      const res = await api.apply({
        gap_id: selected.gap_id,
        document_id: doc.document_id,
        auditor_id: auditor || "anonymous",
        decision,
        auditor_override_text: decision === "APPROVE" && patch && override.trim() !== patch.redlined_text.trim() ? override : undefined,
      });
      if (res.filing_package) setFilings((f) => [res.filing_package as FilingPackage, ...f]);
      if (res.updated_document) {
        setDoc(res.updated_document);
        setToast(`Clause ${selected.target_clause_id} amended and filing package ${res.filing_package?.package_id} generated.`);
        await runAudit(res.updated_document);
      } else {
        setToast(`Patch for ${selected.target_clause_id} rejected by ${auditor}.`);
        setPatch(null);
      }
      setTimeout(() => setToast(null), 6000);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const criticalTotal = allGaps.filter((g) => g.severity === "CRITICAL").length;

  return (
    <main className="mx-auto max-w-[1500px] px-6 py-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-300">
            <ShieldCheck className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Certo</h1>
            <p className="text-xs text-slate-400">Continuous compliance · multi-state consumer lending</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <select
            value={doc?.document_id ?? ""}
            onChange={(e) => selectDocument(e.target.value)}
            disabled={busy !== null}
            className="max-w-[360px] rounded-md border border-slate-700 bg-ink-950 px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-sky-500"
          >
            {documents.map((d) => (
              <option key={d.document_id} value={d.document_id}>
                {d.title}
              </option>
            ))}
          </select>
          <Pill tone={mode === "llm" ? "sky" : "slate"}>
            <Sparkles className="mr-1 h-3 w-3" /> engine: {mode || "…"}
          </Pill>
          <Pill tone="slate">{events.length} active rules</Pill>
          <Pill tone={criticalTotal ? "rose" : "emerald"}>{criticalTotal} critical gaps</Pill>
          <button
            onClick={() => doc && runAudit(doc)}
            disabled={!doc || busy !== null}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-50"
          >
            {busy === "audit" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Re-audit
          </button>
        </div>
      </header>

      {doc?.source_url && (
        <p className="mb-4 flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <FileText className="h-3.5 w-3.5" />
          <span className="text-slate-400">{doc.source_type}</span>
          <a href={doc.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sky-300 hover:underline">
            verbatim source <ExternalLink className="h-3 w-3" />
          </a>
          <span>· {doc.clauses.length} clauses parsed</span>
        </p>
      )}

      {error && (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}
      {toast && (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm text-emerald-200">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{toast}</span>
        </div>
      )}

      <section className="mb-6">
        <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-300">
          <Activity className="h-4 w-4 text-sky-300" /> State Compliance Radar
          {stateFilter && (
            <button onClick={() => setStateFilter(null)} className="ml-2 text-xs text-sky-300 hover:underline">
              clear filter
            </button>
          )}
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {(audit?.radar ?? (["TX", "CA", "NY"] as const).map((j) => ({ jurisdiction: j, status: "UNKNOWN" as RadarStatus, critical_count: 0, warning_count: 0, compliant_count: 0, active_rules: 0 }))).map((s) => (
            <RadarCard key={s.jurisdiction} s={s} active={stateFilter === s.jurisdiction} onClick={() => setStateFilter((f) => (f === s.jurisdiction ? null : s.jurisdiction))} />
          ))}
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[340px_1fr]">
        <aside className="rounded-xl border border-slate-800 bg-ink-900/60">
          <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3 text-sm font-medium text-slate-300">
            <span className="flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-rose-300" /> Gap findings
            </span>
            <span className="text-xs text-slate-500">{gaps.length} open · {passed.length} passed</span>
          </div>
          <div className="max-h-[720px] overflow-y-auto">
            {busy === "boot" && (
              <div className="flex items-center gap-2 p-4 text-sm text-slate-400">
                <Loader2 className="h-4 w-4 animate-spin" /> Auditing agreement…
              </div>
            )}
            {busy !== "boot" && gaps.length === 0 && (
              <div className="p-4 text-sm text-emerald-300">
                <CheckCircle2 className="mb-1 h-5 w-5" />
                No open gaps{stateFilter ? ` for ${stateFilter}` : ""}. Document is compliant with all active rules.
              </div>
            )}
            {gaps.map((g) => (
              <button
                key={g.gap_id}
                onClick={() => {
                  setSelectedGapId(g.gap_id);
                  setPatch(null);
                  setOverride("");
                }}
                className={`block w-full border-b border-slate-800/70 px-4 py-3 text-left transition hover:bg-slate-800/50 ${selected?.gap_id === g.gap_id ? "bg-slate-800/70" : ""}`}
              >
                <div className="mb-1 flex items-center gap-2">
                  <Pill tone={severityTone(g.severity)}>{g.severity}</Pill>
                  <Pill tone="slate">{g.jurisdiction}</Pill>
                  <span className="ml-auto text-[11px] text-slate-500">{Math.round(g.confidence_score * 100)}%</span>
                </div>
                <div className="text-sm font-medium text-slate-200">{g.statute_citation}</div>
                <div className="text-xs text-slate-400">
                  {g.target_clause_id} · {RULE_LABEL[g.rule_type] ?? g.rule_type}
                </div>
              </button>
            ))}
            {passed.length > 0 && (
              <div className="border-t border-slate-800">
                <button onClick={() => setShowPassed((v) => !v)} className="flex w-full items-center gap-2 px-4 py-2 text-xs text-emerald-300 hover:bg-slate-800/40">
                  <CheckCircle2 className="h-3.5 w-3.5" /> {showPassed ? "Hide" : "Show"} {passed.length} passed checks
                </button>
                {showPassed &&
                  passed.map((g) => (
                    <div key={g.gap_id} className="border-t border-slate-800/60 px-4 py-2 text-xs text-slate-400">
                      <span className="text-emerald-300">{g.jurisdiction}</span> · {g.statute_citation} · {g.target_clause_id}
                      <div className="text-[11px] text-slate-500">{g.violation_reason}</div>
                    </div>
                  ))}
              </div>
            )}
          </div>
        </aside>

        <div className="flex flex-col gap-6">
          {selected ? (
            <>
              <section className="rounded-xl border border-slate-800 bg-ink-900/60">
                <div className="flex flex-wrap items-center gap-3 border-b border-slate-800 px-4 py-3">
                  <Scale className="h-4 w-4 text-sky-300" />
                  <span className="text-sm font-medium text-slate-300">Split Diff Viewer</span>
                  <Pill tone="sky">{selected.statute_citation}</Pill>
                  <Pill tone="slate">{STATE_NAMES[selected.jurisdiction]}</Pill>
                  <Pill tone={severityTone(selected.severity)}>{selected.severity}</Pill>
                  <span className="ml-auto text-xs text-slate-400">
                    threshold: <span className="text-slate-200">{selected.statutory_threshold_violated ?? "see statute"}</span>
                  </span>
                </div>
                <div className="grid grid-cols-1 divide-y divide-slate-800 md:grid-cols-2 md:divide-x md:divide-y-0">
                  <div className="p-4">
                    <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-emerald-300">
                      <Gavel className="h-3.5 w-3.5" /> Statutory law source
                    </div>
                    <p className="font-mono text-[13px] leading-relaxed text-slate-300">“{highlightNumbers(selected.statutory_source_snippet, "emerald")}”</p>
                    <p className="mt-3 text-xs text-slate-500">
                      {selectedEvent?.agency} · effective {selectedEvent?.effective_date}
                      {selectedEvent?.applicability ? ` · applies to ${selectedEvent.applicability}` : ""}
                    </p>
                    <div className="mt-2">
                      <VerificationBadge ev={selectedEvent} />
                    </div>
                  </div>
                  <div className="p-4">
                    <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-rose-300">
                      <FileText className="h-3.5 w-3.5" /> Contract clause · {selected.target_clause_id}
                    </div>
                    <p className="max-h-72 overflow-y-auto font-mono text-[13px] leading-relaxed text-slate-300">{highlightNumbers(selected.target_clause_text, "rose")}</p>
                  </div>
                </div>
                <div className="border-t border-slate-800 px-4 py-3 text-sm text-slate-300">
                  <span className={`font-medium ${selected.severity === "CRITICAL" ? "text-rose-300" : "text-amber-300"}`}>{selected.severity === "CRITICAL" ? "Why it fails: " : "What to check: "}</span>
                  {selected.violation_reason}
                </div>
              </section>

              <section className="rounded-xl border border-slate-800 bg-ink-900/60">
                <div className="flex flex-wrap items-center gap-3 border-b border-slate-800 px-4 py-3">
                  <Sparkles className="h-4 w-4 text-amber-300" />
                  <span className="text-sm font-medium text-slate-300">One-Click Remediation Studio</span>
                  <div className="ml-auto flex items-center gap-2">
                    <label className="text-xs text-slate-500">auditor</label>
                    <input
                      value={auditor}
                      onChange={(e) => setAuditor(e.target.value)}
                      className="w-28 rounded-md border border-slate-700 bg-ink-950 px-2 py-1 text-xs text-slate-200 outline-none focus:border-sky-500"
                    />
                    <button
                      onClick={generatePatch}
                      disabled={busy !== null}
                      className="inline-flex items-center gap-1.5 rounded-md bg-amber-500/90 px-3 py-1.5 text-xs font-semibold text-ink-950 hover:bg-amber-400 disabled:opacity-50"
                    >
                      {busy === "patch" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                      Generate AI patch
                    </button>
                  </div>
                </div>

                {!patch ? (
                  <div className="p-4 text-sm text-slate-400">
                    <p className="mb-2">Deterministic draft (Agent B):</p>
                    <p className="max-h-60 overflow-y-auto rounded-md border border-slate-800 bg-ink-950 p-3 font-mono text-[13px] leading-relaxed text-slate-300">{highlightNumbers(selected.suggested_patch, "emerald")}</p>
                    <p className="mt-2 text-xs text-slate-500">Generate the AI patch to run Agent C: grounded redline plus LLM-as-a-judge verification.</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-[1fr_280px]">
                    <div>
                      <div className="mb-1 text-xs font-medium uppercase tracking-wider text-slate-400">Redline (editable, human in the loop)</div>
                      <textarea
                        value={override}
                        onChange={(e) => setOverride(e.target.value)}
                        rows={8}
                        className="w-full rounded-md border border-slate-700 bg-ink-950 p-3 font-mono text-[13px] leading-relaxed text-slate-200 outline-none focus:border-sky-500"
                      />
                      <p className="mt-2 text-xs text-slate-400">
                        <span className="font-medium text-slate-300">Rationale: </span>
                        {patch.change_rationale}
                      </p>
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <button
                          onClick={() => applyPatch("APPROVE")}
                          disabled={busy !== null || !patch.grounding.is_grounded}
                          title={patch.grounding.is_grounded ? "Apply to contract and generate filing package" : "Blocked: patch failed grounding verification"}
                          className="inline-flex items-center gap-1.5 rounded-md bg-emerald-500 px-4 py-2 text-sm font-semibold text-ink-950 hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          {busy === "apply" ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                          Approve &amp; Apply
                        </button>
                        <button
                          onClick={() => applyPatch("REJECT")}
                          disabled={busy !== null}
                          className="inline-flex items-center gap-1.5 rounded-md border border-slate-700 px-4 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800 disabled:opacity-50"
                        >
                          <XCircle className="h-4 w-4" /> Reject
                        </button>
                        {override.trim() !== patch.redlined_text.trim() && <Pill tone="amber">edited: will be re-verified on apply</Pill>}
                      </div>
                    </div>
                    <div className="rounded-md border border-slate-800 bg-ink-950 p-3">
                      <div className="mb-2 flex items-center justify-between">
                        <span className="text-xs font-medium uppercase tracking-wider text-slate-400">Grounding verifier</span>
                        <Pill tone={patch.grounding.is_grounded ? "emerald" : "rose"}>{patch.grounding.is_grounded ? "GROUNDED" : "REJECTED"}</Pill>
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <GroundingBadge ok={patch.grounding.cited_statute_present} label="Statute cited verbatim" />
                        <GroundingBadge ok={patch.grounding.numbers_match_statute} label="All numbers trace to statute" />
                        <GroundingBadge ok={patch.grounding.no_invented_obligations} label="No invented obligations" />
                      </div>
                      <div className="mt-3 text-[11px] leading-relaxed text-slate-500">{patch.grounding.judge_rationale}</div>
                      <div className="mt-2 text-[11px] text-slate-500">judge confidence {Math.round(patch.grounding.confidence * 100)}%</div>
                    </div>
                  </div>
                )}
              </section>
            </>
          ) : (
            busy !== "boot" && (
              <section className="flex flex-col items-center justify-center rounded-xl border border-slate-800 bg-ink-900/60 p-12 text-center">
                <ShieldCheck className="mb-3 h-10 w-10 text-emerald-300" />
                <p className="text-lg font-medium text-slate-200">All clear</p>
                <p className="text-sm text-slate-400">{doc?.title} has no open gaps against {events.length} active rules.</p>
              </section>
            )
          )}

          {filings.length > 0 && (
            <section className="rounded-xl border border-slate-800 bg-ink-900/60">
              <div className="flex items-center gap-2 border-b border-slate-800 px-4 py-3 text-sm font-medium text-slate-300">
                <FileText className="h-4 w-4 text-emerald-300" /> State filing packages
                <span className="ml-auto text-xs text-slate-500">{filings.length}</span>
              </div>
              <div className="divide-y divide-slate-800">
                {filings.map((f) => (
                  <details key={f.package_id} className="group px-4 py-3">
                    <summary className="flex cursor-pointer items-center gap-3 text-sm">
                      <Pill tone="emerald">{f.jurisdiction}</Pill>
                      <span className="font-medium text-slate-200">{f.statute_citation}</span>
                      <span className="text-xs text-slate-500">
                        {f.package_id} · {f.clause_id} · {f.auditor_id}
                      </span>
                    </summary>
                    <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                      <div>
                        <div className="mb-1 text-[11px] uppercase tracking-wider text-rose-300">Before</div>
                        <p className="rounded-md border border-slate-800 bg-ink-950 p-2 font-mono text-xs text-slate-400 line-through decoration-rose-500/60">{f.before_text}</p>
                      </div>
                      <div>
                        <div className="mb-1 text-[11px] uppercase tracking-wider text-emerald-300">After</div>
                        <p className="rounded-md border border-slate-800 bg-ink-950 p-2 font-mono text-xs text-slate-200">{f.after_text}</p>
                      </div>
                    </div>
                    <p className="mt-3 text-xs text-slate-400">
                      <span className="font-medium text-slate-300">Attestation ({f.agency}): </span>
                      {f.attestation}
                    </p>
                  </details>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>

      <footer className="mt-8 text-center text-[11px] text-slate-600">
        Contracts are verbatim public documents; statute excerpts are verbatim from official state sites. Machine-checked, not yet human-verified. Not legal advice.
      </footer>
    </main>
  );
}
