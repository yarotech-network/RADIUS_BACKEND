# --- build ----------------------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# --- serve ----------------------------------------------------------------
# The nginx image renders /etc/nginx/templates/*.template with envsubst on
# container start. API_UPSTREAM (default below) is where /api and /health are
# proxied — point it at the Django/Gunicorn service, e.g.
#   docker run -e API_UPSTREAM=http://django:8000 -p 8080:80 ...
FROM nginx:1.27-alpine
ENV API_UPSTREAM=http://127.0.0.1:8000
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
