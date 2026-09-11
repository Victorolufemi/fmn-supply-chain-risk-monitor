/**
 * Flat ESLint config.
 *
 * eslint-config-next 16 ships native flat configs, so the `FlatCompat` shim that
 * `create-next-app` scaffolds is no longer needed — and in fact breaks, because
 * the compat layer cannot serialise the plugin graph it now returns.
 */
import coreWebVitals from "eslint-config-next/core-web-vitals";
import typescript from "eslint-config-next/typescript";

const config = [
  { ignores: [".next/**", "node_modules/**", "out/**", "next-env.d.ts"] },
  ...coreWebVitals,
  ...typescript,
];

export default config;
