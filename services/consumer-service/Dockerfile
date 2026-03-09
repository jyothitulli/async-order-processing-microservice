FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY entrypoint.sh /entrypoint.sh
COPY entrypoint_relayer.sh /entrypoint_relayer.sh
RUN chmod +x /entrypoint.sh /entrypoint_relayer.sh

ENTRYPOINT ["/entrypoint.sh"]
