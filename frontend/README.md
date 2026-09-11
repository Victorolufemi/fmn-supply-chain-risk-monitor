# Frontend — Supply Chain Risk Monitor

Next.js 16 · TypeScript · Tailwind CSS · Recharts. Deployable to Vercel.

Full project documentation is in the [repository README](../README.md); the complete feature-by-feature walkthrough is in [`docs/HOW_IT_WORKS.md`](../docs/HOW_IT_WORKS.md).

## Quick start

```bash
npm install
cp ../.env.example .env.local   # then set NEXT_PUBLIC_API_URL
npm run dev
```

Open <http://localhost:3000> — it redirects to `/supply-chain`. The backend must
be running (see [Backend setup](../README.md#19-backend-setup)).

## Scripts

| Command                | Purpose                  |
| ---------------------- | ------------------------ |
| `npm run dev`          | Development server       |
| `npm run build`        | Production build         |
| `npm run lint`         | ESLint (flat config)     |
| `npm run typecheck`    | `tsc --noEmit`           |
| `npm run format`       | Prettier, write in place |
| `npm run format:check` | Prettier, verify only    |

## Theming

Light theme only. `tailwind.config.ts` sets `darkMode: "class"` and nothing ever
adds that class, so the app renders light regardless of the viewer's OS setting;
`color-scheme: light` in `globals.css` makes the browser paint its own chrome
(form controls, scrollbars) to match.

Gradients are defined once as CSS custom properties in `globals.css`
(`--grad-page`, `--grad-brand`, `--grad-critical`, …) and applied through the
`.grad-*` and `.surface-gradient` helper classes. They are deliberately
low-contrast surface treatment: the only colours carrying meaning are the risk
colours, and a gradient must never compete with them. Chart fills use SVG
`<linearGradient>` defs, since Recharts needs a paint reference rather than a CSS
class.

## Environment

| Variable              | Purpose                                                                     |
| --------------------- | --------------------------------------------------------------------------- |
| `NEXT_PUBLIC_API_URL` | Backend base URL. Local `http://localhost:8000`; production the Render URL. |

`NEXT_PUBLIC_` values are inlined into the shipped JavaScript and are publicly
readable, so **never** put a secret in one. The Anthropic key lives on the backend
only; this app never contacts Anthropic directly.

## What lives where

```
app/
  supply-chain/page.tsx              dashboard: KPIs, charts, Ask panel, table
  supply-chain/sku/[skuId]/page.tsx  drill-down: risk, policy, drivers, charts
  supply-chain/model/page.tsx        model transparency: metrics, validation, limits
components/                          presentational only — no business logic
lib/api.ts                           the single place that talks to the backend
types/api.ts                         mirrors backend/app/schemas/models.py
```

This app contains **no** ML logic, risk arithmetic, thresholds, model files or
secrets. Every number it shows was computed by the API.
