import type { Config } from "tailwindcss";

export default {
  // Light theme only. With "class" rather than the default "media", a dark
  // variant would apply only under a .dark ancestor, which nothing adds — so the
  // app renders light whatever the viewer's OS is set to. The dark variants
  // themselves have been removed from the components; this line is what stops a
  // stray one from ever taking effect.
  darkMode: "class",
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
      },
    },
  },
  plugins: [],
} satisfies Config;
