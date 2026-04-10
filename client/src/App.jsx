import { useEffect, useState, useRef } from "react";
import "./styles.css";

/* ── Headline structure: lines of words, with accent flags ── */
const HEADLINE_LINES = [
  [
    { text: "AI", accent: false },
    { text: "That", accent: false },
    { text: "Explains", accent: false },
  ],
  [
    { text: "Every", accent: true },
    { text: "Decision", accent: true },
  ],
  [
    { text: "It", accent: false },
    { text: "Makes.", accent: false },
  ],
];

/* ── Pipeline steps data ─────────────────────────────────── */
const PIPELINE_STEPS = [
  { num: "01", title: "Auth Layer", desc: "Clerk session. User context secured." },
  { num: "02", title: "Autopsy", desc: "Gemini dissects your question for bias and assumptions." },
  { num: "03", title: "Context", desc: "Past queries retrieved and weighted." },
  { num: "04", title: "Generation", desc: "Groq LLaMA produces the primary answer." },
  { num: "05", title: "Expansion", desc: "3 ethical perspectives applied." },
  { num: "06", title: "Ethics Gate", desc: "Bias detected, flagged, corrected." },
  { num: "07", title: "Explain", desc: "Why, how, and how confident." },
];

function App() {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isHeroVisible, setIsHeroVisible] = useState(false);
  const pipelineRef = useRef(null);

  /* Scroll listener for navbar */
  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > 50);
    handleScroll();
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  /* Trigger hero animations on mount */
  useEffect(() => {
    const timer = setTimeout(() => setIsHeroVisible(true), 80);
    return () => clearTimeout(timer);
  }, []);

  /* IntersectionObserver for pipeline steps */
  useEffect(() => {
    const steps = document.querySelectorAll(".pipeline-step");
    if (!steps.length) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.2 }
    );

    steps.forEach((step) => observer.observe(step));
    return () => observer.disconnect();
  }, []);

  const handleNavClick = () => setIsMobileMenuOpen(false);

  /* Running word index for stagger delay */
  let wordIndex = 0;

  return (
    <div className="landing-page">
      {/* Fixed glow blobs */}
      <div className="glow-blob glow-blob-1" />
      <div className="glow-blob glow-blob-2" />

      <div className="page-content">
        {/* ── NAVBAR ──────────────────────────────── */}
        <header className={`navbar ${isScrolled ? "navbar-scrolled" : ""}`}>
          <div className="navbar-inner">
            <a className="logo" href="#home">
              [ INTELLEXA ]
            </a>

            <nav className="nav-center" aria-label="Primary">
              <a href="#how-it-works">System</a>
              <a href="#pipeline">Pipeline</a>
              <a href="#trust-score">Trust Layer</a>
              <a href="#demo">Demo</a>
            </nav>

            <div className="nav-right">
              <button className="nav-cta" type="button">
                ▸ Initialize
              </button>
              <button
                className="hamburger"
                type="button"
                aria-label="Open menu"
                onClick={() => setIsMobileMenuOpen((prev) => !prev)}
              >
                <span />
                <span />
                <span />
              </button>
            </div>
          </div>
        </header>

        {/* Mobile nav overlay */}
        <nav className={`mobile-nav ${isMobileMenuOpen ? "is-open" : ""}`}>
          <a href="#how-it-works" onClick={handleNavClick}>System</a>
          <a href="#pipeline" onClick={handleNavClick}>Pipeline</a>
          <a href="#trust-score" onClick={handleNavClick}>Trust Layer</a>
          <a href="#demo" onClick={handleNavClick}>Demo</a>
        </nav>

        <main>
          {/* ── HERO ─────────────────────────────── */}
          <section className="hero" id="home">
            <div className="hero-container">
              {/* Floating HUD chips */}
              <div className="hud-chips">
                <span className="hud-chip">| Perspective Autopsy ⟳ |</span>
                <span className="hud-chip">| Trust Score: 87 |</span>
                <span className="hud-chip">| Ethical Check ✓ |</span>
                <span className="hud-chip">| Multi-Model ◈ |</span>
              </div>

              {/* Hero content */}
              <div className="hero-content">
                {/* Badge */}
                <div
                  className={`hero-badge ${isHeroVisible ? "is-visible" : ""}`}
                  style={{ transitionDelay: "0.3s" }}
                >
                  // TRUST-AWARE AI SYSTEM
                </div>

                {/* Headline: word-by-word reveal */}
                <h1 className="hero-headline">
                  {HEADLINE_LINES.map((line, lineIdx) => {
                    const lineWords = line.map((wordObj) => {
                      const idx = wordIndex++;
                      return (
                        <span
                          key={`w-${idx}`}
                          className={`hero-word ${isHeroVisible ? "is-visible" : ""} ${
                            wordObj.accent ? "accent-word" : ""
                          }`}
                          style={{
                            transitionDelay: `${0.5 + idx * 0.06}s`,
                          }}
                        >
                          {wordObj.text}
                          {"\u00A0"}
                        </span>
                      );
                    });

                    return (
                      <span key={`line-${lineIdx}`}>
                        {lineWords}
                        {lineIdx < HEADLINE_LINES.length - 1 && (
                          <span className="hero-line-break">{"\n"}</span>
                        )}
                      </span>
                    );
                  })}
                </h1>

                {/* Subtext */}
                <p
                  className={`hero-subtext ${isHeroVisible ? "is-visible" : ""}`}
                  style={{ transitionDelay: "1.1s" }}
                >
                  Intellexa runs a 7-layer reasoning pipeline — analyzing your
                  thinking, generating multi-perspective answers, detecting bias,
                  and explaining every step. No black box.
                </p>

                {/* Buttons */}
                <div
                  className={`hero-buttons ${isHeroVisible ? "is-visible" : ""}`}
                  style={{ transitionDelay: "1.3s" }}
                >
                  <button className="hero-btn-primary" type="button">
                    ▸ Start Reasoning
                  </button>
                  <button className="hero-btn-secondary" type="button">
                    [ View Pipeline ]
                  </button>
                </div>
              </div>
            </div>

            {/* Scroll indicator */}
            <span className="scroll-indicator" aria-hidden="true">
              ↓ scroll
            </span>
          </section>

          {/* ── PIPELINE ─────────────────────────── */}
          <section className="pipeline-section" id="pipeline" ref={pipelineRef}>
            <span className="pipeline-label">// 01 — SYSTEM PIPELINE</span>
            <h2 className="pipeline-heading">The Reasoning Stack</h2>
            <hr className="pipeline-divider" />

            <div className="pipeline-grid">
              {PIPELINE_STEPS.map((step, i) => (
                <div
                  className="pipeline-step"
                  key={step.num}
                  style={{ transitionDelay: `${i * 0.06}s` }}
                >
                  <span className="step-num">{step.num}</span>
                  <div className="step-accent-line" />
                  <div className="step-title">{step.title}</div>
                  <p className="step-desc">{step.desc}</p>
                </div>
              ))}
            </div>

            {/* Status bar */}
            <div className="pipeline-status-bar">
              <span className="status-left">
                <span className="status-dot">●</span>
                PIPELINE STATUS: ACTIVE
              </span>
              <span className="status-right">
                7 layers · 3 models · &lt;2s avg response
              </span>
            </div>
          </section>

          {/* Remaining sections — future prompts */}
          <section id="how-it-works" />
          <section id="trust-score" />
          <section id="demo" />
        </main>
      </div>
    </div>
  );
}

export default App;

