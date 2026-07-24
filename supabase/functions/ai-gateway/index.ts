type ChatMessage = {
  role: "user" | "assistant" | "system";
  content: string;
};

type GatewayRequest = {
  action?: "providers" | "chat";
  messages?: ChatMessage[];
  model?: string;
  provider?: string;
  max_tokens?: number;
  reasoning_effort?: "low" | "medium" | "high";
};

const OPENAI_MODELS = new Set(["gpt-5.6-sol", "gpt-5.6-terra"]);
const OPENROUTER_MODELS = new Set([
  "openrouter/auto",
  "openrouter/free",
  "anthropic/claude-sonnet-5",
  "anthropic/claude-opus-5",
  "openai/gpt-5.6-terra",
  "google/gemini-3.6-flash",
  "x-ai/grok-4.5",
]);
const SYSTEM_INSTRUCTIONS =
  "You are Archon, an expert app-building assistant. Give practical, safe, concise guidance and produce complete code when asked.";
const jsonHeaders = { "Content-Type": "application/json" };

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: jsonHeaders });
}

function extractText(payload: Record<string, unknown>): string {
  if (typeof payload.output_text === "string") return payload.output_text;

  const output = Array.isArray(payload.output) ? payload.output : [];
  return output
    .flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const content = (item as { content?: unknown }).content;
      return Array.isArray(content) ? content : [];
    })
    .filter((item) => item && typeof item === "object")
    .map((item) => {
      const value = item as { type?: unknown; text?: unknown };
      return value.type === "output_text" && typeof value.text === "string"
        ? value.text
        : "";
    })
    .filter(Boolean)
    .join("\n");
}

