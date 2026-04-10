import { lazy, Suspense, useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import App from "./App";

const ProtectedRoute = lazy(() => import("./components/ProtectedRoute"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const SignInPage = lazy(() => import("./pages/SignInPage"));
const SignUpPage = lazy(() => import("./pages/SignUpPage"));

function RouteFallback() {
  return <div className="auth-loading">Loading...</div>;
}

function AppRoutes() {
  const location = useLocation();

  useEffect(() => {
    // Safety guard: prevent stale GSAP inline styles from leaving the app fully transparent.
    document.body.style.opacity = "1";
  }, [location.pathname]);

  return (
    <Routes>
      <Route path="/" element={<App />} />
      <Route
        path="/sign-in/*"
        element={
          <Suspense fallback={<RouteFallback />}>
            <SignInPage />
          </Suspense>
        }
      />
      <Route
        path="/sign-up/*"
        element={
          <Suspense fallback={<RouteFallback />}>
            <SignUpPage />
          </Suspense>
        }
      />
      <Route
        path="/dashboard"
        element={
          <Suspense fallback={<RouteFallback />}>
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          </Suspense>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default AppRoutes;
