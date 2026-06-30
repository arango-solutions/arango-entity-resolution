import { Outlet, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "../../api/client";
import { Sidebar } from "./Sidebar";
import { ReviewerChip } from "./ReviewerChip";

const pageTitles: Record<string, string> = {
  "/": "Dashboard",
  "/review": "Review Queue",
  "/clusters": "Clusters",
  "/pipeline": "Pipeline",
  "/golden": "Golden Records",
  "/resolve": "Resolve Entity",
  "/tuner": "Threshold Tuner",
  "/config": "Config Builder",
  "/export": "Export",
};

interface HealthResponse {
  status: string;
  version: string;
  database_connected: boolean;
}

export function AppShell() {
  const location = useLocation();

  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => fetchApi<HealthResponse>("/api/health"),
    retry: false,
    refetchInterval: 30_000,
  });

  const dbConnected = health.data?.database_connected ?? true;
  const serverDown = health.isError;

  const title =
    pageTitles[location.pathname] ??
    (location.pathname.startsWith("/clusters/")
      ? "Cluster Detail"
      : location.pathname.startsWith("/golden/")
        ? "Golden Record"
        : "Entity Resolution");

  return (
    <div className="flex h-screen bg-white">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        {serverDown && (
          <div className="bg-red-600 px-4 py-2 text-center text-sm font-medium text-white">
            Cannot reach the API server. Is it still running?
          </div>
        )}
        {!serverDown && !dbConnected && (
          <div className="bg-amber-500 px-4 py-2 text-center text-sm font-medium text-white">
            No database connection — start ArangoDB and restart with connection options.
          </div>
        )}
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-gray-200 px-6">
          <h1 className="text-lg font-semibold text-gray-900">{title}</h1>
          <ReviewerChip />
        </header>
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
