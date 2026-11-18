FROM python:3.12-slim
WORKDIR /app
COPY backend /app/backend

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN --mount=type=secret,id=build_ca,mode=0444 \
    if [ -f /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi \
    && chmod -R a+rX /app/backend \
    && pip install --no-cache-dir -r backend/requirements.txt \
    && useradd --system --uid 10001 identityops

USER identityops
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--root-path", "/api"]
