import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
import os

# ============================================
# تنظیمات اتصال به MinIO
# ============================================

# اتصال به MinIO با اسم سرویس در Docker
MINIO_ENDPOINT = 'minio:9000'

# خواندن از متغیرهای محیطی (با مقادیر پیش‌فرض)
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "admin123")
MINIO_BUCKET_NAME = os.getenv("MINIO_BUCKET", "my-final-bucket")
MINIO_SECURE = False  # چون از HTTP استفاده می‌کنیم


def get_minio_client():
    """کلاینت MinIO را برمی‌گرداند"""
    return boto3.client(
        's3',
        endpoint_url=f'http://{MINIO_ENDPOINT}',
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        verify=False
    )


def upload_file_to_minio(file_path, object_name):
    """فایلی را در MinIO آپلود می‌کند و آدرس آن را برمی‌گرداند"""
    client = get_minio_client()
    try:
        client.upload_file(file_path, MINIO_BUCKET_NAME, object_name)
        return f"http://{MINIO_ENDPOINT}/{MINIO_BUCKET_NAME}/{object_name}"
    except Exception as e:
        print(f"Error uploading to MinIO: {e}")
        return None


def get_presigned_url(object_name: str, expires_in: int = 3600):
    """
    تولید یک لینک موقت (Presigned URL) برای دانلود یک فایل از MinIO.
    
    Args:
        object_name: نام فایل در باکت
        expires_in: مدت زمان اعتبار لینک به ثانیه (پیش‌فرض 1 ساعت = 3600 ثانیه)
    
    Returns:
        str: لینک موقت دانلود یا None در صورت خطا
    """
    client = get_minio_client()
    try:
        url = client.generate_presigned_url(
            ClientMethod='get_object',
            Params={
                'Bucket': MINIO_BUCKET_NAME,
                'Key': object_name
            },
            ExpiresIn=expires_in
        )
        return url
    except ClientError as e:
        print(f"Error generating presigned URL for {object_name}: {e}")
        return None


def get_presigned_url_for_hls(upload_id: str, quality: str = "master", expires_in: int = 3600):
    """
    تولید لینک موقت برای پخش HLS (ویدیو)
    
    Args:
        upload_id: شناسه آپلود
        quality: کیفیت مورد نظر (master, 240p, 480p, 720p, 1080p)
        expires_in: مدت اعتبار لینک به ثانیه
    """
    if quality == "master":
        object_name = f"{upload_id}_hls/master.m3u8"
    else:
        object_name = f"{upload_id}_hls/{quality}/playlist.m3u8"
    
    return get_presigned_url(object_name, expires_in)


def delete_file_from_minio(object_name: str) -> bool:
    """حذف یک فایل از MinIO"""
    client = get_minio_client()
    try:
        client.delete_object(Bucket=MINIO_BUCKET_NAME, Key=object_name)
        return True
    except ClientError as e:
        print(f"Error deleting {object_name} from MinIO: {e}")
        return False


def list_bucket_contents(prefix: str = "") -> list:
    """لیست محتویات باکت (برای دیباگ)"""
    client = get_minio_client()
    try:
        response = client.list_objects_v2(Bucket=MINIO_BUCKET_NAME, Prefix=prefix)
        objects = response.get('Contents', [])
        return [obj['Key'] for obj in objects]
    except ClientError as e:
        print(f"Error listing bucket contents: {e}")
        return []