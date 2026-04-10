import { SignIn } from "@clerk/clerk-react";
import AuthLayout from "../components/AuthLayout";

function SignInPage() {
  return (
    <AuthLayout>
      <div className="auth-page-shell">
        <p className="auth-kicker">// INTELLEXA ACCESS</p>
        <h1 className="auth-heading">Sign In</h1>
        <p className="auth-subheading">Continue to your secure dashboard.</p>
        <SignIn
          routing="path"
          path="/sign-in"
          signUpUrl="/sign-up"
          forceRedirectUrl="/dashboard"
        />
      </div>
    </AuthLayout>
  );
}

export default SignInPage;
