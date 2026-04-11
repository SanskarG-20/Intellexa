import { lazy, Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/clerk-react";
import { useNavigate } from "react-router-dom";
import Lenis from "@studio-freight/lenis";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import "./styles.css";

const Spline = lazy(() => import("@splinetool/react-spline"));
const SPLINE_SCENE_URL = "https://prod.spline.design/EciRVKyhBcQYj-h8/scene.splinecode";

gsap.registerPlugin(ScrollTrigger);
gsap.config({ autoSleep: 60, nullTargetWarn: false });

function getRuntimeMode() {
  if (typeof window === "undefined") {
    return { reducedMotion: false, isLiteMode: false };
  }

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const isMobileViewport = window.matchMedia("(max-width: 900px)").matches;
  const hardwareConcurrency = navigator.hardwareConcurrency ?? 4;
  const deviceMemory = navigator.deviceMemory ?? 4;
  const saveData = navigator.connection?.saveData === true;
  const networkType = navigator.connection?.effectiveType;
  const constrainedNetwork = networkType === "2g" || networkType === "3g" || networkType === "slow-2g";

  const isLiteMode =
    reducedMotion ||
    isMobileViewport ||
    saveData ||
    constrainedNetwork ||
    hardwareConcurrency <= 4 ||
    deviceMemory <= 4;

  return { reducedMotion, isLiteMode };
}

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
  {
    target: 7,
    decimal: false,
    prefix: "",
    suffix: "×",
    label: "Pipeline Layers",
    sub: "Every query passes 7 transparent stages",
  },
  {
    target: 10,
    decimal: true,
    prefix: "<",
    suffix: "s",
    label: "Avg Response Time",
    sub: "Groq-accelerated generation",
  },
  {
    target: 3,
    decimal: false,
    prefix: "",
    suffix: " POV",
    label: "Ethical Viewpoints",
    sub: "Utilitarian · Rights · Care Ethics",
  },
];

/* ── Single metric cell component ────────────────────────── */
function MetricCell({ metric, delay }) {
  return (
    <div className="metric-cell reveal-up" style={{ transitionDelay: `${delay}s` }}>
      <div
        className="metric-number reveal-up"
        data-target={metric.target}
        data-decimal={metric.decimal ? "true" : "false"}
      >
        {metric.prefix && <span className="metric-suffix">{metric.prefix}</span>}
        <span className="metric-value">0</span>
        <span className="metric-suffix">{metric.suffix}</span>
      </div>
      <div className="metric-label">{metric.label}</div>
      <div className="metric-subdesc">{metric.sub}</div>
    </div>
  );
}

