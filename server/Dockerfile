FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

ARG INSTALL_OPTIONAL_ML=false

# Copy repository context (root or service subdirectory) and install dependencies
# in a context-agnostic way so Railway builds are stable.
COPY . ./

RUN python -m pip install --upgrade pip && \
        if [ -f /app/server/requirements.txt ]; then \
            python -m pip install -r /app/server/requirements.txt; \
        else \
            python -m pip install -r /app/requirements.txt; \
        fi && \
        if [ "$INSTALL_OPTIONAL_ML" = "true" ]; then \
            if [ -f /app/server/requirements-optional-ml.txt ]; then \
                python -m pip install -r /app/server/requirements-optional-ml.txt; \
            elif [ -f /app/requirements-optional-ml.txt ]; then \
                python -m pip install -r /app/requirements-optional-ml.txt; \
            fi; \
        fi

EXPOSE 8000

CMD ["sh", "-c", "if [ -d /app/server/app ]; then cd /app/server; fi; python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
