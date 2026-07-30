import { proxyLongApiRequest } from "@/lib/serverApiProxy";

export const maxDuration = 300;

export async function POST(
  request: Request,
  { params }: { params: Promise<{ project_id: string }> },
) {
  const { project_id } = await params;
  return proxyLongApiRequest(
    request,
    `/api/v1/projects/${encodeURIComponent(project_id)}/legislation/refresh`,
  );
}
