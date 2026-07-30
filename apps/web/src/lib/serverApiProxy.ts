const FORWARDED_REQUEST_HEADERS = ["accept", "content-type"] as const;
const FORWARDED_RESPONSE_HEADERS = [
  "content-disposition",
  "content-type",
  "retry-after",
] as const;

function apiBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(
    /\/+$/,
    "",
  );
}

export async function proxyLongApiRequest(
  request: Request,
  upstreamPath: string,
): Promise<Response> {
  const requestUrl = new URL(request.url);
  const headers = new Headers();

  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) {
      headers.set(name, value);
    }
  }

  try {
    const response = await fetch(
      `${apiBaseUrl()}${upstreamPath}${requestUrl.search}`,
      {
        method: request.method,
        headers,
        body:
          request.method === "GET" || request.method === "HEAD"
            ? undefined
            : await request.arrayBuffer(),
        cache: "no-store",
      },
    );
    const responseHeaders = new Headers();

    for (const name of FORWARDED_RESPONSE_HEADERS) {
      const value = response.headers.get(name);
      if (value) {
        responseHeaders.set(name, value);
      }
    }

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return Response.json(
      {
        detail: `Backend connection failed: ${message}`,
      },
      { status: 502 },
    );
  }
}
