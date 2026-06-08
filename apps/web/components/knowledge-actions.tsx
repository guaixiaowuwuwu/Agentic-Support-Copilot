"use client";

import type { Document } from "@support-copilot/shared";
import { DatabaseZap, PlusCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { apiPost } from "@/lib/api";
import { dictionaries, normalizeLocale, type Locale } from "@/lib/i18n";

type IngestResponse = {
  tenant_id: string;
  updated_chunks: number;
};

export function KnowledgeActions({ locale, tenantId }: { locale?: Locale; tenantId: string }) {
  const router = useRouter();
  const activeLocale = normalizeLocale(locale);
  const dict = dictionaries[activeLocale].knowledge;
  const [error, setError] = useState("");
  const [result, setResult] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setResult("");
    setIsCreating(true);

    const form = new FormData(event.currentTarget);
    const requiredPermissions = String(form.get("required_permissions") ?? "")
      .split(",")
      .map((item) => item.trim().toLowerCase())
      .filter(Boolean);
    try {
      await apiPost<Document>("/api/knowledge/documents", {
        tenant_id: tenantId,
        title: form.get("title"),
        source_type: form.get("source_type"),
        uri: form.get("uri"),
        content: form.get("content"),
        product_line: form.get("product_line") || null,
        version: form.get("version") || null,
        required_permissions: requiredPermissions,
        valid_from: form.get("valid_from") || null,
        valid_until: form.get("valid_until") || null,
        source_system: form.get("source_system") || null
      });
      event.currentTarget.reset();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : dict.createFailed);
    } finally {
      setIsCreating(false);
    }
  }

  async function ingest() {
    setError("");
    setResult("");
    setIsIngesting(true);
    try {
      const response = await apiPost<IngestResponse>("/api/knowledge/embeddings/ingest", {
        tenant_id: tenantId
      });
      setResult(dict.ingestResult.replace("{count}", String(response.updated_chunks)));
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : dict.ingestFailed);
    } finally {
      setIsIngesting(false);
    }
  }

  return (
    <div className="knowledge-actions">
      <form className="ticket-form" onSubmit={submit}>
        <div className="form-row">
          <label>
            {dict.tableTitle}
            <input name="title" required />
          </label>
          <label>
            {dict.source}
            <select name="source_type" defaultValue="knowledge_base">
              <option value="knowledge_base">knowledge_base</option>
              <option value="runbook">runbook</option>
              <option value="historical_ticket">historical_ticket</option>
            </select>
          </label>
          <label>
            {dict.uri}
            <input name="uri" required />
          </label>
        </div>
        <div className="form-row">
          <label>
            {dict.productLine}
            <input name="product_line" placeholder="api" />
          </label>
          <label>
            {dict.version}
            <input name="version" placeholder="v1" />
          </label>
          <label>
            {dict.sourceSystem}
            <input name="source_system" placeholder="confluence" />
          </label>
          <label>
            {dict.requiredPermissions}
            <input name="required_permissions" placeholder="support_agent" />
          </label>
          <label>
            {dict.validFrom}
            <input name="valid_from" placeholder="2026-01-01T00:00:00Z" />
          </label>
          <label>
            {dict.validUntil}
            <input name="valid_until" placeholder="2030-01-01T00:00:00Z" />
          </label>
        </div>
        <label>
          {dict.content}
          <textarea name="content" rows={5} required />
        </label>
        <div className="form-footer">
          {error ? <span className="form-error" role="alert">{error}</span> : result ? <span className="form-success">{result}</span> : <span />}
          <div className="button-pair">
            <button type="button" className="icon-button" onClick={ingest} disabled={isIngesting} title={dict.ingest}>
              <DatabaseZap size={16} />
              <span>{isIngesting ? dict.ingesting : dict.ingest}</span>
            </button>
            <button type="submit" className="button button-primary" disabled={isCreating} title={dict.create}>
              <PlusCircle size={16} />
              <span>{isCreating ? dict.creating : dict.create}</span>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
