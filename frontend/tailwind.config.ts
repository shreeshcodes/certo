import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#0b0f19", 900: "#111827", 800: "#1f2937", 700: "#374151" },
      },
    },
  },
  plugins: [],
};
export default config;
