import type { Config } from "tailwindcss";

// Design tokens from docs/mock/radix-mock-v1.html (SPEC §7.2) — the mock is the visual source of truth.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#F1F4F6",
        surface: "#FFFFFF",
        line: "#E0E6EA",
        line2: "#EDF1F3",
        ink: "#182730",
        ink2: "#5D6E77",
        ink3: "#8A9BA4",
        petrol: {
          DEFAULT: "#0E5B66",
          strong: "#0A464F",
          tint: "#E4EEF0",
          mid: "#2E8A97",
        },
        nav: { DEFAULT: "#14262D", 2: "#1E3842" },
        navtext: "#D9E5E8",
        navmut: "#87A0A8",
        amber: {
          DEFAULT: "#E5A13A",
          tint: "#FBF2DF",
          ink: "#8A5A12",
          line: "#EFD3A2",
        },
        ok: { DEFAULT: "#2F7D5B", tint: "#E4F1EA" },
        err: { DEFAULT: "#BC4238", tint: "#F9E9E7" },
      },
      borderRadius: {
        DEFAULT: "10px",
        sm: "8px",
      },
      boxShadow: {
        card: "0 1px 2px rgba(23,39,48,.05), 0 8px 24px rgba(23,39,48,.06)",
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "Segoe UI", "Roboto", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SF Mono", "Cascadia Code", "Consolas", "Liberation Mono", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
