import path from "node:path";

import type { NextConfig } from "next";

// This app's own folder. Without it Next infers the repo root (it holds another
// package-lock.json) and nests the standalone server under apps/web/, which is not
// where deploy/web.Dockerfile looks.
const appRoot = path.resolve(__dirname);

const nextConfig: NextConfig = {
  // A self-contained server bundle, which is what deploy/web.Dockerfile ships.
  output: "standalone",
  outputFileTracingRoot: appRoot,
  turbopack: { root: appRoot },
  poweredByHeader: false,
};

export default nextConfig;
