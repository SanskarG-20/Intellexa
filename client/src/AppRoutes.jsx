import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

const App = lazy(() => import("./App"));
const ProtectedRoute = lazy(() => import("./components/ProtectedRoute"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const SignInPage = lazy(() => import("./pages/SignInPage"));
const SignUpPage = lazy(() => import("./pages/SignUpPage"));

function RouteFallback() {
  return <div className="auth-loading">Loading...</div>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <Suspense fallback={<RouteFallback />}>
            <App />
          </Suspense>
        }
      />
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
