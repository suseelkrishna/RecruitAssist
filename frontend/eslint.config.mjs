import next from "eslint-config-next";

/** Lint rules: the Next.js recommended set, including the React hooks and accessibility rules. */
const config = [...next, { ignores: [".next/", "node_modules/", "next-env.d.ts"] }];

export default config;
