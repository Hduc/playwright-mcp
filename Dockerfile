FROM node:22-slim

# Playwright dependencies
RUN apt-get update && apt-get install -y \
    libatomic1 libasound2 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libgbm1 \
    libnspr4 libnss3 libxcomposite1 libxdamage1 \
    libxrandr2 xdg-utils fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --omit=dev 2>/dev/null || npm install

# Cài Chromium (Playwright bundled — không lo glibc)
RUN npx playwright install chromium --with-deps

COPY . .

EXPOSE 8000

# API Key (để trống = không auth, set khi docker run: -e MCP_API_KEY=xxx)
ENV MCP_API_KEY=""

CMD ["node", "server.mjs", "--port", "8000"]
