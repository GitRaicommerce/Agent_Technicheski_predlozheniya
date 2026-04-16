/**
 * Next.js Route Handler that proxies file uploads to the FastAPI backend.
 * This bypasses the Next.js rewrite proxy which has a ~4 MB body size limit.
 * Route Handlers in the App Router do not impose a body size limit.
 */
import { NextRequest, NextResponse } from "next/server";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ project_id: string }> },
) {
  const { project_id } = await params;
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const upstream = `${apiUrl}/api/v1/files/${project_id}/upload`;

  const response = await fetch(upstream, {
    method: "POST",
    // Stream the body directly without buffering
    body: request.body,
    headers: {
      // Forward content-type (includes multipart boundary)
      "content-type": request.headers.get("content-type") ?? "",
    },
    // Required for streaming request body in Node.js fetch
    // @ts-expect-error Node.js fetch requires duplex for streamed request bodies.
    duplex: "half",
  });

  const data = await response.json().catch(() => null);
  return NextResponse.json(data ?? {}, { status: response.status });
}
