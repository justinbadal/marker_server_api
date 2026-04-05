FROM node:20-alpine AS deps
WORKDIR /app
ARG NEXT_PUBLIC_MARKER_API_BASE_URL
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
ARG NEXT_PUBLIC_MARKER_API_BASE_URL
ENV NEXT_PUBLIC_MARKER_API_BASE_URL=$NEXT_PUBLIC_MARKER_API_BASE_URL
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# Production runner using standalone output (much smaller image)
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
ARG NEXT_PUBLIC_MARKER_API_BASE_URL
ENV NEXT_PUBLIC_MARKER_API_BASE_URL=$NEXT_PUBLIC_MARKER_API_BASE_URL

# Copy standalone server and required static files
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
