import os

KEYCLOAK_ISSUER = "https://sso.procurehub.example/realms/procurehub"
KEYCLOAK_AUDIENCE = "procurehub-api"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "paybridge-demo")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://procurehub:procurehub@postgres:5432/procurehub",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://minio:9000")
S3_BUCKET = os.getenv("S3_BUCKET", "procurehub-invoices")
OBJECT_STORAGE_BASE = os.getenv(
    "OBJECT_STORAGE_BASE",
    "https://storage.procurehub.example",
)
