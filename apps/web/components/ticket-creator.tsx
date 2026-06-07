"use client";

import type { AgentRun, Ticket } from "@support-copilot/shared";
import { PlusCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { apiPost, userContext } from "@/lib/api";
import { dictionaries, normalizeLocale, type Locale } from "@/lib/i18n";

export function TicketCreator({ locale }: { locale?: Locale }) {
  const router = useRouter();
  const activeLocale = normalizeLocale(locale);
  const dict = dictionaries[activeLocale].ticketForm;
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);

    const form = new FormData(event.currentTarget);
    try {
      const ticket = await apiPost<Ticket>("/api/tickets", {
        tenant_id: form.get("tenant_id") || "acme",
        customer_name: form.get("customer_name") || dict.defaultCustomer,
        channel: form.get("channel") || "email",
        subject: form.get("subject"),
        description: form.get("description")
      });
      await apiPost<AgentRun>(`/api/runs/${ticket.id}/start`);
      router.push(`/tickets/${ticket.id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : dict.createFailed);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="ticket-form" onSubmit={submit}>
      <div className="form-row">
        <label>
          {dict.tenant}
          <input name="tenant_id" value={userContext.tenant_id} readOnly />
        </label>
        <label>
          {dict.customer}
          <input name="customer_name" defaultValue={dict.defaultCustomer} />
        </label>
        <label>
          {dict.channel}
          <select name="channel" defaultValue="email">
            <option value="email">email</option>
            <option value="portal">portal</option>
            <option value="slack">slack</option>
          </select>
        </label>
      </div>
      <label>
        {dict.subject}
        <input name="subject" defaultValue={dict.defaultSubject} required />
      </label>
      <label>
        {dict.description}
        <textarea
          name="description"
          defaultValue={dict.defaultDescription}
          required
          rows={4}
        />
      </label>
      <div className="form-footer">
        {error ? <span className="form-error">{error}</span> : <span />}
        <button type="submit" className="button button-primary" disabled={isSubmitting} title={dict.createTitle}>
          <PlusCircle size={16} />
          {isSubmitting ? dict.running : dict.create}
        </button>
      </div>
    </form>
  );
}
