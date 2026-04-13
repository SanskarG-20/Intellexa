import { Component } from "react";

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught an error:", error);
    console.error("Error info:", errorInfo);
    this.setState({ errorInfo });
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    window.location.href = "/";
  };

  render() {
    if (this.state.hasError) {
      const errorMessage = this.state.error?.message || "Unknown error";
      const isClerkError = errorMessage.toLowerCase().includes("clerk") || 
                          errorMessage.toLowerCase().includes("publishable key") ||
                          errorMessage.toLowerCase().includes("authentication");
      
      return (
        <div style={styles.container}>
          <div style={styles.card}>
            <h1 style={styles.title}>Something went wrong</h1>
            <p style={styles.message}>
              {isClerkError 
                ? "There was an issue initializing authentication. Please check your environment configuration."
                : "We encountered an unexpected error. Please try refreshing the page."
              }
            </p>
            <details style={styles.details}>
              <summary style={styles.summary}>Error Details</summary>
              <p style={styles.errorText}>{errorMessage}</p>
            </details>
            <button onClick={this.handleRetry} style={styles.button}>
              Return Home
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

const styles = {
  container: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#0C0C15",
    padding: "20px",
  },
  card: {
    backgroundColor: "#111120",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: "12px",
    padding: "40px",
    maxWidth: "500px",
    textAlign: "center",
  },
  title: {
    fontFamily: "'Space Mono', monospace",
    fontSize: "24px",
    color: "#E8E8F0",
    marginBottom: "16px",
  },
  message: {
    fontFamily: "'Outfit', sans-serif",
    fontSize: "14px",
    color: "#5A5A7A",
    marginBottom: "16px",
    lineHeight: "1.6",
  },
  details: {
    marginBottom: "24px",
    textAlign: "left",
  },
  summary: {
    fontFamily: "'Space Mono', monospace",
    fontSize: "12px",
    color: "#4DFFD2",
    cursor: "pointer",
    marginBottom: "8px",
  },
  errorText: {
    fontFamily: "'Space Mono', monospace",
    fontSize: "11px",
    color: "#ffb1aa",
    backgroundColor: "rgba(255,177,170,0.1)",
    padding: "12px",
    borderRadius: "6px",
    wordBreak: "break-word",
    lineHeight: "1.5",
  },
  button: {
    fontFamily: "'Space Mono', monospace",
    fontSize: "12px",
    letterSpacing: "0.1em",
    textTransform: "uppercase",
    color: "#0C0C15",
    backgroundColor: "#4DFFD2",
    padding: "12px 24px",
    border: "none",
    borderRadius: "6px",
    cursor: "pointer",
  },
};

export default ErrorBoundary;
