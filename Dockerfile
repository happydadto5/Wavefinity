# Wavefinity on Hugging Face Spaces (Docker SDK).
FROM python:3.14-slim

# System libraries the geometry stack needs at runtime.
#   libglib2.0-0 -> opencv-python-headless
#   libgomp1     -> numpy / opencv threading
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Spaces runs the container as uid 1000; give that user a home and a writable app dir.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH="/home/user/.local/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    WAVEFINITY_PID_FILE=/tmp/wavefinity.pid

WORKDIR /app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .

EXPOSE 7860
CMD ["python", "wavefinity_web.py", "--host", "0.0.0.0", "--port", "7860", "--no-browser"]
