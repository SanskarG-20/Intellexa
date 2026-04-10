import AuthParticles from "./AuthParticles";

function AuthLayout({ children }) {
  return (
    <div className="landing-page auth-shell">
      <div className="auth-grid-overlay" />
      <AuthParticles />
      <div className="auth-text-fx" aria-hidden="true">
        <p className="auth-text-line auth-text-line-1">
          INTELLEXA · EXPLAINABILITY · TRUST · ETHICAL AI · CONTEXT AWARENESS
        </p>
        <p className="auth-text-line auth-text-line-2">
          REASONING ENGINE · BIAS CHECK · MULTI MODEL · TRANSPARENCY
        </p>
        <p className="auth-text-word">INTELLEXA</p>
      </div>
      <div className="glow-blob glow-blob-1 auth-glow-blob-1" />
      <div className="glow-blob glow-blob-2 auth-glow-blob-2" />

      <div className="page-content">
        <div className="auth-page">{children}</div>
      </div>
    </div>
  );
}

export default AuthLayout;