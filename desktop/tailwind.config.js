/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        base:    "#0b0b12",
        surface: "#111120",
        raised:  "#191930",
        border:  "#252540",
        accent:  "#7c6af5",
        "accent-light": "#9f8fff",
        "accent-dim":   "rgba(124,106,245,0.15)",
        "surface-2": "rgba(124,106,245,0.06)",
        "border-strong": "#3a3a60",
        muted:   "#6060a0",
        primary: "#e8e8f4",
        secondary: "#8888b8",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      keyframes: {
        fadeIn:  { from: { opacity: "0", transform: "translateY(6px)" }, to: { opacity: "1", transform: "translateY(0)" } },
        blink:   { "0%,100%": { opacity: "1" }, "50%": { opacity: "0" } },
        shimmer: { from: { backgroundPosition: "200% center" }, to: { backgroundPosition: "-200% center" } },
        pulse2:  { "0%,100%": { opacity: ".4" }, "50%": { opacity: "1" } },
      },
      animation: {
        fadeIn:  "fadeIn 0.2s ease-out",
        blink:   "blink 1s step-end infinite",
        shimmer: "shimmer 3s linear infinite",
        pulse2:  "pulse2 1.5s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
