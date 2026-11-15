# CropStory web image (ABB-30): static build served by Caddy, which also proxies /api to the API
# container. TLS terminates at the Cloudflare tunnel in front of it.
FROM node:24-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM caddy:2.10-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /src/dist /srv
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=4s --start-period=10s --retries=4 \
  CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/"]
