import requests
import time
import threading

API_URL = "http://127.0.0.1:8000"

# ============================================
# مقادیر را با مقادیر واقعی خود جایگزین کنید
# ============================================
COMPONENT_ID = "6d2e2f16-607b-4636-93fa-b3de7c18d13c"  # ID کامپوننت خود را وارد کنید
IMAGE_PATH = "C:/Users/MTC/Desktop/device_component_upload/test.jpg"  # مسیر یک عکس واقعی
# ============================================

results = []

def upload_file(index):
    """ارسال یک درخواست آپلود"""
    try:
        # مرحله 1: آپلود موقت
        with open(IMAGE_PATH, 'rb') as f:
            temp_res = requests.post(
                f"{API_URL}/upload/temp",
                files={"file": f}
            )
        
        if temp_res.status_code != 200:
            results.append({"index": index, "error": f"Temp upload failed: {temp_res.text}"})
            print(f"❌ درخواست {index} - آپلود موقت خطا: {temp_res.status_code}")
            return
        
        upload_id = temp_res.json().get("upload_id")
        
        # مرحله 2: درخواست پردازش
        process_res = requests.post(
            f"{API_URL}/upload/process",
            json={"component_id": COMPONENT_ID, "upload_id": upload_id}
        )
        
        if process_res.status_code != 200:
            results.append({"index": index, "error": f"Process failed: {process_res.text}"})
            print(f"❌ درخواست {index} - پردازش خطا: {process_res.status_code}")
            return
        
        results.append({
            "index": index,
            "upload_id": upload_id,
            "task_id": process_res.json().get("task_id"),
            "status": "accepted"
        })
        print(f"✅ درخواست {index} پذیرفته شد - upload_id: {upload_id}")
        
    except Exception as e:
        results.append({"index": index, "error": str(e)})
        print(f"❌ درخواست {index} خطا: {e}")

# اجرای 10 درخواست همزمان
print("🚀 ارسال 10 درخواست همزمان...")
start_time = time.time()

threads = []
for i in range(1, 11):
    t = threading.Thread(target=upload_file, args=(i,))
    threads.append(t)
    t.start()

# منتظر اتمام همه درخواست‌ها
for t in threads:
    t.join()

end_time = time.time()
print(f"\n📊 زمان ارسال همه درخواست‌ها: {end_time - start_time:.2f} ثانیه")
print(f"📊 تعداد درخواست‌های پذیرفته شده: {len([r for r in results if 'error' not in r])}")

# نمایش نتیجه
print("\n📋 نتیجه درخواست‌ها:")
for r in results:
    if 'error' in r:
        print(f"  ❌ {r['index']}: {r['error']}")
    else:
        print(f"  ✅ {r['index']}: upload_id={r['upload_id']}, task_id={r['task_id']}")