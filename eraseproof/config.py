import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://lab:lab@localhost:5432/eraseproof")
BROKER_URL = os.getenv("BROKER_URL", "amqp://lab:lab@localhost:5672/%2F")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SEARCH_URL = os.getenv("SEARCH_URL", "http://localhost:9200")
INSPECTION_TOKEN = os.getenv("INSPECTION_TOKEN", "")
SERVICE = os.getenv("SERVICE", "customer")
