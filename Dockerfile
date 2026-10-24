# Optional: run the pipeline in Docker (ffmpeg included).
#   docker build -t fa-subs .
#   docker run --rm -v "$PWD:/work" fa-subs run video.mp4 --en-srt subs.en.srt
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY fonts ./fonts
RUN pip install --no-cache-dir ".[google]"

ENV FA_SUBS_FONT_DIR=/app/fonts
WORKDIR /work
ENTRYPOINT ["fa-subs"]
CMD ["doctor"]
