/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        display: ["Sora", "Inter", "sans-serif"],
      },
      colors: {
        // Institutional light palette — calm, trustworthy, finance-grade.
        paper: "#ffffff",
        page: "#fafaf8",
        line: "#e9e9e4",
        ink: {
          900: "#14181f", // headings
          700: "#2c333d",
          600: "#454d59",
          500: "#5d6572", // body
          400: "#8b93a0", // muted
        },
        accent: {
          50: "#edf7f3",
          100: "#d4ebe2",
          200: "#a9d7c7",
          400: "#3a9e82",
          500: "#138a6c",
          600: "#0f7559", // primary
          700: "#0c6049",
          900: "#08382b",
        },
      },
      borderRadius: {
        xl: "14px",
        "2xl": "18px",
      },
      boxShadow: {
        card: "0 1px 2px rgba(20,24,31,0.04), 0 1px 1px rgba(20,24,31,0.03)",
        lift: "0 12px 32px -16px rgba(20,24,31,0.18)",
        ring: "0 0 0 1px rgba(20,24,31,0.06)",
      },
    },
  },
  plugins: [],
};
