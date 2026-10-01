# The hosted copy (docs/HOSTING.md): Sorted in a Cloudflare container, one per visitor, behind the Worker in
# cloudflare/. The Worker turns on hosted mode and the Workers AI model when it starts each container. Run on its own,
# this image is an ordinary Sorted with cached readings only, and remote callers still need the council password.
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.5 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 FT_CLASSIFIER=cache
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev
COPY . .
# The photos for phones are made once here, so a new container only re-dates the demo data (a few seconds).
RUN python scripts/build_seed.py
EXPOSE 8800
CMD ["sh", "scripts/hosted_start.sh"]
