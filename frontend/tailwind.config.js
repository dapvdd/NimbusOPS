/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
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
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      colors: {
        // NimbusOps dark ops palette
        ink: {
          950: "#0b0f14",
          900: "#0f141a",
          850: "#121820",
          800: "#161d27",
          700: "#1d2633",
          600: "#2a3648",
          500: "#3b4a61",
          400: "#5d7290",
          300: "#8ba3c2",
          200: "#b7c8de",
          100: "#dbe6f3",
        },
        surface: {
          0: "#0b0f14",
          1: "#0f141a",
          2: "#121820",
          3: "#161d27",
          muted: "#1d2633",
          elevated: "#121820",
          border: "#2a3648",
        },
        border: {
          subtle: "#1d2633",
          strong: "#2a3648",
        },
        signal: {
          ok: "#34d399",
          warn: "#fbbf24",
          bad: "#f87171",
          info: "#60a5fa",
          revoked: "#a78bfa",
          pending: "#60a5fa",
        },
      },
    },
  },
  plugins: [],
};
