FROM python:3.12-slim

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin acquire
WORKDIR /app
COPY tools/kite_acquire/ /app/tools/kite_acquire/
RUN chown -R 10001:10001 /app
USER 10001:10001
ENTRYPOINT ["python", "-m", "tools.kite_acquire"]
