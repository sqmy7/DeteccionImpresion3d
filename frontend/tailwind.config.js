/** @type {import('tailwindcss').Config} */
// Colors come from CSS variables (src/index.css), so the whole palette lives in one place.
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: token("canvas"),
        surface: {
          DEFAULT: token("surface"),
          2: token("surface-2"),
          3: token("surface-3"),
        },
        line: token("line"),
        fg: token("fg"),
        muted: token("muted"),
        faint: token("faint"),
        accent: { DEFAULT: token("accent"), fg: token("accent-fg") },
        ok: { DEFAULT: token("ok"), fg: token("ok-fg") },
        warn: { DEFAULT: token("warn"), fg: token("warn-fg") },
        danger: { DEFAULT: token("danger"), fg: token("danger-fg") },
        info: { DEFAULT: token("info"), fg: token("info-fg") },
      },
      fontFamily: {
        // System fonts on purpose: the lab network may have no internet for web fonts.
        sans: ["ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "sans-serif"],
        mono: ["ui-monospace", "Cascadia Mono", "Consolas", "Menlo", "monospace"],
      },
      keyframes: {
        shimmer: { "100%": { transform: "translateX(100%)" } },
      },
      animation: {
        shimmer: "shimmer 1.4s infinite",
      },
    },
  },
  plugins: [],
};
