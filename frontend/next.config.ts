import type { NextConfig } from "next";

/** The backend's base URL. Vercel sets BACKEND_URL; locally the API runs on port 8000. */
const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

/**
 * Next.js settings. Every /api request is forwarded to the backend, so the browser only talks
 * to this origin. agentRules is off so `next dev` does not write an AGENTS.md into the repo,
 * and the dev indicator is off so local screenshots show only the app.
 */
const config: NextConfig = {
  agentRules: false,
  devIndicators: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default config;
