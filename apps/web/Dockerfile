# syntax=docker/dockerfile:1
# Drikr Systems training simulator web client, served by an unprivileged nginx
# that also reverse-proxies /api to the API container. Build context: repository root.
#   docker build -f apps/web/Dockerfile -t drikr-web:1.0.0 .

# Node >= 22.22 is required by the test toolchain (jsdom 30); the build uses the same runtime.
FROM node:22.23.3-alpine3.23 AS build
WORKDIR /src/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
COPY packages/contracts/schemas/ /src/packages/contracts/schemas/
COPY packages/simcore/drikr_simcore/demo_scenarios/ /src/packages/simcore/drikr_simcore/demo_scenarios/
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27.2-alpine AS runtime
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/apps/web/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
