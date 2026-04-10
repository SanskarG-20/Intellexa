import React from "react";
import ReactDOM from "react-dom/client";
import { ClerkProvider } from "@clerk/clerk-react";
import { BrowserRouter } from "react-router-dom";
import AppRoutes from "./AppRoutes";
import "./styles.css";

const clerkPublishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

if (!clerkPublishableKey) {
  throw new Error("Missing VITE_CLERK_PUBLISHABLE_KEY in environment variables.");
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <ClerkProvider
    publishableKey={clerkPublishableKey}
    afterSignOutUrl="/"
    signInForceRedirectUrl="/dashboard"
    signUpForceRedirectUrl="/dashboard"
  >
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  </ClerkProvider>
);
