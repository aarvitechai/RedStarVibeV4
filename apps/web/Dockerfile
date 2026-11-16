FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S rsv && adduser -S rsv -G rsv
COPY --from=build --chown=rsv:rsv /app/.next/standalone ./
COPY --from=build --chown=rsv:rsv /app/.next/static ./.next/static
COPY --from=build --chown=rsv:rsv /app/public ./public
USER rsv
EXPOSE 3000
CMD ["node", "server.js"]
