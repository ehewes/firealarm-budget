# The Next.js web app. Build context: the repo root.
#
# Expects apps/web to be a standard Next.js app with a package-lock.json and
# `output: "standalone"` in next.config (see docs/DEPLOYMENT.md). CI only builds this
# image once apps/web/package.json exists.
FROM node:22-alpine AS deps
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY apps/web/ ./
# NEXT_PUBLIC_* values are compiled into the bundle, so they are build arguments
# (GitHub variables, public by design), not runtime secrets.
ARG NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_ANON_KEY \
    NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_GROK_BOT_URL
ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY \
    NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_GROK_BOT_URL=$NEXT_PUBLIC_GROK_BOT_URL \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup -g 10001 -S nodejs && adduser -S -u 10001 -G nodejs nextjs
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
USER nextjs
ARG GIT_SHA=dev
ENV GIT_SHA=$GIT_SHA
EXPOSE 3000
CMD ["node", "server.js"]
