import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  ClipboardCheck,
  Network,
  Play,
  Trophy,
  Search,
  SlidersHorizontal,
  Settings,
  Download,
} from "lucide-react";
import { cn } from "../../lib/cn";
import { useSelectedCollection } from "../../contexts/CollectionContext";
import { useCollections } from "../../hooks/useCollections";
import { useReviewStats } from "../../hooks/useReview";

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  showBadge?: boolean;
}

const navItems: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/review", label: "Review", icon: ClipboardCheck, showBadge: true },
  { to: "/clusters", label: "Clusters", icon: Network },
  { to: "/pipeline", label: "Pipeline", icon: Play },
  { to: "/golden", label: "Golden Records", icon: Trophy },
  { to: "/resolve", label: "Resolve", icon: Search },
  { to: "/tuner", label: "Threshold Tuner", icon: SlidersHorizontal },
  { to: "/config", label: "Config", icon: Settings },
  { to: "/export", label: "Export", icon: Download },
];

export function Sidebar() {
  const { selectedCollection, setSelectedCollection } =
    useSelectedCollection();
  const { data: collections } = useCollections();
  const { data: reviewStats } = useReviewStats(selectedCollection);

  // The feedback store tracks decided verdicts, not a pending queue, so the
  // badge reflects the total number of recorded verdicts for the collection.
  const pendingCount = reviewStats?.total ?? 0;

  return (
    <aside className="flex h-screen w-60 flex-col border-r border-gray-200 bg-gray-50">
      <div className="flex h-14 items-center gap-2 border-b border-gray-200 px-4">
        <Network className="h-6 w-6 text-indigo-600" />
        <span className="text-sm font-semibold text-gray-900">
          Entity Resolution
        </span>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-3">
        {navItems.map(({ to, label, icon: Icon, showBadge }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-indigo-50 text-indigo-700"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900",
              )
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            <span className="flex-1">{label}</span>
            {showBadge && pendingCount > 0 && (
              <span className="inline-flex items-center rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700">
                {pendingCount}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-gray-200 p-4">
        <label className="mb-1 block text-xs font-medium text-gray-500">
          Collection
        </label>
        <select
          value={selectedCollection ?? ""}
          onChange={(e) =>
            setSelectedCollection(e.target.value || null)
          }
          className="w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-700 shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
        >
          <option value="">Select collection...</option>
          {collections?.map((c: { name: string }) => (
            <option key={c.name} value={c.name}>
              {c.name}
            </option>
          ))}
        </select>
      </div>
    </aside>
  );
}
