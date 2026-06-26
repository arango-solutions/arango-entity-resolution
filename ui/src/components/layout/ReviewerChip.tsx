import { User } from "lucide-react";
import { useReviewer } from "../../hooks/useReviewer";

/**
 * Header chip showing/setting the reviewer name used to attribute curation
 * actions (sent as the X-Reviewer header). Attribution only — not authentication.
 */
export function ReviewerChip() {
  const { reviewer, setReviewer } = useReviewer();

  function edit() {
    const next = window.prompt(
      "Reviewer name (attributes your review/curation actions in the audit log):",
      reviewer ?? "",
    );
    if (next !== null) setReviewer(next);
  }

  return (
    <button
      type="button"
      onClick={edit}
      title="Set the reviewer name attributed to your curation actions"
      className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-100"
    >
      <User className="h-3.5 w-3.5" />
      {reviewer ? reviewer : <span className="text-gray-400">Set reviewer</span>}
    </button>
  );
}