Deno.serve(async (request: Request) => {
  if (request.method !== "POST") {
    return json({ error: "Method not allowed" }, 405);
  }

  let body: GatewayRequest;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid JSON body" }, 400);
  }

  if (body.action === "providers") {
    return json({
      providers: [
        {
          id: "openai",
          name: "OpenAI",
          configured: Boolean(Deno.env.get("OPENAI_API_KEY")),
          requiresKey: true,
          models: [
            { id: "gpt-5.6-sol", name: "GPT-5.6 Sol" },
            { id: "gpt-5.6-terra", name: "GPT-5.6 Terra" },
          ],
        },
        {
          id: "openrouter",
          name: "OpenRouter",
          configured: Boolean(Deno.env.get("OPENROUTER_API_KEY")),
          requiresKey: true,
          models: [
            { id: "openrouter/auto", name: "Auto (Best Available)" },
            { id: "openrouter/free", name: "Free Models (Auto)" },
            { id: "anthropic/claude-sonnet-5", name: "Claude Sonnet 5" },
            { id: "anthropic/claude-opus-5", name: "Claude Opus 5" },
            { id: "openai/gpt-5.6-terra", name: "GPT-5.6 Terra" },
            { id: "google/gemini-3.6-flash", name: "Gemini 3.6 Flash" },
            { id: "x-ai/grok-4.5", name: "Grok 4.5" },
          ],
        },
      ],
    });
  }

  if (
    body.action !== "chat" ||
    (body.provider !== "openai" && body.provider !== "openrouter")
  ) {
    return json({ error: "Unsupported action or provider" }, 400);
  }

  const messages = body.messages ?? [];
  if (
    messages.length === 0 ||
    messages.length > 50 ||
    messages.some((message) =>
      !["user", "assistant", "system"].includes(message.role) ||
      typeof message.content !== "string" ||
      message.content.length === 0 ||
      message.content.length > 50_000
    )
  ) {
    return json({ error: "Invalid messages" }, 400);
  }

  if (body.provider === "openrouter") {
    const apiKey = Deno.env.get("OPENROUTER_API_KEY");
    if (!apiKey) return json({ error: "OpenRouter is not configured" }, 503);

    const model = body.model ?? "openrouter/auto";
    if (!OPENROUTER_MODELS.has(model)) {
      return json({ error: "Unsupported OpenRouter model" }, 400);
    }

    const chatMessages = messages.some((message) => message.role === "system")
      ? messages
      : [{ role: "system", content: SYSTEM_INSTRUCTIONS }, ...messages];

    const openRouterResponse = await fetch(
      "https://openrouter.ai/api/v1/chat/completions",
      {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${apiKey}`,
          "Content-Type": "application/json",
          "HTTP-Referer": "https://archon.app",
          "X-Title": "Archon",
        },
        body: JSON.stringify({
          model,
          messages: chatMessages.map(({ role, content }) => ({
            role,
            content,
          })),
          max_tokens: Math.min(Math.max(body.max_tokens ?? 4096, 1), 8192),
        }),
      },
    );

    const payload = await openRouterResponse.json() as Record<string, unknown>;
    if (!openRouterResponse.ok) {
      const upstreamError =
        typeof payload.error === "object" && payload.error
          ? (payload.error as { message?: unknown }).message
          : undefined;
      console.error("OpenRouter request failed", openRouterResponse.status);
      return json({
        error: typeof upstreamError === "string"
          ? upstreamError
          : "OpenRouter request failed",
      }, openRouterResponse.status >= 500 ? 502 : 400);
    }

    const choices = Array.isArray(payload.choices) ? payload.choices : [];
    const firstMessage = choices[0] &&
        typeof choices[0] === "object"
      ? (choices[0] as { message?: { content?: unknown } }).message
      : undefined;
    const content = typeof firstMessage?.content === "string"
      ? firstMessage.content
      : "";
    if (!content) return json({ error: "OpenRouter returned no text" }, 502);

    const usage = payload.usage && typeof payload.usage === "object"
      ? payload.usage as { prompt_tokens?: number; completion_tokens?: number }
      : {};

    return json({
      content,
      // OpenRouter reports which model actually served the request (useful
      // for the auto routers); fall back to the requested model.
      model: typeof payload.model === "string" ? payload.model : model,
      provider: "openrouter",
      tokens_used: {
        input: usage.prompt_tokens ?? 0,
        output: usage.completion_tokens ?? 0,
      },
      reasoning_effort: body.reasoning_effort ?? "medium",
      credit_units: null,
    });
  }

  const apiKey = Deno.env.get("OPENAI_API_KEY");
  if (!apiKey) return json({ error: "OpenAI is not configured" }, 503);

  const model = body.model ?? "gpt-5.6-terra";
  if (!OPENAI_MODELS.has(model)) {
    return json({ error: "Unsupported OpenAI model" }, 400);
  }

  const openAIResponse = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      input: messages.map(({ role, content }) => ({ role, content })),
      instructions: SYSTEM_INSTRUCTIONS,
      max_output_tokens: Math.min(Math.max(body.max_tokens ?? 4096, 1), 8192),
      reasoning: { effort: body.reasoning_effort ?? "medium" },
    }),
  });

  const payload = await openAIResponse.json() as Record<string, unknown>;
  if (!openAIResponse.ok) {
    const upstreamError =
      typeof payload.error === "object" && payload.error
        ? (payload.error as { message?: unknown }).message
        : undefined;
    console.error("OpenAI request failed", openAIResponse.status);
    return json({
      error: typeof upstreamError === "string"
        ? upstreamError
        : "OpenAI request failed",
    }, openAIResponse.status >= 500 ? 502 : 400);
  }

  const content = extractText(payload);
  if (!content) return json({ error: "OpenAI returned no text" }, 502);

  const usage =
    payload.usage && typeof payload.usage === "object"
      ? payload.usage as { input_tokens?: number; output_tokens?: number }
      : {};

  return json({
    content,
    model,
    provider: "openai",
    tokens_used: {
      input: usage.input_tokens ?? 0,
      output: usage.output_tokens ?? 0,
    },
    reasoning_effort: body.reasoning_effort ?? "medium",
    credit_units: null,
  });
});
