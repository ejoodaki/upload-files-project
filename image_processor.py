import os
import tempfile
import threading
import subprocess
from PIL import Image
from datetime import datetime
import json
import shutil
from typing import Dict, Optional

from minio_client import upload_file_to_minio

# ============================================
# تنظیمات و فرمت‌های پشتیبانی شده
# ============================================

def get_supported_formats() -> Dict:
    """لیست تمام فرمت‌های پشتیبانی شده"""
    return {
        "images": ["jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff"],
        "documents": ["pdf", "doc", "docx", "txt", "md", "json", "xml"],
        "videos": ["mp4", "mov", "avi", "mkv", "webm", "flv", "m4v"],
        "max_size_mb": 100
    }


def validate_file(file_name: str, file_size_mb: float, rules: Dict = None) -> Dict:
    """اعتبارسنجی فایل قبل از آپلود"""
    errors = []
    warnings = []
    
    file_ext = file_name.split(".")[-1].lower()
    supported = get_supported_formats()
    all_supported = supported["images"] + supported["documents"] + supported["videos"]
    
    if file_ext not in all_supported:
        errors.append(f"فرمت فایل پشتیبانی نمی‌شود. فرمت‌های مجاز: {', '.join(all_supported)}")
    
    max_size = rules.get("max_size_mb", 100) if rules else 100
    if file_size_mb > max_size:
        errors.append(f"حجم فایل ({file_size_mb:.2f} مگابایت) بیشتر از حد مجاز ({max_size} مگابایت) است")
    elif file_size_mb > max_size * 0.8:
        warnings.append(f"حجم فایل نزدیک به حد مجاز است ({file_size_mb:.2f}/{max_size} مگابایت)")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "file_ext": file_ext,
        "is_image": file_ext in supported["images"],
        "is_video": file_ext in supported["videos"],
        "file_size_mb": round(file_size_mb, 2)
    }


def get_upload_status_message(status: str) -> Dict:
    """دریافت پیام وضعیت برای نمایش به کاربر"""
    messages = {
        "pending": {"message": "⏳ در صف پردازش...", "color": "orange", "progress": 10},
        "processing": {"message": "🔄 در حال پردازش و بهینه‌سازی...", "color": "blue", "progress": 50},
        "completed": {"message": "✅ پردازش با موفقیت انجام شد!", "color": "green", "progress": 100},
        "failed": {"message": "❌ خطا در پردازش فایل", "color": "red", "progress": 0}
    }
    return messages.get(status, {"message": "وضعیت نامشخص", "color": "gray", "progress": 0})


# ============================================
# توابع کمکی برای قوانین آپلود
# ============================================

def get_rules_for_mime_type(upload_rules: Dict, mime_type: str) -> Dict:
    """
    دریافت قوانین آپلود برای یک MIME Type خاص از آرایه
    """
    rules_by_mime = upload_rules.get("rules_by_mime", [])
    
    # جستجو در آرایه
    specific_rules = {}
    for rule in rules_by_mime:
        if rule.get("mime_type") == mime_type:
            specific_rules = rule.copy()
            break
    
    # حذف mime_type از داخل upload_rules (اضافی است)
    if "mime_type" in specific_rules:
        specific_rules.pop("mime_type")
    
    # حذف quality از داخل upload_rules
    if "quality" in specific_rules:
        specific_rules.pop("quality")
    
    # قوانین پیش‌فرض
    default_rules = upload_rules.get("default", {})
    
    # حذف quality از قوانین پیش‌فرض
    if "quality" in default_rules:
        default_rules.pop("quality")
    
    # ادغام قوانین (قوانین خاص اولویت دارند)
    merged_rules = {**default_rules, **specific_rules}
    
    return merged_rules


def validate_file_by_mime(file_name: str, file_size_mb: float, mime_type: str, upload_rules: Dict) -> Dict:
    """
    اعتبارسنجی فایل بر اساس MIME Type و قوانین آپلود قطعه
    """
    errors = []
    warnings = []
    
    # دریافت قوانین مخصوص این MIME Type
    rules = get_rules_for_mime_type(upload_rules, mime_type)
    
    # بررسی حجم (تبدیل به کیلوبایت)
    max_size_kb = rules.get("max_size_kb", 10240)
    file_size_kb = file_size_mb * 1024
    
    if file_size_kb > max_size_kb:
        errors.append(f"حجم فایل ({file_size_kb:.0f} کیلوبایت) بیشتر از حد مجاز برای نوع {mime_type} ({max_size_kb} کیلوبایت) است")
    elif file_size_kb > max_size_kb * 0.8:
        warnings.append(f"حجم فایل نزدیک به حد مجاز است ({file_size_kb:.0f}/{max_size_kb} کیلوبایت)")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "rules": rules
    }


