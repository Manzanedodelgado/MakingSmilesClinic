// El backend interno (mismo host que el server de Next). Configurable por entorno;
// por defecto localhost:8000 (desarrollo). En producción el rewrite real lo hace
// vercel.json (/api/* -> https://app.ms.rubiogarciadental.com/*).
const BACKEND = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";
// `next dev` evalúa código (recarga en caliente) y la CSP de producción lo bloquea.
const EVAL_DEV = process.env.NODE_ENV === "production" ? "" : " 'unsafe-eval'";
const path = require("path");
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  reactStrictMode: true,
  htmlLimitedBots: /.*/,
  allowedDevOrigins: ["100.86.41.61", "192.168.1.46", "ms.rubiogarciadental.com"],
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: false },
  // El proxy /api → backend corta a los 30 s por defecto; el análisis de IA tarda ~30 s.
  experimental: { proxyTimeout: 180_000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND}/:path*` }];
  },
  headers: async () => [
    {
      source: "/(.*)",
      headers: [
        { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
        { key: "Cross-Origin-Embedder-Policy", value: "require-corp" },
        {
          key: "Content-Security-Policy",
          value:
            `default-src 'self'; script-src 'self' 'wasm-unsafe-eval' 'unsafe-inline'${EVAL_DEV}; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://app.ms.rubiogarciadental.com; font-src 'self' data:; connect-src 'self' https://app.ms.rubiogarciadental.com wss://app.ms.rubiogarciadental.com; worker-src blob:;`,
        },
      ],
    },
  ],
  webpack: (config) => {
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      "/assets": path.resolve(__dirname, "public/assets"),
    };
    config.module.rules.push({
      test: /node_modules\/dental-cbct-viewer\/.*\.js$/,
      type: "asset/resource",
    });
    config.module.noParse = [/public\/assets/];
    return config;
  },
};

export default nextConfig;
