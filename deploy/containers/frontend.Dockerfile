FROM node:18.20.8-bookworm-slim AS environment
WORKDIR /app/frontend
COPY modules/access/web/package*.json ./
RUN npm ci --no-audit --no-fund
FROM environment AS development
ENV HOME=/tmp BROWSER=none
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--strictPort"]
FROM environment AS runtime
COPY modules/access/web ./
COPY deploy/containers/frontend-server.mjs /app/frontend-server.mjs
RUN npm test && npm run build
ARG REVISION=unknown
ENV HXJM_REVISION=$REVISION BROWSER=none HOME=/tmp
LABEL org.opencontainers.image.revision=$REVISION
CMD ["node", "/app/frontend-server.mjs"]
