import { useEffect, useMemo, useState } from "react";
import Particles, { initParticlesEngine } from "@tsparticles/react";
import { loadSlim } from "@tsparticles/slim";

function AuthParticles() {
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    initParticlesEngine(async (engine) => {
      await loadSlim(engine);
    }).then(() => {
      setIsReady(true);
    });
  }, []);

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
      fpsLimit: 60,
      detectRetina: true,
      particles: {
        number: {
          value: 70,
          density: {
            enable: true,
            area: 900,
          },
        },
        color: {
          value: ["#4DFFD2", "#7B6FFF", "#A8E6FF"],
        },
        links: {
          enable: true,
          distance: 140,
          color: "#4DFFD2",
          opacity: 0.12,
          width: 1,
        },
        move: {
          enable: true,
          speed: 0.9,
          direction: "none",
          outModes: {
            default: "bounce",
          },
        },
        opacity: {
          value: {
            min: 0.15,
            max: 0.5,
          },
        },
        size: {
          value: {
            min: 1,
            max: 2.8,
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
    []
  );

  if (!isReady) {
    return null;
  }

  return <Particles className="auth-particles" options={options} />;
}

export default AuthParticles;