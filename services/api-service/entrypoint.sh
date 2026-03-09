#!/bin/sh
echo "Waiting for MySQL to be ready..."
until python -c "
import pymysql, os, sys
try:
    pymysql.connect(host=os.getenv('DB_HOST'), user=os.getenv('DB_USER'),
                    password=os.getenv('DB_PASSWORD'), database=os.getenv('DB_NAME'))
    sys.exit(0)
except Exception as e:
    print(f'MySQL not ready: {e}')
    sys.exit(1)
"; do
  sleep 2
done
echo "MySQL is ready. Starting api-service..."
cd /app/src
exec uvicorn main:app --host 0.0.0.0 --port 8000
