/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        base:    "#070B1A",
        surface: "#0E1430",
        raised:  "#141C40",
        border:  "#24306B",
        accent:  "#3B24C8",
        "accent-light": "#6B7CFF",
        "accent-dim":   "rgba(59,36,200,0.16)",
        "surface-2": "rgba(35,61,255,0.10)",
        "border-strong": "#334392",
        muted:   "#868686",
        primary: "#EDF1FF",
        secondary: "#B5C0EC",
      },
      fontFamily: {
        sans: ["Poppins", "Articulat CF", "system-ui", "sans-serif"],
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
