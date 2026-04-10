import { useEffect, useState } from "react";
import "./styles.css";

function App() {
  const [isScrolled, setIsScrolled] = useState(false);
  const [headlineWords, setHeadlineWords] = useState([]);
  const [isHeroVisible, setIsHeroVisible] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 60);
    };

    handleScroll();
    window.addEventListener("scroll", handleScroll);

    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    const headline = "AI That Thinks Transparently. Answers Responsibly.";
    setHeadlineWords(headline.split(" "));

    const animationTimer = window.setTimeout(() => {
      setIsHeroVisible(true);
    }, 20);

    return () => window.clearTimeout(animationTimer);
  }, []);

  const isGradientWord = (word) => {
    const cleaned = word.replace(/[^a-zA-Z]/g, "");
    return cleaned === "Transparently" || cleaned === "Responsibly";
  };

  return (
    <div className="landing-page">
      <div className="bg-blob blob-1" />
      <div className="bg-blob blob-2" />

      <div className="page-content">
        <header className={`navbar ${isScrolled ? "navbar-scrolled" : ""}`}>
          <div className="navbar-inner">
            <a className="logo" href="#home">
              Intellexa
            </a>

            <nav className="nav-center" aria-label="Primary">
              <a href="#how-it-works">How It Works</a>
              <a href="#features">Features</a>
              <a href="#trust-score">Trust Score</a>
              <a href="#demo">Demo</a>
            </nav>

            <div className="nav-right">
              <button className="try-button" type="button">
                Try Intellexa
              </button>
              <button className="hamburger" type="button" aria-label="Open menu">
                <span />
                <span />
                <span />
              </button>
            </div>
          </div>
        </header>

        <main>
          <section className="hero" id="home">
            <div className={`hero-badge ${isHeroVisible ? "is-visible" : ""}`}>
              <span>✦ Ethical AI · Explainable · Trust-Aware</span>
            </div>

            <h1 className="hero-headline" aria-label="AI That Thinks Transparently. Answers Responsibly.">
              {headlineWords.map((word, index) => (
                <span
                  key={`${word}-${index}`}
                  className={`hero-word ${isHeroVisible ? "is-visible" : ""} ${
                    isGradientWord(word) ? "gradient-word" : ""
                  }`}
                  style={{ transitionDelay: `${0.3 + index * 0.07}s` }}
                >
                  {word}
                  {index < headlineWords.length - 1 ? "\u00A0" : ""}
                </span>
              ))}
            </h1>

            <p
              className={`hero-subtext ${isHeroVisible ? "is-visible" : ""}`}
              style={{ transitionDelay: "0.85s" }}
            >
              Intellexa analyzes your thinking, generates multi-perspective
              answers, checks for bias, and explains every decision — so you
              always know why.
            </p>

            <div
              className={`hero-cta-row ${isHeroVisible ? "is-visible" : ""}`}
              style={{ transitionDelay: "1.0s" }}
            >
              <button className="hero-cta-primary" type="button">
                Start Thinking Better →
              </button>
              <button className="hero-cta-secondary" type="button">
                See How It Works
              </button>
            </div>

            <p
              className={`trust-row ${isHeroVisible ? "is-visible" : ""}`}
              style={{ transitionDelay: "1.0s" }}
            >
              <span className="trust-stars">★★★★★</span> Trusted by researchers,
              students, and teams who need honest AI
            </p>

            <div
              className={`hero-visual-card ${isHeroVisible ? "is-visible" : ""}`}
              style={{ transitionDelay: "1.2s" }}
            >
              <div className="visual-pills">
                <span className="visual-pill visual-pill-autopsy">
                  Perspective Autopsy
                </span>
                <span className="visual-pill visual-pill-answer">
                  Multi-Perspective Answer
                </span>
                <span className="visual-pill visual-pill-trust">
                  Trust Score: 87
                </span>
              </div>

              <div className="visual-divider" />

              <div className="visual-placeholder" role="presentation">
                <span>
                  Context mapped from previous prompts and authenticated memory.
                </span>
                <span>
                  Ethical checks identified framing risks and added fairness
                  mitigation.
                </span>
                <span>
                  Final answer includes reasoning trace, assumptions, and trust
                  metadata.
                </span>
              </div>
            </div>
          </section>

          <section className="section" id="how-it-works">
            <h2>How It Works</h2>
          </section>

          <section className="section" id="features">
            <h3>Features</h3>
          </section>

          <section className="section" id="trust-score">
            <h4>Trust Score</h4>
          </section>

          <section className="section" id="demo">
            <h4>Demo</h4>
          </section>
        </main>
      </div>
    </div>
  );
}

export default App;
