import { lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AutoPauseOverlay } from "./components/AutoPauseOverlay";
import { AppShell } from "./components/layout/AppShell";
import { PrinterLayout } from "./components/layout/PrinterLayout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { PrintersProvider } from "./context/PrintersContext";
import { WebSocketProvider } from "./context/WebSocketContext";
import { AlertCenterPage } from "./pages/AlertCenterPage";
import { JobsListPage } from "./pages/JobsListPage";
import { LoginPage } from "./pages/LoginPage";
import { LogbookPage } from "./pages/LogbookPage";
import { OverviewPage } from "./pages/OverviewPage";

// The pages with charts load on demand: the chart library is most of the bundle, and a phone on
// the lab Wi-Fi shouldn't download it just to open the overview.
const LivePrintPage = lazy(() => import("./pages/LivePrintPage").then((module) => ({ default: module.LivePrintPage })));
const JobReplayPage = lazy(() => import("./pages/JobReplayPage").then((module) => ({ default: module.JobReplayPage })));
const CalibrationPage = lazy(() => import("./pages/CalibrationPage").then((module) => ({ default: module.CalibrationPage })));
const AnalyticsPage = lazy(() => import("./pages/AnalyticsPage").then((module) => ({ default: module.AnalyticsPage })));
const HealthPage = lazy(() => import("./pages/HealthPage").then((module) => ({ default: module.HealthPage })));

export function App() {
  return (
    <WebSocketProvider>
      <PrintersProvider>
        <AutoPauseOverlay />
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            element={
              <ProtectedRoute>
                <AppShell />
              </ProtectedRoute>
            }
          >
            <Route index element={<OverviewPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="alerts" element={<AlertCenterPage />} />
            <Route path="printers/:printerId" element={<PrinterLayout />}>
              <Route index element={<Navigate to="live" replace />} />
              <Route path="live" element={<LivePrintPage />} />
              <Route path="jobs" element={<JobsListPage />} />
              <Route path="jobs/:jobId" element={<JobReplayPage />} />
              <Route path="logbook" element={<LogbookPage />} />
              <Route path="camera" element={<CalibrationPage />} />
              <Route path="health" element={<HealthPage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </PrintersProvider>
    </WebSocketProvider>
  );
}
