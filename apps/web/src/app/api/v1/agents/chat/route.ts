import { proxyLongApiRequest } from "@/lib/serverApiProxy";

export const maxDuration = 300;

export async function POST(request: Request) {
  return proxyLongApiRequest(request, "/api/v1/agents/chat");
}
