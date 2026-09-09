# ================================
# Stage 1: Build
# ================================
FROM node:20.19-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build arg: permite override en docker-compose.local.yml (ARG "" -> runtime env.js)
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

# ================================
# Stage 2: Production (nginx)
# ================================
FROM nginx:1.27-alpine

# Create non-root user
RUN addgroup -g 1001 -S appgroup && \
    adduser -S appuser -u 1001 -G appgroup

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Custom nginx config for SPA routing
RUN echo 'server { \
    listen 8080; \
    server_name _; \
    root /usr/share/nginx/html; \
    index index.html; \
    \
    # Security headers \
    add_header X-Frame-Options "SAMEORIGIN" always; \
    add_header X-Content-Type-Options "nosniff" always; \
    add_header X-XSS-Protection "1; mode=block" always; \
    add_header Referrer-Policy "strict-origin-when-cross-origin" always; \
    \
    # Cross-Origin Isolation — required for SharedArrayBuffer (FFmpeg.wasm). \
    # credentialless COEP allows CDN resources without explicit CORP headers. \
    add_header Cross-Origin-Opener-Policy "same-origin" always; \
    add_header Cross-Origin-Embedder-Policy "credentialless" always; \
    \
    # Gzip compression \
    gzip on; \
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/javascript image/svg+xml; \
    gzip_min_length 256; \
    \
    # Cache static assets \
    location /assets/ { \
    expires 1y; \
    add_header Cache-Control "public, immutable"; \
    } \
    \
    # SPA routing - serve index.html for all non-file routes \
    location / { \
    try_files $uri $uri/ /index.html; \
    } \
    }' > /etc/nginx/conf.d/default.conf

# Runtime env.js (envsubst) — permite VITE_API_BASE_URL sin rebuild
RUN printf '#!/bin/sh\n\
cat > /usr/share/nginx/html/env.js <<EOF\n\
window.__ENV__ = { VITE_API_BASE_URL: "${VITE_API_BASE_URL:-}" };\n\
EOF\n\
# inyecta <script src="/env.js"> si no existe\n\
if ! grep -q "env.js" /usr/share/nginx/html/index.html; then sed -i "s|</head>|<script src=\"/env.js\"></script></head>|" /usr/share/nginx/html/index.html; fi\n\
exec nginx -g "daemon off;"\n' > /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

# Remove default nginx config
RUN rm -f /etc/nginx/conf.d/default.conf.bak

ENV PORT=8080
EXPOSE 8080

RUN chown -R appuser:appgroup /usr/share/nginx/html /var/cache/nginx /var/log/nginx /etc/nginx/conf.d && \
    touch /var/run/nginx.pid && chown appuser:appgroup /var/run/nginx.pid
USER appuser
ENTRYPOINT ["/docker-entrypoint.sh"]
