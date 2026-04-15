import { X } from "lucide-react";
import { cn } from "../../lib/cn";

interface WeightSliderProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  onRemove?: () => void;
  min?: number;
  max?: number;
  step?: number;
  className?: string;
}

export function WeightSlider({
  label,
  value,
  onChange,
  onRemove,
  min = 0,
  max = 1,
  step = 0.05,
  className,
}: WeightSliderProps) {
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <span className="w-28 shrink-0 truncate text-sm font-medium text-gray-700">
        {label}
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="h-2 flex-1 cursor-pointer appearance-none rounded-lg bg-gray-200 accent-indigo-600"
      />
      <span className="w-12 shrink-0 text-right font-mono text-sm tabular-nums text-gray-600">
        {value.toFixed(2)}
      </span>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          className="rounded p-0.5 text-gray-400 hover:bg-red-50 hover:text-red-500"
          title="Remove"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
