import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        fond: "rgb(var(--fond) / <alpha-value>)",
        carte: "rgb(var(--carte) / <alpha-value>)",
        encre: "rgb(var(--encre) / <alpha-value>)",
        attenue: "rgb(var(--attenue) / <alpha-value>)",
        ligne: "rgb(var(--ligne) / <alpha-value>)",
        marine: "rgb(var(--marine) / <alpha-value>)",
        action: "rgb(var(--action) / <alpha-value>)",
        action2: "rgb(var(--action2) / <alpha-value>)",
        rouge: "rgb(var(--rouge) / <alpha-value>)",
        orange: "rgb(var(--orange) / <alpha-value>)",
        vert: "rgb(var(--vert) / <alpha-value>)",
        gris: "rgb(var(--gris) / <alpha-value>)",
        survol: "rgb(var(--survol) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["'Inter Variable'", "Inter", "system-ui", "sans-serif"],
        arabe: ["'IBM Plex Sans Arabic'", "'Inter Variable'", "sans-serif"],
      },
      borderRadius: { "2xl": "1rem", xl: "0.75rem" },
      boxShadow: {
        carte: "0 1px 2px rgb(15 23 42 / 0.04), 0 1px 3px rgb(15 23 42 / 0.06)",
        levee: "0 10px 30px -12px rgb(15 23 42 / 0.25)",
      },
      keyframes: {
        "shimmer": { "100%": { transform: "translateX(100%)" } },
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
export default config;