function App() {
  const { isSignedIn } = useAuth();
  const navigate = useNavigate();
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [runtimeMode, setRuntimeMode] = useState(() => getRuntimeMode());
  const [isHeroSplineLoaded, setIsHeroSplineLoaded] = useState(false);
  const [shouldRenderHeroSpline, setShouldRenderHeroSpline] = useState(false);
  const [canLoadHeroSpline, setCanLoadHeroSpline] = useState(false);
  const pipelineRef = useRef(null);
  const heroSplineRef = useRef(null);
  const lenisRef = useRef(null);
  const isLiteMode = runtimeMode.isLiteMode;
  const reducedMotion = runtimeMode.reducedMotion;

  useEffect(() => {
    // Guard against stale inline styles from interrupted route transitions.
    document.body.style.opacity = "1";

    return () => {
      document.body.style.opacity = "1";
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;

    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updateMode = () => setRuntimeMode(getRuntimeMode());

    updateMode();

    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", updateMode);
    } else if (typeof mediaQuery.addListener === "function") {
      mediaQuery.addListener(updateMode);
    }

    window.addEventListener("resize", updateMode);

    return () => {
      if (typeof mediaQuery.removeEventListener === "function") {
        mediaQuery.removeEventListener("change", updateMode);
      } else if (typeof mediaQuery.removeListener === "function") {
        mediaQuery.removeListener(updateMode);
      }

      window.removeEventListener("resize", updateMode);
    };
  }, []);

  /* Scroll listener for navbar */
  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > 50);
    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  /* Lenis smooth scroll */
  useEffect(() => {
    if (isLiteMode || reducedMotion) {
      document.documentElement.style.scrollBehavior = "auto";
      return undefined;
    }

    document.documentElement.style.scrollBehavior = "auto";

    const lenis = new Lenis({
      duration: 1.05,
      easing: (t) => 1 - Math.pow(1 - t, 3),
      smooth: true,
      wheelMultiplier: 1,
      touchMultiplier: 1.0,
    });

    lenisRef.current = lenis;
    lenis.on("scroll", ScrollTrigger.update);

    let rafId;
    const raf = (time) => {
      lenis.raf(time);
      rafId = requestAnimationFrame(raf);
    };

    rafId = requestAnimationFrame(raf);

    return () => {
      cancelAnimationFrame(rafId);
      lenisRef.current = null;
      lenis.destroy();
    };
  }, [isLiteMode, reducedMotion]);

  useEffect(() => {
    if (isLiteMode) {
      setCanLoadHeroSpline(false);
      return undefined;
    }

    let timeoutId;
    let idleId;

    const enableSplineLoad = () => {
      timeoutId = window.setTimeout(() => {
        setCanLoadHeroSpline(true);
      }, 320);
    };

    if (typeof window.requestIdleCallback === "function") {
      idleId = window.requestIdleCallback(enableSplineLoad, { timeout: 1200 });
    } else {
      timeoutId = window.setTimeout(() => {
        setCanLoadHeroSpline(true);
      }, 900);
    }

    return () => {
      if (typeof window.cancelIdleCallback === "function" && idleId) {
        window.cancelIdleCallback(idleId);
      }

      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [isLiteMode]);

  useEffect(() => {
    if (isLiteMode) {
      setShouldRenderHeroSpline(false);
      return undefined;
    }

    const observeSpline = (element, setVisible) => {
      if (!element) return undefined;

      const observer = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting) {
            setVisible(true);
            observer.unobserve(entry.target);
          }
        },
        { rootMargin: "120px 0px", threshold: 0.1 }
      );

      observer.observe(element);
      return observer;
    };

    const heroObserver = observeSpline(heroSplineRef.current, setShouldRenderHeroSpline);

    return () => {
      heroObserver?.disconnect();
    };
  }, [isLiteMode]);

  /* GSAP motion system */
  useLayoutEffect(() => {
    gsap.set("body", { opacity: 1 });

    if (isLiteMode || reducedMotion) {
      return undefined;
    }

    const ctx = gsap.context(() => {
      gsap.fromTo(
        ".navbar",
        { yPercent: -28 },
        {
          yPercent: 0,
          duration: 0.72,
          delay: 0.15,
          ease: "power4.out",
          force3D: true,
          overwrite: "auto",
        }
      );

      const tl = gsap.timeline({ delay: 0.3 });

      tl.from(".hero-badge", {
        y: -10,
        duration: 0.52,
        ease: "power3.out",
        force3D: true,
        overwrite: "auto",
      })
        .from(
          ".hero-word",
          {
            y: 20,
            duration: 0.56,
            ease: "power4.out",
            stagger: 0.05,
            force3D: true,
            overwrite: "auto",
          },
          "-=0.3"
        )
        .from(
          ".hero-subtext",
          {
            y: 12,
            duration: 0.5,
            ease: "power3.out",
            force3D: true,
            overwrite: "auto",
          },
          "-=0.4"
        )
        .from(
          ".hero-buttons",
          {
            y: 10,
            duration: 0.46,
            ease: "power3.out",
            force3D: true,
            overwrite: "auto",
          },
          "-=0.35"
        )
        .from(
          ".hero-trust",
          {
            y: 8,
            duration: 0.4,
            ease: "power2.out",
          },
          "-=0.2"
        )
        .from(
          ".hero-chips",
          {
            y: 10,
            scale: 0.97,
            duration: 0.48,
            ease: "power2.out",
            stagger: 0.1,
          },
          "-=0.6"
        );

      gsap.utils.toArray(".reveal-up").forEach((el, i) => {
        if (el.classList.contains("pipeline-cell") || el.classList.contains("feature-card")) {
          return;
        }

        gsap.fromTo(
          el,
          {
            opacity: 0,
            y: 40,
          },
          {
          scrollTrigger: {
            trigger: el,
            start: "top 88%",
            toggleActions: "play none none none",
          },
          opacity: 1,
          y: 0,
          duration: 0.75,
          ease: "power3.out",
          delay: i * 0.04,
          immediateRender: false,
          force3D: true,
          overwrite: "auto",
        }
        );
      });

      gsap.fromTo(
        ".pipeline-cell",
        {
          opacity: 0,
          y: 32,
        },
        {
        scrollTrigger: {
          trigger: ".pipeline-grid",
          start: "top 80%",
          toggleActions: "play none none none",
        },
        opacity: 1,
        y: 0,
        duration: 0.6,
        ease: "power3.out",
        stagger: 0.07,
        immediateRender: false,
        force3D: true,
        overwrite: "auto",
      }
      );

      gsap.fromTo(
        ".feature-card",
        {
          opacity: 0,
          y: 36,
          scale: 0.97,
        },
        {
        scrollTrigger: {
          trigger: ".features-grid",
          start: "top 80%",
          toggleActions: "play none none none",
        },
        opacity: 1,
        y: 0,
        scale: 1,
        duration: 0.65,
        ease: "power3.out",
        stagger: 0.08,
        immediateRender: false,
        force3D: true,
        overwrite: "auto",
      }
      );

      gsap.utils.toArray(".metric-number").forEach((el) => {
        const target = parseFloat(el.dataset.target || "0");
        const isDecimal = el.dataset.decimal === "true";
        const valueEl = el.querySelector(".metric-value");

        if (!valueEl) return;

        ScrollTrigger.create({
          trigger: el,
          start: "top 85%",
          toggleActions: "play none none none",
          once: true,
          onEnter: () => {
            const counter = { val: 0 };
            gsap.to(counter, {
              val: target,
              duration: 2,
              ease: "power2.out",
              onUpdate: () => {
                const current = counter.val;
                if (isDecimal) {
                  valueEl.textContent = current.toFixed(1).replace(/\.0$/, "");
                } else {
                  valueEl.textContent = String(Math.round(current));
                }
              },
            });
          },
        });
      });
    });

    return () => {
      ctx.revert();
      ScrollTrigger.getAll().forEach((t) => t.kill());
    };
  }, [isLiteMode, reducedMotion]);

  const handleNavClick = () => setIsMobileMenuOpen(false);

  const handleInitialize = useCallback(() => {
    setIsMobileMenuOpen(false);
    navigate(isSignedIn ? "/dashboard" : "/sign-in");
  }, [isSignedIn, navigate]);

  const handleCTAClick = useCallback(() => {
    const targetRoute = isSignedIn ? "/dashboard" : "/sign-in";

    setIsMobileMenuOpen(false);
    navigate(targetRoute);
  }, [isSignedIn, navigate]);

  const handleScrollToPipeline = useCallback(() => {
    setIsMobileMenuOpen(false);
    if (lenisRef.current && pipelineRef.current) {
      lenisRef.current.scrollTo(pipelineRef.current, { offset: -72 });
      return;
    }

    pipelineRef.current?.scrollIntoView({ behavior: "auto", block: "start" });
  }, []);

  /* Running word index for stagger delay */
  let wordIndex = 0;

  return (
    <div className={`landing-page ${isLiteMode ? "lite-mode" : ""}`}>
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
              <a href="#features">System</a>
              <a href="#pipeline">Pipeline</a>
              <a href="#trust-score">Trust Layer</a>
              <a href="#demo">Demo</a>
            </nav>

            <div className="nav-right">
              <button className="nav-cta" type="button" onClick={handleInitialize}>
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
          <a href="#features" onClick={handleNavClick}>System</a>
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
                <span className="hud-chip hero-chips">| Perspective Autopsy ⟳ |</span>
                <span className="hud-chip hero-chips hero-trust">| Trust Score: 87 |</span>
                <span className="hud-chip hero-chips">| Ethical Check ✓ |</span>
                <span className="hud-chip hero-chips">| Multi-Model ◈ |</span>
              </div>

              {/* Hero content */}
              <div className="hero-content">
                {/* Badge */}
                <div className="hero-badge">
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
                          className={`hero-word ${wordObj.accent ? "accent-word" : ""}`}
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
                <p className="hero-subtext">
                  Intellexa runs a 7-layer reasoning pipeline — analyzing your
                  thinking, generating multi-perspective answers, detecting bias,
                  and explaining every step. No black box.
                </p>

                {/* Buttons */}
                <div className="hero-buttons">
                  <button className="hero-btn-primary" type="button" onClick={handleCTAClick}>
                    ▸ Start Reasoning
                  </button>
                  <button className="hero-btn-secondary" type="button" onClick={handleScrollToPipeline}>
                    [ View Pipeline ]
                  </button>
                </div>
              </div>

              {/* Spline Right Column */}
              <div className="hero-spline" ref={heroSplineRef}>
                {isLiteMode ? (
                  <div className="spline-lite-fallback">
                    <span className="spline-lite-chip">[ ADAPTIVE PERFORMANCE MODE ]</span>
                    <p>Smooth rendering enabled for this device profile.</p>
                  </div>
                ) : (
                  <div className="spline-wrapper">
                    {/* Fading Skeleton */}
                    <div className={`spline-skeleton ${isHeroSplineLoaded ? "fade-out" : ""}`}>
                      <span>[ LOADING 3D RENDER... ]</span>
                    </div>

                    {/* Spline Component */}
                    <div className={`spline-container ${isHeroSplineLoaded ? "is-visible" : ""}`}>
                      {shouldRenderHeroSpline && canLoadHeroSpline ? (
                        <Suspense fallback={null}>
                          <Spline
                            scene={SPLINE_SCENE_URL}
                            onLoad={() => setIsHeroSplineLoaded(true)}
                          />
                        </Suspense>
                      ) : null}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Scroll indicator */}
            <span className="scroll-indicator" aria-hidden="true">
              ↓ scroll
            </span>
          </section>

          {/* ── PIPELINE ─────────────────────────── */}
          <section className="pipeline-section" id="pipeline" ref={pipelineRef}>
            <span className="pipeline-label reveal-up">// 01 — SYSTEM PIPELINE</span>
            <h2 className="pipeline-heading reveal-up">The Reasoning Stack</h2>
            <hr className="pipeline-divider" />

            <div className="pipeline-grid">
              {PIPELINE_STEPS.map((step, i) => (
                <div
                  className="pipeline-step pipeline-cell reveal-up"
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
            <div className="pipeline-status-bar reveal-up">
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
            <span className="features-label reveal-up">// 02 — CORE FEATURES</span>
            <h2 className="features-heading reveal-up">Built Different.</h2>
            <p className="features-subheading reveal-up">
              Not another black-box AI.
            </p>

            <div className="bento-grid features-grid">
              {/* Card 1 — Perspective Autopsy (2 cols) */}
              <article
                className="bento-card hud-card feature-card reveal-up card-autopsy card-span-2-col"
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
                className="bento-card hud-card feature-card reveal-up card-trust trust-card card-span-2-row"
                style={{ transitionDelay: "0.07s" }}
              >
                <span className="trust-big-number trust-number">87</span>
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
                className="bento-card hud-card feature-card reveal-up"
                style={{ transitionDelay: "0.14s" }}
              >
                <h3 className="card-small-title">Multi-Perspective</h3>
                <div className="perspective-row" style={{ borderColor: "#4ADE80" }}>
                  <div className="perspective-name">Utilitarian</div>
                  <div className="perspective-desc">Greatest good for the most people</div>
                </div>
                <div className="perspective-row" style={{ borderColor: "var(--violet)" }}>
                  <div className="perspective-name">Rights-Based</div>
                  <div className="perspective-desc">What rights does this decision affect?</div>
                </div>
                <div className="perspective-row" style={{ borderColor: "var(--accent)" }}>
                  <div className="perspective-name">Care Ethics</div>
                  <div className="perspective-desc">Who is made vulnerable here?</div>
                </div>
              </article>

              {/* Card 4 — Explainability Engine (1 col) */}
              <article
                className="bento-card hud-card feature-card reveal-up"
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
                className="bento-card hud-card feature-card reveal-up"
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
                className="bento-card hud-card feature-card reveal-up card-context card-span-2-col"
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
            <span className="metrics-label reveal-up">// 03 — SYSTEM METRICS</span>
            <div className="metrics-row">
              {METRICS.map((m, i) => (
                <MetricCell key={m.label} metric={m} delay={i * 0.1} />
              ))}
            </div>
          </section>

          {/* ── TERMINAL CTA ─────────────────────── */}
          <section className="cta-section" id="demo">
            <div className="cta-spline-background cta-surface-glow" aria-hidden="true" />

            <div className="terminal-frame reveal-up">
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
              <button className="cta-button" type="button" onClick={handleCTAClick}>
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
            Llama · Gemini · Clerk · Supabase · React · Spline · DuckDuckGo
          </span>
          <span className="footer-copy">© 2026 Team Zexters</span>
        </footer>
      </div>
    </div>
  );
}

export default App;
