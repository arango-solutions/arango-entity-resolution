import { Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { DashboardPage } from "./pages/DashboardPage";
import { ReviewPage } from "./pages/ReviewPage";
import { ClustersPage } from "./pages/ClustersPage";
import { ClusterDetailPage } from "./pages/ClusterDetailPage";
import { PipelinePage } from "./pages/PipelinePage";
import { GoldenRecordsPage } from "./pages/GoldenRecordsPage";
import { GoldenRecordDetailPage } from "./pages/GoldenRecordDetailPage";
import { ResolvePage } from "./pages/ResolvePage";
import { ConfigPage } from "./pages/ConfigPage";
import { ExportPage } from "./pages/ExportPage";

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/review" element={<ReviewPage />} />
        <Route path="/clusters" element={<ClustersPage />} />
        <Route
          path="/clusters/:collection/:key"
          element={<ClusterDetailPage />}
        />
        <Route path="/pipeline" element={<PipelinePage />} />
        <Route path="/golden" element={<GoldenRecordsPage />} />
        <Route
          path="/golden/:collection/:key"
          element={<GoldenRecordDetailPage />}
        />
        <Route path="/resolve" element={<ResolvePage />} />
        <Route path="/config" element={<ConfigPage />} />
        <Route path="/export" element={<ExportPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
