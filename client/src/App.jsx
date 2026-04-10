import { useEffect, useState, useRef, useCallback } from "react";
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

/* ── Metrics data ────────────────────────────────────────── */
const METRICS = [
  { target: 7, prefix: "", suffix: "×", label: "Pipeline Layers", sub: "Every query passes 7 transparent stages" },
  { target: 2, prefix: "<", suffix: "s", label: "Avg Response Time", sub: "Groq-accelerated generation" },
  { target: 3, prefix: "", suffix: " POV", label: "Ethical Viewpoints", sub: "Utilitarian · Rights · Care Ethics" },
];

/* ── Count-up hook ───────────────────────────────────────── */
function useCountUp(target, duration = 2000, start = false) {
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (!start) return;
    let startTime = null;
    let raf;

    const easeOut = (t) => 1 - Math.pow(1 - t, 3);

    const step = (timestamp) => {
      if (!startTime) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / duration, 1);
      setValue(Math.round(easeOut(progress) * target));
      if (progress < 1) {
        raf = requestAnimationFrame(step);
      }
    };

    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [start, target, duration]);

  return value;
}

/* ── Single metric cell component ────────────────────────── */
function MetricCell({ metric, delay }) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.unobserve(el);
        }
      },
      { threshold: 0.3 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const count = useCountUp(metric.target, 2000, visible);

  return (
    <div
      ref={ref}
      className={`metric-cell ${visible ? "is-visible" : ""}`}
      style={{ transitionDelay: `${delay}s` }}
    >
      <div className="metric-number">
        {metric.prefix && <span className="metric-suffix">{metric.prefix}</span>}
        <span>{count}</span>
        <span className="metric-suffix">{metric.suffix}</span>
      </div>
      <div className="metric-label">{metric.label}</div>
      <div className="metric-subdesc">{metric.sub}</div>
    </div>
  );
}

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

  /* IntersectionObserver for bento feature cards */
  useEffect(() => {
    const cards = document.querySelectorAll(".bento-card");
    if (!cards.length) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.1 }
    );

    cards.forEach((card) => observer.observe(card));
    return () => observer.disconnect();
  }, []);

  /* IntersectionObserver for generic fade-up elements */
  useEffect(() => {
    const els = document.querySelectorAll(".fade-up");
    if (!els.length) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15 }
    );

    els.forEach((el) => observer.observe(el));
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

          {/* ── FEATURES ─────────────────────────── */}
          <section className="features-section" id="features">
            <span className="features-label">// 02 — CORE FEATURES</span>
            <h2 className="features-heading">Built Different.</h2>
            <p className="features-subheading">
              Not another black-box AI.
            </p>

            <div className="bento-grid">
              {/* Card 1 — Perspective Autopsy (2 cols) */}
              <article
                className="bento-card hud-card card-autopsy card-span-2-col"
                style={{ transitionDelay: "0s" }}
              >
                <span className="card-chip">| RUNS BEFORE EVERY ANSWER |</span>
                <h3 className="card-title">Perspective Autopsy</h3>
                <p className="card-desc">
                  Before generating any answer, Gemini surgically dissects your
                  question — surfacing hidden assumptions, embedded biases, and
                  missing angles you didn't know to ask.
                </p>
                <div className="tag-row">
                  <span className="tag-pill">Bias Detection</span>
                  <span className="tag-pill">Assumption Mapping</span>
                  <span className="tag-pill">Blind Spot Analysis</span>
                </div>
              </article>

              {/* Card 2 — Trust Score (2 rows) */}
              <article
                className="bento-card hud-card card-trust card-span-2-row"
                style={{ transitionDelay: "0.07s" }}
              >
                <span className="trust-big-number">87</span>
                <span className="trust-label">TRUST SCORE</span>
                <div className="trust-divider" />
                <div className="trust-metrics">
                  <span className="trust-metric metric-green">↑ Ethical Risk: LOW</span>
                  <span className="trust-metric metric-accent">↑ Confidence: HIGH</span>
                  <span className="trust-metric metric-violet">↑ Bias Clean: TRUE</span>
                </div>
              </article>

              {/* Card 3 — Multi-Perspective (1 col) */}
              <article
                className="bento-card hud-card"
                style={{ transitionDelay: "0.14s" }}
              >
                <h3 className="card-small-title">Multi-Perspective</h3>
                <div className="perspective-row" style={{ borderColor: '#4ADE80' }}>
                  <div className="perspective-name">Utilitarian</div>
                  <div className="perspective-desc">Greatest good for the most people</div>
                </div>
                <div className="perspective-row" style={{ borderColor: 'var(--violet)' }}>
                  <div className="perspective-name">Rights-Based</div>
                  <div className="perspective-desc">What rights does this decision affect?</div>
                </div>
                <div className="perspective-row" style={{ borderColor: 'var(--accent)' }}>
                  <div className="perspective-name">Care Ethics</div>
                  <div className="perspective-desc">Who is made vulnerable here?</div>
                </div>
              </article>

              {/* Card 4 — Explainability Engine (1 col) */}
              <article
                className="bento-card hud-card"
                style={{ transitionDelay: "0.21s" }}
              >
                <h3 className="card-small-title">Explainability Engine</h3>
                <p className="card-small-desc">
                  Every response ships with its reasoning — what context was
                  used, how it was weighted, and a confidence level.
                </p>
                <div className="toggle-row">
                  <button className="toggle-switch toggle-active" type="button">
                    [ BEGINNER ]
                  </button>
                  <button className="toggle-switch toggle-inactive" type="button">
                    [ EXPERT ]
                  </button>
                </div>
              </article>

              {/* Card 5 — Ethical Gate (1 col) */}
              <article
                className="bento-card hud-card"
                style={{ transitionDelay: "0.28s" }}
              >
                <h3 className="card-small-title">Ethical Gate</h3>
                <div className="gate-status">
                  <span className="status-dot">●</span>
                  <span className="gate-status-text">GATE STATUS: ACTIVE</span>
                </div>
                <p className="card-small-desc">
                  Sensitive content, political bias, and factual overreach are
                  caught before they reach you. Fairness is enforced, not
                  optional.
                </p>
              </article>

              {/* Card 6 — Context Memory (2 cols) */}
              <article
                className="bento-card hud-card card-context card-span-2-col"
                style={{ transitionDelay: "0.35s" }}
              >
                <h3 className="card-title">Context Memory</h3>
                <p className="card-desc">
                  Intellexa builds a user-specific memory from your query
                  history. Responses become more relevant, more personalized —
                  and more accurate — over time.
                </p>
                <div className="timeline-row">
                  <span className="timeline-chip">query_001</span>
                  <span className="timeline-chip">query_002</span>
                  <span className="timeline-chip">query_003</span>
                  <span className="timeline-chip timeline-chip-active">→ current</span>
                </div>
              </article>
            </div>
          </section>

          {/* ── SYSTEM METRICS ───────────────────── */}
          <section className="metrics-section" id="trust-score">
            <span className="metrics-label">// 03 — SYSTEM METRICS</span>
            <div className="metrics-row">
              {METRICS.map((m, i) => (
                <MetricCell key={m.label} metric={m} delay={i * 0.1} />
              ))}
            </div>
          </section>

          {/* ── TERMINAL CTA ─────────────────────── */}
          <section className="cta-section fade-up" id="demo">
            <div className="terminal-frame">
              {/* 4-corner brackets */}
              <div className="terminal-bracket bracket-tl" />
              <div className="terminal-bracket bracket-tr" />
              <div className="terminal-bracket bracket-bl" />
              <div className="terminal-bracket bracket-br" />

              {/* Titlebar */}
              <div className="terminal-titlebar">
                <span className="terminal-dot dot-red" />
                <span className="terminal-dot dot-yellow" />
                <span className="terminal-dot dot-green" />
                <span className="terminal-title-text">
                  intellexa — terminal v1.0
                </span>
              </div>

              {/* Prompt */}
              <div className="cta-prompt">
                {"> system.initialize(user)"}
              </div>

              {/* Headline */}
              <h2 className="cta-headline">
                Ready to Think
                <br />
                <span className="cta-accent-line">Without Limits?</span>
              </h2>

              {/* Subtext */}
              <p className="cta-subtext">
                Intellexa doesn't just answer — it reasons, reflects, and earns
                trust. One query at a time.
              </p>

              {/* Button */}
              <button className="cta-button" type="button">
                ▸ Initialize Session
              </button>

              {/* Note */}
              <p className="cta-note">
                // No account required · Built for Hackathon PS-202 · Team Nexus
              </p>
            </div>
          </section>
        </main>

        {/* ── FOOTER ───────────────────────────── */}
        <footer className="page-footer">
          <span className="footer-logo">[ INTELLEXA ]</span>
          <span className="footer-tech">
            Groq · Gemini · Clerk · Supabase · React
          </span>
          <span className="footer-copy">© 2025 Team Nexus</span>
        </footer>
      </div>
    </div>
  );
}

export default App;