# ============================================
# توابع پردازش تصویر با MinIO
# ============================================

def resize_and_compress_image(input_path: str, output_path: str, target_size: tuple, quality: int = 85):
    """تغییر سایز و فشرده‌سازی تصویر"""
    with Image.open(input_path) as img:
        img.thumbnail(target_size, Image.Resampling.LANCZOS)
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        img.save(output_path, 'JPEG', quality=quality, optimize=True)
        
        return {
            "width": img.width,
            "height": img.height,
            "size_mb": round(os.path.getsize(output_path) / (1024 * 1024), 2),
            "quality": quality
        }


def process_image(upload_id: str, original_path: str, target_sizes: Dict = None) -> Dict:
    """
    پردازش کامل تصویر و آپلود در MinIO
    """
    if target_sizes is None:
        target_sizes = {
            "mobile": {"width": 640, "height": 480, "quality": 80},
            "tablet": {"width": 1024, "height": 768, "quality": 85},
            "desktop": {"width": 1920, "height": 1080, "quality": 90},
            "thumbnail": {"width": 150, "height": 150, "quality": 75}
        }
    
    processed = {}
    temp_files = []
    
    try:
        for device_type, specs in target_sizes.items():
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                temp_path = tmp_file.name
                
                img_info = resize_and_compress_image(
                    original_path, temp_path,
                    (specs["width"], specs["height"]),
                    specs.get("quality", 85)
                )
                
                object_name = f"{upload_id}_{device_type}.jpg"
                file_url = upload_file_to_minio(temp_path, object_name)
                
                processed[device_type] = {
                    "url": file_url,
                    "width": img_info["width"],
                    "height": img_info["height"],
                    "size_mb": img_info["size_mb"],
                    "quality": img_info["quality"]
                }
                temp_files.append(temp_path)
        
        original_object_name = f"{upload_id}_original.jpg"
        original_url = upload_file_to_minio(original_path, original_object_name)
        processed["original"] = {
            "url": original_url,
            "size_mb": round(os.path.getsize(original_path) / (1024 * 1024), 2),
            "original_name": os.path.basename(original_path)
        }
        
        return processed
        
    finally:
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)


# ============================================
# توابع پردازش ویدیو به HLS
# ============================================

def convert_video_to_hls(input_path: str, output_dir: str, upload_id: str) -> Dict:
    """
    تبدیل ویدیو به فرمت HLS (تکه تکه شده)
    """
    hls_dir = os.path.join(output_dir, f"{upload_id}_hls")
    os.makedirs(hls_dir, exist_ok=True)
    
    playlist_path = os.path.join(hls_dir, "playlist.m3u8")
    
    cmd = [
        "ffmpeg", "-i", input_path,
        "-profile:v", "baseline", "-level", "3.0",
        "-start_number", "0",
        "-hls_time", "4",
        "-hls_list_size", "0",
        "-f", "hls",
        playlist_path
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        segments = [f for f in os.listdir(hls_dir) if f.endswith('.ts')]
        
        hls_files = []
        for file in os.listdir(hls_dir):
            file_path = os.path.join(hls_dir, file)
            object_name = f"{upload_id}_hls/{file}"
            url = upload_file_to_minio(file_path, object_name)
            hls_files.append({"name": file, "url": url})
        
        return {
            "success": True,
            "upload_id": upload_id,
            "playlist_url": f"http://localhost:9000/my-final-bucket/{upload_id}_hls/playlist.m3u8",
            "total_segments": len(segments),
            "segment_duration": 4,
            "files": hls_files,
            "hls_directory": hls_dir
        }
        
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": e.stderr,
            "upload_id": upload_id
        }


