import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

export default function ProtectedRoute({ children }) {
  const { loading, token } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen grid place-items-center" data-testid="auth-loading-state">
        <p className="font-mono">Checking access...</p>
      </div>
    );
  }
  if (!token) return <Navigate to="/login" replace />;
  return children;
}
