import boto3

from .config import OBJECT_STORAGE_BASE, S3_BUCKET, S3_ENDPOINT_URL


def s3_client():
    return boto3.client("s3", endpoint_url=S3_ENDPOINT_URL)


def save_pdf(storage_key: str, pdf_bytes: bytes) -> None:
    client = s3_client()
    client.put_object(
        Bucket=S3_BUCKET,
        Key=storage_key,
        Body=pdf_bytes,
        ContentType="application/pdf",
    )


def public_object_url(storage_key: str) -> str:
    return f"{OBJECT_STORAGE_BASE}/{storage_key}"