def convert_video_to_hls_adaptive(input_path: str, output_dir: str, upload_id: str) -> Dict:
    """
    تبدیل ویدیو به HLS با کیفیت‌های مختلف (240p, 480p, 720p, 1080p)
    """
    hls_dir = os.path.join(output_dir, f"{upload_id}_hls_adaptive")
    os.makedirs(hls_dir, exist_ok=True)
    
    qualities = [
        {"name": "240p", "width": 426, "height": 240, "bitrate": "500k"},
        {"name": "480p", "width": 854, "height": 480, "bitrate": "1000k"},
        {"name": "720p", "width": 1280, "height": 720, "bitrate": "2500k"},
        {"name": "1080p", "width": 1920, "height": 1080, "bitrate": "5000k"}
    ]
    
    master_playlist = "#EXTM3U\n#EXT-X-VERSION:3\n"
    
    for q in qualities:
        quality_dir = os.path.join(hls_dir, q["name"])
        os.makedirs(quality_dir, exist_ok=True)
        playlist_path = os.path.join(quality_dir, "playlist.m3u8")
        
        cmd = [
            "ffmpeg", "-i", input_path,
            "-vf", f"scale={q['width']}:{q['height']}",
            "-b:v", q["bitrate"],
            "-hls_time", "4",
            "-hls_list_size", "0",
            "-hls_segment_filename", f"{quality_dir}/segment_%03d.ts",
            playlist_path
        ]
        
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        master_playlist += f"#EXT-X-STREAM-INF:BANDWIDTH={q['bitrate']},RESOLUTION={q['width']}x{q['height']}\n"
        master_playlist += f"{q['name']}/playlist.m3u8\n"
    
    master_path = os.path.join(hls_dir, "master.m3u8")
    with open(master_path, "w") as f:
        f.write(master_playlist)
    
    for root, dirs, files in os.walk(hls_dir):
        for file in files:
            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, hls_dir)
            object_name = f"{upload_id}_hls/{relative_path}"
            upload_file_to_minio(file_path, object_name)
    
    return {
        "success": True,
        "upload_id": upload_id,
        "master_playlist_url": f"http://localhost:9000/my-final-bucket/{upload_id}_hls/master.m3u8",
        "qualities": [q["name"] for q in qualities]
    }


def process_video_complete(upload_id: str, original_path: str, adaptive: bool = True) -> Dict:
    """نسخه کامل پردازش ویدیو (برای استفاده در Celery)"""
    if adaptive:
        return convert_video_to_hls_adaptive(original_path, "uploads/final-bucket", upload_id)
    else:
        return convert_video_to_hls(original_path, "uploads/final-bucket", upload_id)


def process_image_complete(upload_id: str, original_path: str) -> Dict:
    """نسخه کامل پردازش تصویر (برای استفاده در Celery)"""
    return process_image(upload_id, original_path)


# ============================================
# پردازش غیرهمزمان (Threading) - Fallback
# ============================================

def start_async_processing(upload_id: str, component_id: str, original_path: str, 
                           file_ext: str = None, device_id: str = None):
    """شروع پردازش غیرهمزمان با Threading (در صورت نبود Celery)"""
    
    def process():
        try:
            import crud
            
            print(f"🔄 Processing started for {upload_id}")
            crud.update_temp_upload_status(upload_id, "processing")
            
            is_video = file_ext in get_supported_formats()["videos"] if file_ext else False
            
            if is_video:
                processed_result = process_video_complete(upload_id, original_path, adaptive=True)
                processed_images = processed_result
            else:
                processed_images = process_image(upload_id, original_path)
            
            component = crud.get_component_by_id(component_id)
            if component:
                current_images = component.get("images", {}) or {}
                
                upload_record = {
                    "upload_id": upload_id,
                    "processed_images": processed_images,
                    "processed_at": datetime.now().isoformat()
                }
                
                if device_id:
                    if "by_device" not in current_images:
                        current_images["by_device"] = {}
                    if upload_id not in current_images["by_device"].get(device_id, {}):
                        current_images["by_device"][device_id] = current_images["by_device"].get(device_id, {})
                    current_images["by_device"][device_id][upload_id] = upload_record
                else:
                    if "uploads" not in current_images:
                        current_images["uploads"] = {}
                    current_images["uploads"][upload_id] = upload_record
                
                crud.update_component_images(component_id, current_images)
            
            crud.update_temp_upload_status(upload_id, "completed", processed_images=processed_images)
            
            if os.path.exists(original_path):
                os.remove(original_path)
                
            print(f"✅ Processing completed for {upload_id}")
            
        except Exception as e:
            import crud
            error_msg = str(e)
            print(f"❌ Processing failed for {upload_id}: {error_msg}")
            crud.update_temp_upload_status(upload_id, "failed", error_message=error_msg)
            if os.path.exists(original_path):
                os.remove(original_path)
    
    threading.Thread(target=process, daemon=True).start()
    return {"message": "Processing started", "upload_id": upload_id}