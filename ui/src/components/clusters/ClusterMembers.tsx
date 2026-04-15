import { Badge } from "../shared/Badge";
import { cn } from "../../lib/cn";

interface MemberRecord {
  _key?: string;
  _id?: string;
  [key: string]: unknown;
}

interface ClusterMembersProps {
  members: MemberRecord[];
  highlightedKey?: string | null;
  onMemberClick?: (key: string) => void;
}

function getSource(member: MemberRecord): string | null {
  for (const field of ["source", "source_system", "_source"]) {
    const val = member[field];
    if (typeof val === "string" && val) return val;
  }
  return null;
}

function getMemberKey(member: MemberRecord): string {
  if (member._key) return String(member._key);
  if (member._id) return String(member._id).split("/").pop() ?? String(member._id);
  return "unknown";
}

function getDisplayFields(member: MemberRecord): [string, string][] {
  return Object.entries(member)
    .filter(
      ([k]) =>
        !k.startsWith("_") &&
        k !== "source" &&
        k !== "source_system",
    )
    .slice(0, 5)
    .map(([k, v]) => [k, v == null ? "—" : String(v)]);
}

export function ClusterMembers({
  members,
  highlightedKey,
  onMemberClick,
}: ClusterMembersProps) {
  if (members.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-gray-400">
        No member records found
      </p>
    );
  }

  return (
    <div className="space-y-3 overflow-y-auto pr-1">
      {members.map((member) => {
        const key = getMemberKey(member);
        const source = getSource(member);
        const fields = getDisplayFields(member);
        const isHighlighted = highlightedKey === key;

        return (
          <div
            key={key}
            className={cn(
              "rounded-lg border bg-white p-3 transition-all",
              isHighlighted
                ? "border-indigo-400 ring-2 ring-indigo-200"
                : "border-gray-200",
              onMemberClick && "cursor-pointer hover:border-gray-300 hover:shadow-sm",
            )}
            onClick={onMemberClick ? () => onMemberClick(key) : undefined}
          >
            <div className="mb-2 flex items-center justify-between">
              <span className="font-mono text-xs font-semibold text-gray-800">
                {key}
              </span>
              {source && (
                <Badge variant="info">{source}</Badge>
              )}
            </div>
            <dl className="space-y-0.5 text-xs">
              {fields.map(([label, value]) => (
                <div key={label} className="flex gap-2">
                  <dt className="w-24 shrink-0 truncate font-medium text-gray-500">
                    {label}:
                  </dt>
                  <dd className="truncate text-gray-700">{value}</dd>
                </div>
              ))}
            </dl>
          </div>
        );
      })}
    </div>
  );
}
