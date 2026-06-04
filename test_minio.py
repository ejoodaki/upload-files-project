from minio_client import upload_file_to_minio
import tempfile

# یک فایل تست موقت بساز
with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
    f.write("This is a test file")
    temp_path = f.name

# آپلود در MinIO
url = upload_file_to_minio(temp_path, "test-file.txt")
print(f"File uploaded. URL: {url}")