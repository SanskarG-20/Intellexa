import { Component } from "react";

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
    window.location.href = "/";
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={styles.container}>
          <div style={styles.card}>
            <h1 style={styles.title}>Something went wrong</h1>
            <p style={styles.message}>
              We encountered an unexpected error. Please try refreshing the page.
            </p>
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
    maxWidth: "400px",
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
    marginBottom: "24px",
    lineHeight: "1.6",
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
