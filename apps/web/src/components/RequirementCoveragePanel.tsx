"use client";

import { useState } from "react";
import type {
  ContentPlan,
  ContentPlanItem,
  RequirementDisposition,
} from "@/lib/api";

interface Props {
  plan: ContentPlan;
  busy: boolean;
  onResolve: (
    requirementId: string,
    resolution: {
      action: "assign" | "exclude" | "global_control";
      item_id?: string;
      reason?: string;
    },
  ) => Promise<void>;
}

const DISPOSITION_LABELS: Record<string, string> = {
  target: "в подточка",
  global_control: "общо правило",
  excluded: "изключено",
  unresolved: "без получател",
};

/** K-03: every confirmed requirement has a visible disposition. */
export default function RequirementCoveragePanel({ plan, busy, onResolve }: Props) {
  const coverage = plan.requirement_coverage;
  if (!coverage || coverage.total === 0) return null;
  const unresolved = (plan.requirement_dispositions ?? []).filter(
    (entry) => entry.disposition === "unresolved",
  );
  const workingItems = plan.items.filter((item) => item.generation_uid);

  return (
    <div data-testid="requirement-coverage-panel" className="space-y-2 rounded border border-slate-200 p-2 text-[11px]">
      <p className="text-slate-700">
        Изисквания към ТП: {coverage.total} ·{" "}
        {(["target", "global_control", "excluded", "unresolved"] as const)
          .filter((key) => coverage[key] > 0)
          .map((key) => `${DISPOSITION_LABELS[key]}: ${coverage[key]}`)
          .join(" · ")}
      </p>
      {unresolved.length > 0 && (
        <div data-testid="requirement-unresolved-list" className="space-y-2">
          <p className="font-medium text-red-700">
            {unresolved.length === 1
              ? "1 потвърдено изискване няма получател в плана. Одобрението е блокирано, докато не бъде разрешено."
              : `${unresolved.length} потвърдени изисквания нямат получател в плана. Одобрението е блокирано, докато не бъдат разрешени.`}
          </p>
          {unresolved.map((entry) => (
            <UnresolvedRequirement
              key={entry.requirement_id}
              entry={entry}
              items={workingItems}
              busy={busy || plan.status_locked}
              onResolve={onResolve}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function UnresolvedRequirement({
  entry,
  items,
  busy,
  onResolve,
}: {
  entry: RequirementDisposition;
  items: ContentPlanItem[];
  busy: boolean;
  onResolve: Props["onResolve"];
}) {
  const [itemId, setItemId] = useState(items[0]?.id ?? "");
  const [reason, setReason] = useState("");
  return (
    <div className="space-y-1 rounded bg-red-50 p-2" data-testid={`unresolved-${entry.requirement_id}`}>
      <p className="text-gray-800">{entry.text}</p>
      {entry.source_quote && (
        <p className="italic text-gray-500">
          „{entry.source_quote}“{entry.source_page ? ` (стр. ${entry.source_page})` : ""}
        </p>
      )}
      <div className="flex gap-1">
        <select
          value={itemId}
          onChange={(event) => setItemId(event.target.value)}
          className="min-w-0 flex-1 rounded border px-1"
          aria-label="Подточка-получател"
        >
          {items.map((item) => (
            <option key={item.id} value={item.id}>
              {item.number} {item.title}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={busy || !itemId}
          onClick={() => void onResolve(entry.requirement_id, { action: "assign", item_id: itemId })}
          className="rounded border px-2"
        >
          Към подточката
        </button>
      </div>
      <div className="flex gap-1">
        <input
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Обосновка за изключване"
          className="min-w-0 flex-1 rounded border px-1"
        />
        <button
          type="button"
          disabled={busy || reason.trim().length < 10}
          onClick={() => void onResolve(entry.requirement_id, { action: "exclude", reason })}
          className="rounded border px-2"
        >
          Изключи
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void onResolve(entry.requirement_id, { action: "global_control" })}
          className="rounded border px-2"
        >
          Общо правило
        </button>
      </div>
    </div>
  );
}
