import { useCallback, useEffect, useState } from "react";
import { Check, X, SkipForward } from "lucide-react";
import { useSubmitVerdict } from "../../hooks/useReview";
import { cn } from "../../lib/cn";

interface VerdictPanelProps {
  collection: string;
  keyA: string;
  keyB: string;
  onVerdictSubmitted?: () => void;
}

type VerdictType = "match" | "no_match" | "skip";

export function VerdictPanel({
  collection,
  keyA,
  keyB,
  onVerdictSubmitted,
}: VerdictPanelProps) {
  const mutation = useSubmitVerdict();
  const [submitted, setSubmitted] = useState<VerdictType | null>(null);

  const submit = useCallback(
    (verdict: VerdictType) => {
      if (mutation.isPending || submitted) return;

      if (verdict === "skip") {
        setSubmitted("skip");
        setTimeout(() => {
          setSubmitted(null);
          onVerdictSubmitted?.();
        }, 600);
        return;
      }

      mutation.mutate(
        { collection, keyA, keyB, verdict: { decision: verdict } },
        {
          onSuccess: () => {
            setSubmitted(verdict);
            setTimeout(() => {
              setSubmitted(null);
              onVerdictSubmitted?.();
            }, 1000);
          },
        },
      );
    },
    [collection, keyA, keyB, mutation, onVerdictSubmitted, submitted],
  );

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLSelectElement
      ) {
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      switch (e.key.toLowerCase()) {
        case "m":
          e.preventDefault();
          submit("match");
          break;
        case "n":
          e.preventDefault();
          submit("no_match");
          break;
        case "s":
          e.preventDefault();
          submit("skip");
          break;
      }
    }

    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [submit]);

  const busy = mutation.isPending;

  return (
    <div className="flex items-center justify-center gap-3 pt-3">
      <button
        disabled={busy || submitted !== null}
        onClick={() => submit("match")}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md px-4 py-2 text-sm font-medium shadow-sm transition-colors",
          submitted === "match"
            ? "bg-green-600 text-white"
            : "bg-green-500 text-white hover:bg-green-600 disabled:opacity-50",
        )}
      >
        {submitted === "match" ? (
          <Check className="h-4 w-4" />
        ) : (
          <>
            <Check className="h-4 w-4" />
            Match
          </>
        )}
        <kbd className="ml-1 rounded bg-green-600/40 px-1 py-0.5 text-[10px] font-mono">
          M
        </kbd>
      </button>

      <button
        disabled={busy || submitted !== null}
        onClick={() => submit("no_match")}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md px-4 py-2 text-sm font-medium shadow-sm transition-colors",
          submitted === "no_match"
            ? "bg-red-600 text-white"
            : "bg-red-500 text-white hover:bg-red-600 disabled:opacity-50",
        )}
      >
        {submitted === "no_match" ? (
          <Check className="h-4 w-4" />
        ) : (
          <>
            <X className="h-4 w-4" />
            Not Match
          </>
        )}
        <kbd className="ml-1 rounded bg-red-600/40 px-1 py-0.5 text-[10px] font-mono">
          N
        </kbd>
      </button>

      <button
        disabled={busy || submitted !== null}
        onClick={() => submit("skip")}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50 disabled:opacity-50",
          submitted === "skip" && "bg-gray-200",
        )}
      >
        {submitted === "skip" ? (
          <Check className="h-4 w-4" />
        ) : (
          <>
            <SkipForward className="h-4 w-4" />
            Skip
          </>
        )}
        <kbd className="ml-1 rounded bg-gray-200 px-1 py-0.5 text-[10px] font-mono text-gray-500">
          S
        </kbd>
      </button>
    </div>
  );
}
