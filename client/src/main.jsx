import React, { useState, useEffect } from "react";
import ReactDOM from "react-dom/client";
import { ClerkProvider, ClerkLoaded, ClerkLoading } from "@clerk/clerk-react";
import { BrowserRouter } from "react-router-dom";
import AppRoutes from "./AppRoutes";
import ErrorBoundary from "./components/ErrorBoundary";
import "./styles.css";

const clerkPublishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

function ClerkLoadingScreen() {
  return (
    <div className="clerk-loading-screen">
      <div className="clerk-loading-content">
        <div className="clerk-loading-spinner" />
        <p className="clerk-loading-text">Initializing Intellexa...</p>
      </div>
    </div>
  );
}

function ClerkErrorScreen({ message }) {
  return (
    <div className="clerk-loading-screen">
      <div className="clerk-loading-content">
        <p className="clerk-error-text">{message}</p>
        <button
          className="clerk-retry-button"
          onClick={() => window.location.reload()}
        >
          Retry
        </button>
      </div>
    </div>
  );
}

function App() {
  const [clerkError, setClerkError] = useState(null);

  // Validate Clerk key on mount
  useEffect(() => {
    if (!clerkPublishableKey) {
      setClerkError("Missing Clerk publishable key. Please check your environment configuration.");
    } else if (!clerkPublishableKey.startsWith("pk_test_") && !clerkPublishableKey.startsWith("pk_live_")) {
      setClerkError("Invalid Clerk publishable key format. Key must start with pk_test_ or pk_live_");
    }
  }, []);

  if (clerkError) {
    return <ClerkErrorScreen message={clerkError} />;
  }

  if (!clerkPublishableKey) {
    return <ClerkLoadingScreen />;
  }

  return (
    <ClerkProvider
      publishableKey={clerkPublishableKey}
      afterSignOutUrl="/"
      signInForceRedirectUrl="/dashboard"
      signUpForceRedirectUrl="/dashboard"
    >
      <ClerkLoading>
        <ClerkLoadingScreen />
      </ClerkLoading>
      <ClerkLoaded>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </ClerkLoaded>
    </ClerkProvider>
  );
}

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element not found. Make sure there is a <div id=\"root\"></div> in your HTML.");
}

ReactDOM.createRoot(rootElement).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>
);
