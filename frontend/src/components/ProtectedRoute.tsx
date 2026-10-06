import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { token, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center text-slate-500">
        Cargando...
      </div>
    );
  }

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
