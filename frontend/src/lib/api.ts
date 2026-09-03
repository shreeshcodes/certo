import type { AuditResponse, ContractDocument, RegulatoryEvent, RemediationPatch, RemediationResponse } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<{ status: string; mode: string; events: number; store: string }>("/api/health"),
  events: () => request<RegulatoryEvent[]>("/api/events"),
  documents: () => request<ContractDocument[]>("/api/documents"),
  sampleDocument: () => request<ContractDocument>("/api/documents/sample"),
  audit: (document: ContractDocument) =>
    request<AuditResponse>("/api/audit/document", { method: "POST", body: JSON.stringify({ document }) }),
  preview: (gap_id: string, document_id: string) =>
    request<RemediationPatch>(
      `/api/remediate/preview?gap_id=${encodeURIComponent(gap_id)}&document_id=${encodeURIComponent(document_id)}`,
      { method: "POST" },
    ),
  apply: (body: { gap_id: string; document_id: string; auditor_id: string; decision: "APPROVE" | "REJECT"; auditor_override_text?: string }) =>
    request<RemediationResponse>("/api/remediate/patch", { method: "POST", body: JSON.stringify(body) }),
};
