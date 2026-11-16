# Build context is the repo root (needs packages/api-types for type checking).
FROM node:22-alpine AS deps
WORKDIR /repo/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /repo
ENV NEXT_TELEMETRY_DISABLED=1
COPY packages/api-types ./packages/api-types
COPY apps/web ./apps/web
COPY --from=deps /repo/apps/web/node_modules ./apps/web/node_modules
WORKDIR /repo/apps/web
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S rsv && adduser -S rsv -G rsv
COPY --from=build --chown=rsv:rsv /repo/apps/web/.next/standalone ./
COPY --from=build --chown=rsv:rsv /repo/apps/web/.next/static ./.next/static
COPY --from=build --chown=rsv:rsv /repo/apps/web/public ./public
USER rsv
EXPOSE 3000
CMD ["node", "server.js"]
