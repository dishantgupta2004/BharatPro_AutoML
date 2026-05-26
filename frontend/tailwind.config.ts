import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
    "./hooks/**/*.{ts,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
      colors: {
        // Surface — deep zinc/slate for premium dark canvas
        canvas: {
          900: "#09090b", // page bg (zinc-950 deeper)
          800: "#0f172a", // panel bg (slate-900)
          700: "#18181b", // raised panel (zinc-900)
          600: "#1e293b", // hover surface (slate-800)
          500: "#27272a", // border subtle (zinc-800)
          400: "#3f3f46", // border strong (zinc-700)
        },
        // Foreground — crisp contrast scale
        fg: {
          50: "#fafafa",  // headings (zinc-50)
          100: "#e4e4e7", // body (zinc-200)
          200: "#a1a1aa", // muted (zinc-400)
          300: "#71717a", // subtle (zinc-500)
          400: "#52525b", // disabled (zinc-600)
        },
        // Brand — indigo, used sparingly for accents
        accent: {
          50:  "#eef2ff",
          100: "#e0e7ff",
          400: "#818cf8",
          500: "#6366f1",
          600: "#4f46e5",
          700: "#4338ca",
        },
        // Status traffic-light
        status: {
          online: "#10b981",   // emerald-500
          processing: "#f59e0b", // amber-500
          offline: "#71717a",  // zinc-500
          error: "#ef4444",    // red-500
        },
      },
      boxShadow: {
        // Premium subtle shadows that read well on dark surfaces
        glow:    "0 0 0 1px rgba(99,102,241,0.15), 0 8px 24px -8px rgba(99,102,241,0.25)",
        elevate: "0 1px 0 rgba(255,255,255,0.04) inset, 0 8px 24px rgba(0,0,0,0.35)",
        ring:    "0 0 0 1px rgba(255,255,255,0.06)",
      },
      ringColor: {
        DEFAULT: "rgba(99,102,241,0.4)",
      },
      backgroundImage: {
        "grid-fade":
          "linear-gradient(to bottom, rgba(9,9,11,0) 0%, rgba(9,9,11,1) 70%)",
        "panel-divider":
          "linear-gradient(180deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0) 100%)",
      },
      animation: {
        "pulse-soft": "pulse 2.5s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "slide-in":   "slide-in 0.18s ease-out",
      },
      keyframes: {
        "slide-in": {
          "0%":   { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;