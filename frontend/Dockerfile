FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build

# Static output in /app/dist; the compose service copies it into the volume served by Caddy.
CMD ["sh", "-c", "rm -rf /out/* && cp -r /app/dist/. /out/"]
