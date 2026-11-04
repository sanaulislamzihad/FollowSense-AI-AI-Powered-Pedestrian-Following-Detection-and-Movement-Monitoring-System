# ---- 1. build the React dashboard ----
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 2. Python API + AI pipeline ----
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 libgl1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt .
# CPU wheels of torch keep the image small; use the CUDA index for GPU hosts.
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
RUN pip install torch torchvision --index-url ${TORCH_INDEX} && pip install -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist ./static
# fetch the pretrained YOLO weights at build time so the container works offline
RUN python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"
ENV FS_DATA_DIR=/data FS_YOLO_MODEL=/app/yolo11n.pt
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
