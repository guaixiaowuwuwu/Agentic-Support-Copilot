FROM node:22-alpine AS deps

WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
COPY packages/shared/package.json ./packages/shared/package.json
RUN npm ci

FROM deps AS builder

WORKDIR /app
ARG NEXT_PUBLIC_API_BASE=/support-api
ARG NEXT_PUBLIC_SUPPORT_COPILOT_ENV=staging
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE \
    NEXT_PUBLIC_SUPPORT_COPILOT_ENV=$NEXT_PUBLIC_SUPPORT_COPILOT_ENV \
    NEXT_TELEMETRY_DISABLED=1
COPY apps/web ./apps/web
COPY packages/shared ./packages/shared
RUN npm --workspace apps/web run build

FROM node:22-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    SUPPORT_COPILOT_API_BASE=http://api:8000 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs

COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/static ./apps/web/.next/static

USER nextjs
WORKDIR /app/apps/web
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000').then((r)=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
