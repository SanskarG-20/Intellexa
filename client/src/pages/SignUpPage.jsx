import { SignUp } from "@clerk/clerk-react";
import AuthLayout from "../components/AuthLayout";

function SignUpPage() {
  return (
    <AuthLayout>
      <div className="auth-page-shell">
        <p className="auth-kicker">// INTELLEXA ACCESS</p>
        <h1 className="auth-heading">Sign Up</h1>
        <p className="auth-subheading">Create your account to start reasoning.</p>
        <SignUp
          routing="path"
          path="/sign-up"
          signInUrl="/sign-in"
          forceRedirectUrl="/dashboard"
        />
      </div>
    </AuthLayout>
  );
}

export default SignUpPage;
