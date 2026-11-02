FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir redis "psycopg[binary]" requests
COPY planner.py .
CMD ["python", "-u", "planner.py"]
