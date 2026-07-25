# 동네사주카페 — Node + 파이썬(Playwright·Chromium·WeasyPrint) 통합 이미지
FROM node:20-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
# WeasyPrint(pango/cairo/gdk-pixbuf) + 기본 유틸/폰트 캐시
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv \
      libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi-dev \
      fontconfig ca-certificates wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) Node 의존성
COPY package*.json ./
RUN npm install --omit=dev

# 2) 파이썬 의존성 + Playwright Chromium(+필요한 OS 라이브러리)
COPY saju_engine/requirements.txt ./saju_engine/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r saju_engine/requirements.txt \
    && python3 -m playwright install --with-deps chromium

# 3) 앱 소스 전체
COPY . .

ENV NODE_ENV=production
ENV PYTHON_BIN=python3
ENV DATA_DIR=/data

EXPOSE 3000
CMD ["node", "server.js"]

