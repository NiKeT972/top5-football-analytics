import type { Metadata } from "next";
import { AskChat } from "@/components/ask-chat";
import { PageHeader } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "Ask",
  description: "Ask football data questions in plain English. An AI agent writes and runs a read-only SQL query and shows its work.",
};

export default function AskPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="Ask" subtitle="Plain-English questions → one read-only SQL query → an answer, a table and the SQL it ran." />
      <AskChat />
      <p className="mt-6 text-xs text-fg-3">Guardrails: single SELECT over documented views, parsed before running, 5-second timeout, 200-row limit, daily request cap. The model can be wrong; check the SQL.</p>
    </div>
  );
}
