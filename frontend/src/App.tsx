import { Navigate, Route, Routes } from "react-router-dom";
import { AutoPauseOverlay } from "./components/AutoPauseOverlay";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { WebSocketProvider } from "./context/WebSocketContext";
import { AlertCenterPage } from "./pages/AlertCenterPage";
import { DashboardPage } from "./pages/DashboardPage";
import { JobDetailPage } from "./pages/JobDetailPage";
import { LoginPage } from "./pages/LoginPage";

export function App() {
  return (
    <WebSocketProvider>
      <AutoPauseOverlay />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/printers/:printerId"
          element={
            <ProtectedRoute>
              <JobDetailPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/printers/:printerId/jobs/:jobId"
          element={
            <ProtectedRoute>
              <JobDetailPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/alerts"
          element={
            <ProtectedRoute>
              <AlertCenterPage />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </WebSocketProvider>
  );
}
