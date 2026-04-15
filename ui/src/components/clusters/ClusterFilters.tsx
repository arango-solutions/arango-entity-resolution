import { SearchBar } from "../shared/SearchBar";

interface ClusterFiltersProps {
  minSize: number;
  onMinSizeChange: (size: number) => void;
  search: string;
  onSearchChange: (search: string) => void;
}

export function ClusterFilters({
  minSize,
  onMinSizeChange,
  search,
  onSearchChange,
}: ClusterFiltersProps) {
  return (
    <div className="flex flex-wrap items-center gap-4">
      <label className="flex items-center gap-2 text-sm text-gray-700">
        <span className="whitespace-nowrap font-medium">Min size:</span>
        <input
          type="number"
          min={1}
          value={minSize}
          onChange={(e) => {
            const v = parseInt(e.target.value, 10);
            if (!isNaN(v) && v >= 1) onMinSizeChange(v);
          }}
          className="w-20 rounded-md border border-gray-300 px-2 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
        />
      </label>
      <SearchBar
        value={search}
        onChange={onSearchChange}
        placeholder="Search clusters…"
        className="w-64"
      />
    </div>
  );
}
