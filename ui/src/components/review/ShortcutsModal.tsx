import { X } from "lucide-react";

interface ShortcutsModalProps {
  open: boolean;
  onClose: () => void;
}

const SHORTCUTS: { keys: string; label: string }[] = [
  { keys: "M", label: "Mark focused pair as Match" },
  { keys: "N", label: "Mark focused pair as Not a match" },
  { keys: "S", label: "Skip focused pair" },
];

export function ShortcutsModal({ open, onClose }: ShortcutsModalProps) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-lg bg-white p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-900">Keyboard shortcuts</h3>
          <button onClick={onClose} className="rounded p-1 text-gray-400 hover:bg-gray-100">
            <X className="h-4 w-4" />
          </button>
        </div>
        <ul className="space-y-2">
          {SHORTCUTS.map((s) => (
            <li key={s.keys} className="flex items-center justify-between text-sm">
              <span className="text-gray-600">{s.label}</span>
              <kbd className="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs text-gray-700">
                {s.keys}
              </kbd>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-xs text-gray-400">
          Use the checkboxes to select multiple pairs, then apply a bulk verdict from the
          action bar. Export the current queue with the CSV button.
        </p>
      </div>
    </div>
  );
}
