import os
from celery import Celery
from datetime import datetime
import shutil
from glob import glob

# ============================================
# تنظیمات Celery
# ============================================
celery_app = Celery(
    'image_processor',
    broker='amqp://guest:guest@rabbitmq:5672//',
    include=['tasks']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Tehran',
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry=True,
    broker_connection_max_retries=100,
    broker_connection_retry_delay=5,
)

import db_sync as db
from image_processor import process_image_complete, process_video_complete, get_supported_formats, convert_video_to_hls_adaptive


@celery_app.task(bind=True, name="process_upload_task")
def process_upload_task(self, upload_id: str, component_id: str, original_path: str):
    """پردازش فایل آپلود شده (تصویر یا ویدیوی معمولی)"""
    try:
        self.update_state(state='PROCESSING', meta={'progress': 30, 'status': 'شروع پردازش'})
        
        db.update_temp_upload_status_sync(upload_id, "processing")
        
        file_ext = original_path.split(".")[-1].lower()
        supported = get_supported_formats()
        is_video = file_ext in supported["videos"]
        
        self.update_state(state='PROCESSING', meta={'progress': 60, 'status': 'در حال پردازش فایل...'})
        
        if is_video:
            processed_result = process_video_complete(upload_id, original_path, adaptive=True)
            processed_images = processed_result
        else:
            processed_images = process_image_complete(upload_id, original_path)
        
        self.update_state(state='PROCESSING', meta={'progress': 80, 'status': 'ذخیره در دیتابیس'})
        
        component = db.get_component_by_id_sync(component_id)
        if component:
            current_images = component.get("images", {}) or {}
            if "uploads" not in current_images:
                current_images["uploads"] = {}
            current_images["uploads"][upload_id] = {
                "upload_id": upload_id,
                "processed_images": processed_images,
                "processed_at": datetime.now().isoformat(),
                "file_type": "video" if is_video else "image"
            }
            db.update_component_images_sync(component_id, current_images)
        
        db.update_temp_upload_status_sync(upload_id, "completed", processed_images=processed_images)
        
        if os.path.exists(original_path):
            os.remove(original_path)
        
        return {
            "status": "completed",
            "upload_id": upload_id,
            "file_type": "video" if is_video else "image",
            "processed_data": processed_images
        }
        
    except Exception as e:
        error_msg = str(e)
        db.update_temp_upload_status_sync(upload_id, "failed", error_message=error_msg)
        if os.path.exists(original_path):
            os.remove(original_path)
        self.update_state(state='FAILURE', meta={'error': error_msg})
        raise


@celery_app.task(bind=True, name="process_split_video_task")
def process_split_video_task(self, session_id: str, component_id: str, component_slug: str):
    """پردازش ویدیوی اسپلیت شده - ترکیب قطعات و تبدیل به HLS"""
    VIDEO_PARTS_DIR = "uploads/video_parts"
    
    try:
        self.update_state(state='PROCESSING', meta={'progress': 10, 'status': 'شروع ترکیب قطعات'})
        db.update_video_session_status_sync(session_id, "processing")
        
        part_dir = os.path.join(VIDEO_PARTS_DIR, session_id)
        parts = sorted(glob(os.path.join(part_dir, "*.mp4")), key=lambda x: int(os.path.basename(x).split(".")[0]))
        
        if not parts:
            raise Exception("No parts found for assembly")
        
        self.update_state(state='PROCESSING', meta={'progress': 30, 'status': 'ترکیب قطعات ویدیو'})
        
        merged_path = os.path.join("uploads/final-bucket", f"{session_id}_merged.mp4")
        with open(merged_path, "wb") as out:
            for part in parts:
                with open(part, "rb") as f:
                    out.write(f.read())
        
        self.update_state(state='PROCESSING', meta={'progress': 60, 'status': 'تبدیل به HLS'})
        
        result = convert_video_to_hls_adaptive(merged_path, "uploads/final-bucket", session_id)
        
        if not result.get("success"):
            raise Exception(result.get("error", "HLS conversion failed"))
        
        self.update_state(state='PROCESSING', meta={'progress': 80, 'status': 'ذخیره در دیتابیس'})
        
        component = db.get_component_by_id_sync(component_id)
        if component:
            current_images = component.get("images", {}) or {}
            if "videos" not in current_images:
                current_images["videos"] = {}
            current_images["videos"][session_id] = {
                "session_id": session_id,
                "master_playlist_url": result["master_playlist_url"],
                "qualities": result["qualities"],
                "processed_at": datetime.now().isoformat()
            }
            db.update_component_images_sync(component_id, current_images)
        
        db.update_video_session_status_sync(session_id, "completed", result["master_playlist_url"])
        
        self.update_state(state='SUCCESS', meta={'progress': 100, 'status': 'پردازش کامل شد'})
        
        if os.path.exists(part_dir):
            shutil.rmtree(part_dir)
        if os.path.exists(merged_path):
            os.remove(merged_path)
        
        return {
            "status": "completed",
            "session_id": session_id,
            "master_playlist_url": result["master_playlist_url"],
            "qualities": result["qualities"]
        }
        
    except Exception as e:
        error_msg = str(e)
        db.update_video_session_status_sync(session_id, "failed", error=error_msg)
        part_dir = os.path.join(VIDEO_PARTS_DIR, session_id)
        if os.path.exists(part_dir):
            shutil.rmtree(part_dir)
        self.update_state(state='FAILURE', meta={'error': error_msg})
        raise


@celery_app.task(name="check_upload_status")
def check_upload_status(upload_id: str):
    status = db.get_temp_upload_status_sync(upload_id)
    if status:
        return {
            "upload_id": upload_id,
            "status": status.get("status"),
            "progress": 100 if status.get("status") == "completed" else 50,
            "processed_images": status.get("processed_images")
        }
    return {"error": "Upload not found"}


@celery_app.task(name="cleanup_temp_files")
def cleanup_temp_files():
    import time
    temp_dir = "uploads/temp-mean-io"
    video_parts_dir = "uploads/video_parts"
    deleted_count = 0
    
    if os.path.exists(temp_dir):
        now = time.time()
        for filename in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, filename)
            if os.path.isfile(file_path):
                file_age = now - os.path.getmtime(file_path)
                if file_age > 86400:
                    os.remove(file_path)
                    deleted_count += 1
    
    if os.path.exists(video_parts_dir):
        now = time.time()
        for session_dir in os.listdir(video_parts_dir):
            dir_path = os.path.join(video_parts_dir, session_dir)
            if os.path.isdir(dir_path):
                dir_age = now - os.path.getmtime(dir_path)
                if dir_age > 86400:
                    shutil.rmtree(dir_path)
                    deleted_count += 1
    
    return {"message": f"Cleaned up {deleted_count} old temp files"}