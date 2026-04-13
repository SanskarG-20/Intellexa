import React, { useState, useEffect } from "react";
import ReactDOM from "react-dom/client";
import { ClerkProvider, ClerkLoaded, ClerkLoading } from "@clerk/clerk-react";
import { BrowserRouter } from "react-router-dom";
import AppRoutes from "./AppRoutes";
import ErrorBoundary from "./components/ErrorBoundary";
import "./styles.css";

// Get Clerk key from environment
const clerkPublishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

// Debug: Log key status (remove in production if desired)
if (typeof window !== 'undefined') {
  console.log('[Intellexa] Clerk key status:', {
    exists: !!clerkPublishableKey,
    startsCorrectly: clerkPublishableKey?.startsWith('pk_test_') || clerkPublishableKey?.startsWith('pk_live_'),
    length: clerkPublishableKey?.length || 0
  });
}

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

function ClerkErrorScreen({ message, showKeyHelp }) {
  return (
    <div className="clerk-loading-screen">
      <div className="clerk-loading-content">
        <p className="clerk-error-text">{message}</p>
        {showKeyHelp && (
          <div style={{ marginTop: "16px", textAlign: "left" }}>
            <p style={{ fontSize: "12px", color: "#5A5A7A", marginBottom: "8px" }}>
              To fix this on Vercel:
            </p>
            <ol style={{ fontSize: "11px", color: "#5A5A7A", paddingLeft: "16px", lineHeight: "1.6" }}>
              <li>Go to Vercel Dashboard → Project Settings → Environment Variables</li>
              <li>Add <code style={{ color: "#4DFFD2" }}>VITE_CLERK_PUBLISHABLE_KEY</code></li>
              <li>Copy the FULL key from your Clerk Dashboard</li>
              <li>Redeploy the project</li>
            </ol>
          </div>
        )}
        <button
          className="clerk-retry-button"
          onClick={() => window.location.reload()}
          style={{ marginTop: "20px" }}
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
      console.error('[Intellexa] Missing Clerk publishable key');
      setClerkError("Missing Clerk publishable key.");
    } else if (!clerkPublishableKey.startsWith("pk_test_") && !clerkPublishableKey.startsWith("pk_live_")) {
      console.error('[Intellexa] Invalid Clerk key format:', clerkPublishableKey.substring(0, 10) + '...');
      setClerkError("Invalid Clerk publishable key format. Key must start with pk_test_ or pk_live_");
    } else {
      console.log('[Intellexa] Clerk key validated successfully');
    }
  }, []);

  if (clerkError) {
    return <ClerkErrorScreen message={clerkError} showKeyHelp={true} />;
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
