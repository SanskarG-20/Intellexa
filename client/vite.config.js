import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 3000,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;

          if (id.includes("@tsparticles")) return "vendor-particles";
          if (id.includes("@clerk")) return "vendor-clerk";
          if (id.includes("react-router")) return "vendor-router";
          if (id.includes("gsap") || id.includes("lenis")) return "vendor-motion";
          if (
            id.includes("/node_modules/react/") ||
            id.includes("/node_modules/react-dom/") ||
            id.includes("/node_modules/scheduler/")
          ) {
            return "vendor-react";
          }

          return undefined;
        },
      },
    },
  },
});
