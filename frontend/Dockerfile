# ── Stage 1: Build React app ──────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci --silent           # ci = clean install, faster and reproducible than npm install
COPY . .
RUN npm run build             # Outputs to /app/dist

# ── Stage 2: Serve with Nginx ─────────────────────────────────────────────────
# nginx:alpine is ~25MB — perfect for serving static files
FROM nginx:alpine AS production

# Copy built static files
COPY --from=builder /app/dist /usr/share/nginx/html

# Custom nginx config to handle React Router (SPA routing)
# Without this, refreshing any route except / returns 404
RUN echo 'server { \
    listen 80; \
    location / { \
        root /usr/share/nginx/html; \
        try_files $uri $uri/ /index.html; \
    } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
