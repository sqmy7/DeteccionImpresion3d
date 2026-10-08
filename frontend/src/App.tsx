import { Navigate, Route, Routes } from "react-router-dom";
import { AutoPauseOverlay } from "./components/AutoPauseOverlay";
import { AppShell } from "./components/layout/AppShell";
import { PrinterLayout } from "./components/layout/PrinterLayout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { PrintersProvider } from "./context/PrintersContext";
import { WebSocketProvider } from "./context/WebSocketContext";
import { AlertCenterPage } from "./pages/AlertCenterPage";
import { CalibrationPage } from "./pages/CalibrationPage";
import { JobReplayPage } from "./pages/JobReplayPage";
import { JobsListPage } from "./pages/JobsListPage";
import { LivePrintPage } from "./pages/LivePrintPage";
import { LoginPage } from "./pages/LoginPage";
import { LogbookPage } from "./pages/LogbookPage";
import { OverviewPage } from "./pages/OverviewPage";

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
            <Route path="alerts" element={<AlertCenterPage />} />
            <Route path="printers/:printerId" element={<PrinterLayout />}>
              <Route index element={<Navigate to="live" replace />} />
              <Route path="live" element={<LivePrintPage />} />
              <Route path="jobs" element={<JobsListPage />} />
              <Route path="jobs/:jobId" element={<JobReplayPage />} />
              <Route path="logbook" element={<LogbookPage />} />
              <Route path="camera" element={<CalibrationPage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </PrintersProvider>
    </WebSocketProvider>
  );
}
