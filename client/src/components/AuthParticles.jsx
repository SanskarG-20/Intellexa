import { useEffect, useMemo, useState } from "react";
import Particles, { initParticlesEngine } from "@tsparticles/react";
import { loadSlim } from "@tsparticles/slim";

function getParticlesMode() {
  if (typeof window === "undefined") {
    return { disable: true, compact: true };
  }

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const compact = window.matchMedia("(max-width: 1024px)").matches;
  const hardwareConcurrency = navigator.hardwareConcurrency ?? 4;
  const deviceMemory = navigator.deviceMemory ?? 4;
  const saveData = navigator.connection?.saveData === true;
  const networkType = navigator.connection?.effectiveType;
  const constrainedNetwork = networkType === "2g" || networkType === "3g" || networkType === "slow-2g";

  const disable =
    reducedMotion ||
    compact ||
    saveData ||
    constrainedNetwork ||
    hardwareConcurrency <= 4 ||
    deviceMemory <= 4;

  return { disable, compact };
}

function AuthParticles() {
  const [mode, setMode] = useState(() => getParticlesMode());
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;

    const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const compactQuery = window.matchMedia("(max-width: 1024px)");
    const updateMode = () => setMode(getParticlesMode());

    updateMode();

    if (typeof reducedMotionQuery.addEventListener === "function") {
      reducedMotionQuery.addEventListener("change", updateMode);
      compactQuery.addEventListener("change", updateMode);
    } else {
      reducedMotionQuery.addListener(updateMode);
      compactQuery.addListener(updateMode);
    }

    window.addEventListener("resize", updateMode);

    return () => {
      if (typeof reducedMotionQuery.removeEventListener === "function") {
        reducedMotionQuery.removeEventListener("change", updateMode);
        compactQuery.removeEventListener("change", updateMode);
      } else {
        reducedMotionQuery.removeListener(updateMode);
        compactQuery.removeListener(updateMode);
      }

      window.removeEventListener("resize", updateMode);
    };
  }, []);

  useEffect(() => {
    if (mode.disable) {
      setIsReady(false);
      return undefined;
    }

    let isMounted = true;

    initParticlesEngine(async (engine) => {
      await loadSlim(engine);
    }).then(() => {
      if (isMounted) {
        setIsReady(true);
      }
    });

    return () => {
      isMounted = false;
    };
  }, [mode.disable]);

  const options = useMemo(
    () => ({
      fullScreen: {
        enable: false,
      },
      background: {
        color: {
          value: "transparent",
        },
      },
      fpsLimit: 35,
      detectRetina: false,
      pauseOnBlur: true,
      particles: {
        number: {
          value: mode.compact ? 20 : 34,
          density: {
            enable: true,
            area: mode.compact ? 1200 : 1000,
          },
        },
        color: {
          value: ["#4DFFD2", "#7B6FFF", "#A8E6FF"],
        },
        links: {
          enable: !mode.compact,
          distance: 120,
          color: "#4DFFD2",
          opacity: 0.08,
          width: 1,
        },
        move: {
          enable: true,
          speed: mode.compact ? 0.35 : 0.55,
          direction: "none",
          outModes: {
            default: "out",
          },
        },
        opacity: {
          value: {
            min: 0.08,
            max: 0.28,
          },
        },
        size: {
          value: {
            min: 1,
            max: mode.compact ? 2 : 2.4,
          },
        },
      },
      interactivity: {
        events: {
          onHover: {
            enable: false,
            mode: "grab",
          },
          onClick: {
            enable: false,
            mode: "push",
          },
          resize: true,
        },
      },
    }),
    [mode.compact]
  );

  if (mode.disable || !isReady) {
    return null;
  }

  return <Particles className="auth-particles" options={options} />;
}

export default AuthParticles;