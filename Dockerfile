FROM node:22-alpine

# curl: Coolify sağlık kontrolü için
RUN apk add --no-cache curl

WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
ENV DATA_DIR=/data

# package-lock.json varsa onu kullanır; yoksa package.json'dan kurar
COPY package*.json ./
RUN npm install --omit=dev && npm cache clean --force

COPY src ./src

# Kalıcı veri (yüklenen rapor): Coolify > Persistent Storage'da /data için volume tanımlayın
RUN mkdir -p /data && chown node:node /data
VOLUME ["/data"]

USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD curl -fsS http://127.0.0.1:3000/health || exit 1
CMD ["npx", "tsx", "src/index.ts"]
