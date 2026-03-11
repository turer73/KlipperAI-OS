import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // KlipperOS-AI brand palette
        kos: {
          bg: "#0a0e17",
          card: "#111827",
          border: "#1e293b",
          accent: "#3b82f6",     // blue-500
          success: "#22c55e",    // green-500
          warning: "#f59e0b",    // amber-500
          danger: "#ef4444",     // red-500
          muted: "#64748b",      // slate-500
          text: "#e2e8f0",       // slate-200
        },
      },
      animation: {
        "pulse-slow": "pulse 3s ease-in-out infinite",
        "spin-slow": "spin 3s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
