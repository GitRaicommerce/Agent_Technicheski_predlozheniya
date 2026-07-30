import { afterEach, describe, expect, it, vi } from "vitest";

import { proxyLongApiRequest } from "./serverApiProxy";

describe("proxyLongApiRequest", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("forwards the body and query without attaching the client abort signal", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api:8000");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await proxyLongApiRequest(
      new Request("http://localhost/api/v1/agents/chat?mode=full", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ message: "generate" }),
      }),
      "/api/v1/agents/chat",
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api:8000/api/v1/agents/chat?mode=full",
      expect.objectContaining({
        method: "POST",
        cache: "no-store",
      }),
    );
    expect(fetchMock.mock.calls[0][1]).not.toHaveProperty("signal");
  });

  it("returns a useful gateway error when the backend connection fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("socket closed")));

    const response = await proxyLongApiRequest(
      new Request("http://localhost/api/v1/agents/chat", { method: "POST" }),
      "/api/v1/agents/chat",
    );

    expect(response.status).toBe(502);
    await expect(response.json()).resolves.toEqual({
      detail: "Backend connection failed: socket closed",
    });
  });
});
