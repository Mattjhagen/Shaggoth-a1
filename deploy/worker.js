// Shaggoth AI — Cloudflare Worker
// Serves the dashboard static assets and proxies /api/* to the Python backend.

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Proxy API requests to the Python backend
    if (url.pathname.startsWith("/api/")) {
      const origin = env.API_ORIGIN || "http://127.0.0.1:8420";
      const backendUrl = new URL(url.pathname.replace("/api/", "/"), origin);
      backendUrl.search = url.search;

      const proxyReq = new Request(backendUrl.toString(), {
        method: request.method,
        headers: request.headers,
        body: request.method !== "GET" && request.method !== "HEAD" ? request.body : undefined,
      });

      try {
        const resp = await fetch(proxyReq);
        const newHeaders = new Headers(resp.headers);
        newHeaders.set("Access-Control-Allow-Origin", "*");
        newHeaders.set("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS");
        newHeaders.set("Access-Control-Allow-Headers", "Content-Type");
        return new Response(resp.body, {
          status: resp.status,
          headers: newHeaders,
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: "Backend unreachable", detail: err.message }), {
          status: 502,
          headers: { "Content-Type": "application/json" },
        });
      }
    }

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type",
        },
      });
    }

    // Serve static assets (dashboard)
    if (env.ASSETS) {
      return env.ASSETS.fetch(request);
    }

    return new Response("Shaggoth AI", { status: 200 });
  },
};
