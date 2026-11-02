/** LLM provider selection via env (LLM_PROVIDER=google|groq|openai, LLM_MODEL optional). */
import { createGoogleGenerativeAI } from "@ai-sdk/google";
import { createGroq } from "@ai-sdk/groq";
import { createOpenAI } from "@ai-sdk/openai";

const DEFAULT_MODEL = { google: "gemini-2.5-flash", groq: "llama-3.3-70b-versatile", openai: "gpt-4o-mini" } as const;
type Provider = keyof typeof DEFAULT_MODEL;

export function llmConfigured(): boolean {
  const p = (process.env.LLM_PROVIDER ?? "google") as Provider;
  return Boolean({ google: process.env.GOOGLE_GENERATIVE_AI_API_KEY, groq: process.env.GROQ_API_KEY, openai: process.env.OPENAI_API_KEY }[p]);
}

export function model() {
  const p = (process.env.LLM_PROVIDER ?? "google") as Provider;
  const id = process.env.LLM_MODEL || DEFAULT_MODEL[p];
  if (p === "groq") return createGroq({ apiKey: process.env.GROQ_API_KEY })(id);
  if (p === "openai") return createOpenAI({ apiKey: process.env.OPENAI_API_KEY })(id);
  return createGoogleGenerativeAI({ apiKey: process.env.GOOGLE_GENERATIVE_AI_API_KEY })(id);
}
