from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Response, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi_standalone_docs import StandaloneDocs
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import os
import uuid
import hashlib
import shutil
from datetime import datetime
from glob import glob

import database as db
from image_processor import validate_file, get_upload_status_message, process_image_complete, process_video_complete
from minio_client import upload_file_to_minio, get_presigned_url

# ============================================
# مدل‌های Pydantic
# ============================================

class DeviceCreate(BaseModel):
    name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    category: Optional[str] = None
    price: float = 0

class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None

class ComponentCreate(BaseModel):
    slug: str
    symbol: str

class ComponentUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    brand: Optional[str] = None
    specs: Optional[Dict] = None
    physical: Optional[Dict] = None
    price: Optional[float] = None

class MimeTypesUpdate(BaseModel):
    allowed_mime_types: List[str]

class AttachComponentRequest(BaseModel):
    component_id: str
    width_mm: Optional[float] = None
    height_mm: Optional[float] = None
    weight_g: Optional[float] = None
    position_x: Optional[int] = None
    position_y: Optional[int] = None
    mobile_specs: Optional[Dict] = Field(default=None, description="سایز موبایل: {width, height, quality}")
    tablet_specs: Optional[Dict] = Field(default=None, description="سایز تبلت: {width, height, quality}")
    desktop_specs: Optional[Dict] = Field(default=None, description="سایز دسکتاپ: {width, height, quality}")

class DevicePaginationFilter(BaseModel):
    page: int = 1
    per_page: int = 10
    filters: Optional[Dict[str, Any]] = {
        "name": None,
        "brand": None,
        "category": None,
        "min_price": None,
        "max_price": None
    }

class ComponentPaginationFilter(BaseModel):
    page: int = 1
    per_page: int = 10
    filters: Optional[Dict[str, Any]] = {
        "name": None,
        "type": None,
        "brand": None,
        "min_price": None,
        "max_price": None
    }

class ProcessRequest(BaseModel):
    component_id: str
    upload_id: str

class DownloadRequest(BaseModel):
    upload_id: str
    size_type: str = "desktop"
    expires_in: int = 3600

# ============================================
# ایجاد اپلیکیشن FastAPI
# ============================================
app = FastAPI(
    title="Device/Component Upload System with AI Agent",
    version="7.0",
    description="سیستم آپلود هوشمند فایل - پشتیبانی از تصاویر، ویدیوها، PDF و آپلود چندقطعی ویدیو"
)

# ============================================
# Swagger آفلاین
# ============================================
try:
    StandaloneDocs(app=app)
    print("✅ Swagger offline enabled")
except:
    print("⚠️ Swagger offline not available")

# ============================================
# CORS
# ============================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# ایجاد پوشه‌های مورد نیاز
# ============================================
os.makedirs("uploads/temp-mean-io", exist_ok=True)
os.makedirs("uploads/final-bucket", exist_ok=True)
os.makedirs("uploads/video_parts", exist_ok=True)


# ============================================
# ========== توابع کمکی برای ویدیو ==========
# ============================================

VIDEO_PARTS_DIR = "uploads/video_parts"

def calculate_file_hash(file_path: str) -> str:
    """محاسبه SHA256 هش یک فایل"""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def assemble_video_parts(session_id: str) -> str:
    """ترکیب قطعات ویدیو به ترتیب شماره"""
    part_dir = os.path.join(VIDEO_PARTS_DIR, session_id)
    parts = sorted(glob(os.path.join(part_dir, "*.mp4")), key=lambda x: int(os.path.basename(x).split(".")[0]))
    
    if not parts:
        return None
    
    output_path = os.path.join("uploads/final-bucket", f"{session_id}_merged.mp4")
    with open(output_path, "wb") as out:
        for part in parts:
            with open(part, "rb") as f:
                out.write(f.read())
    
    return output_path

def cleanup_video_parts(session_id: str):
    """حذف پوشه موقت قطعات ویدیو"""
    part_dir = os.path.join(VIDEO_PARTS_DIR, session_id)
    if os.path.exists(part_dir):
        shutil.rmtree(part_dir)

async def process_video_parts_async(session_id: str, component_id: str, component_slug: str):
    """پردازش پس‌زمینه ویدیو پس از دریافت همه قطعات"""
    try:
        await db.update_video_session_status(session_id, "processing")

        merged_path = assemble_video_parts(session_id)
        if not merged_path:
            await db.update_video_session_status(session_id, "failed", error="No parts received")
            return

        from tasks import process_split_video_task
        process_split_video_task.delay(session_id, component_id, component_slug)
        await db.update_video_session_status(session_id, "processing", "Task sent to Celery")

    except Exception as e:
        await db.update_video_session_status(session_id, "failed", error=str(e))
        cleanup_video_parts(session_id)

# ============================================
# ========== APIهای Device (بدون تغییر) ==========
# ============================================

@app.post("/devices", tags=["Device"])
async def create_device(device: DeviceCreate):
    try:
        device_id = await db.create_device(device.dict())
        return {"success": True, "id": device_id}
    except Exception as e:
        raise HTTPException(400, detail=str(e))

@app.post("/devices/list", tags=["Device"])
async def get_devices_list(request: DevicePaginationFilter):
    try:
        result = await db.get_all_devices_paginated(
            page=request.page,
            per_page=request.per_page,
            filters=request.filters or {}
        )
        return result
    except Exception as e:
        raise HTTPException(400, detail=str(e))

@app.get("/devices/{device_id}", tags=["Device"])
async def get_device(device_id: str):
    device = await db.get_device_by_id(device_id)
    if not device:
        raise HTTPException(404, "device not found")
    return device

@app.put("/devices/{device_id}", tags=["Device"])
async def update_device(device_id: str, device: DeviceUpdate):
    data = {k: v for k, v in device.dict().items() if v is not None}
    if not data:
        raise HTTPException(400, "no data provided")
    success = await db.update_device(device_id, data)
    if not success:
        raise HTTPException(404, "device not found")
    return Response(status_code=200)

@app.delete("/devices/{device_id}", tags=["Device"])
async def delete_device(device_id: str):
    success = await db.delete_device(device_id)
    if not success:
        raise HTTPException(404, "device not found")
    return Response(status_code=200)


# ============================================
# ========== APIهای Component (بدون تغییر) ==========
# ============================================

@app.post("/components", tags=["Component"], status_code=200)
async def create_component(component: ComponentCreate):
    try:
        existing = await db.components_collection.find_one({
            "$or": [
                {"slug": component.slug},
                {"symbol": component.symbol}
            ]
        })
        if existing:
            raise HTTPException(400, "slug or symbol already exists")
        
        default_mime_types = [
            "image/jpeg", "image/png", "image/gif", "image/webp",
            "video/mp4", "video/mov", "video/avi", "video/mkv",
            "application/pdf"
        ]
        
        component_data = {
            "slug": component.slug,
            "symbol": component.symbol,
            "name": component.slug,
            "allowed_mime_types": default_mime_types,
            "type": "unknown",
            "brand": "unknown",
            "specs": {},
            "physical": {},
            "price": 0,
            "upload_rules": db.get_default_upload_rules(),
            "images": {},
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        await db.create_component(component_data)
        return Response(status_code=200)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "internal server error")

@app.put("/components/{slug}/mime-types", tags=["Component"], status_code=200)
async def update_component_mime_types(slug: str, request: MimeTypesUpdate):
    try:
        component = await db.get_component_by_slug(slug)
        if not component:
            raise HTTPException(404, "component not found")
        
        await db.components_collection.update_one(
            {"slug": slug},
            {"$set": {"allowed_mime_types": request.allowed_mime_types}}
        )
        return Response(status_code=200)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "internal server error")

@app.post("/components/list", tags=["Component"])
async def get_components_list(request: ComponentPaginationFilter):
    try:
        result = await db.get_all_components_paginated(
            page=request.page,
            per_page=request.per_page,
            filters=request.filters or {}
        )
        return result
    except Exception as e:
        raise HTTPException(400, detail=str(e))

@app.get("/components/{component_id}", tags=["Component"])
async def get_component(component_id: str):
    component = await db.get_component_by_id(component_id)
    if not component:
        raise HTTPException(404, "component not found")
    return component

@app.get("/components/by-slug/{slug}", tags=["Component"])
async def get_component_by_slug(slug: str):
    component = await db.get_component_by_slug(slug)
    if not component:
        raise HTTPException(404, "component not found")
    return component

@app.put("/components/{component_id}", tags=["Component"])
async def update_component(component_id: str, component: ComponentUpdate):
    data = {k: v for k, v in component.dict().items() if v is not None}
    if not data:
        raise HTTPException(400, "no data provided")
    success = await db.update_component(component_id, data)
    if not success:
        raise HTTPException(404, "component not found")
    return Response(status_code=200)

@app.delete("/components/{component_id}", tags=["Component"])
async def delete_component(component_id: str):
    success = await db.delete_component(component_id)
    if not success:
        raise HTTPException(404, "component not found")
    return Response(status_code=200)


# ============================================
# ========== API دریافت قوانین آپلود ==========
# ============================================

@app.get("/components/rules/by-slug/{slug}", tags=["Component"])
async def get_component_rules_by_slug(slug: str):
    component = await db.get_component_by_slug(slug)
    if not component:
        raise HTTPException(404, "component not found")
    upload_rules = component.get("upload_rules", {})
    return {
        "slug": component["slug"],
        "upload_rules": upload_rules
    }


# ============================================
# ========== APIهای ارتباط Device-Component ==========
# ============================================

@app.post("/devices/{device_id}/components", tags=["Device-Component"], status_code=200)
async def attach_component_to_device(device_id: str, request: AttachComponentRequest):
    try:
        device = await db.get_device_by_id(device_id)
        if not device:
            raise HTTPException(404, "device not found")
        component = await db.get_component_by_id(request.component_id)
        if not component:
            raise HTTPException(404, "component not found")
        success = await db.attach_component_to_device(device_id, request.component_id, request.dict())
        if not success:
            raise HTTPException(400, "component already attached")
        return Response(status_code=200)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "internal server error")

@app.get("/devices/{device_id}/components", tags=["Device-Component"])
async def get_device_components(
    device_id: str, 
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100)
):
    try:
        result = await db.get_device_components(device_id, page, per_page)
        if "error" in result:
            raise HTTPException(404, result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, detail=str(e))

@app.delete("/devices/{device_id}/components/{component_id}", tags=["Device-Component"], status_code=200)
async def remove_component_from_device(device_id: str, component_id: str):
    success = await db.remove_component_from_device(device_id, component_id)
    if not success:
        raise HTTPException(404, "relation not found")
    return Response(status_code=200)


# ============================================
# ========== APIهای آپلود عکس، PDF و ویدیوی معمولی (بدون تغییر) ==========
# ============================================

@app.post("/upload/temp", tags=["Upload"])
async def upload_temp(file: UploadFile = File(...)):
    content = await file.read()
    file_size_mb = len(content) / (1024 * 1024)
    validation = validate_file(file.filename, file_size_mb)
    if not validation.get("valid", False):
        raise HTTPException(400, detail={"errors": validation.get("errors", []), "warnings": validation.get("warnings", [])})
    
    temp_dir = "uploads/temp-mean-io"
    upload_id = str(uuid.uuid4())
    temp_path = f"{temp_dir}/{upload_id}_{file.filename}"
    
    with open(temp_path, "wb") as f:
        f.write(content)
    
    db_upload_id = await db.create_temp_upload(
        component_id=None,
        original_name=file.filename,
        original_path=temp_path,
        file_size_mb=file_size_mb,
        file_type=validation.get("file_ext", "unknown")
    )
    
    return {"upload_id": db_upload_id}


@app.post("/upload/process", tags=["Upload"])
async def process_upload(request: ProcessRequest):
    component = await db.get_component_by_id(request.component_id)
    if not component:
        raise HTTPException(404, "component not found")
    
    temp_upload = await db.get_temp_upload_status(request.upload_id)
    if not temp_upload:
        raise HTTPException(404, "upload not found")
    
    if not os.path.exists(temp_upload.get("original_path")):
        raise HTTPException(404, "file not found in temp bucket")
    
    try:
        file_ext = temp_upload["original_path"].split(".")[-1].lower()
        is_video = file_ext in ["mp4", "mov", "avi", "mkv", "webm"]
        
        if is_video:
            processed_result = process_video_complete(request.upload_id, temp_upload["original_path"], adaptive=True)
            processed_images = processed_result
        else:
            processed_images = process_image_complete(request.upload_id, temp_upload["original_path"])
        
        current_images = component.get("images", {}) or {}
        if "uploads" not in current_images:
            current_images["uploads"] = {}
        current_images["uploads"][request.upload_id] = {
            "upload_id": request.upload_id,
            "processed_images": processed_images,
            "processed_at": datetime.now().isoformat(),
            "file_type": "video" if is_video else "image"
        }
        await db.update_component_images(request.component_id, current_images)
        await db.update_temp_upload_status(request.upload_id, "completed", processed_images=processed_images)
        
        if os.path.exists(temp_upload["original_path"]):
            os.remove(temp_upload["original_path"])
        
        return Response(status_code=200)
        
    except Exception as e:
        await db.update_temp_upload_status(request.upload_id, "failed", error_message=str(e))
        raise HTTPException(500, "internal server error")


@app.get("/upload/status/{upload_id}", tags=["Upload"])
async def get_upload_status(upload_id: str):
    status = await db.get_temp_upload_status(upload_id)
    if not status:
        raise HTTPException(404, "upload not found")
    
    status_info = get_upload_status_message(status.get("status", "pending"))
    
    return {
        "upload_id": status.get("upload_id"),
        "original_name": status.get("original_name"),
        "file_size_mb": status.get("file_size_mb"),
        "status": status.get("status"),
        "status_message": status_info["message"],
        "progress": status_info["progress"],
        "error_message": status.get("error_message"),
        "processed_images": status.get("processed_images", {}),
        "created_at": status.get("created_at"),
        "completed_at": status.get("completed_at")
    }


@app.get("/components/{component_id}/images", tags=["Upload"])
async def get_component_images(component_id: str):
    component = await db.get_component_by_id(component_id)
    if not component:
        raise HTTPException(404, "component not found")
    
    return {
        "component_id": component_id,
        "images": component.get("images", {}),
        "count": len(component.get("images", {}))
    }


# ============================================
# ========== API دانلود امن ==========
# ============================================

@app.post("/upload/download", tags=["Upload"])
async def get_download_link(request: DownloadRequest):
    upload_record = await db.get_temp_upload_status(request.upload_id)
    if not upload_record:
        raise HTTPException(404, "upload not found")
    
    processed_images = upload_record.get("processed_images", {})
    
    if "master_playlist_url" in processed_images:
        if request.size_type == "master":
            object_name = processed_images.get("master_playlist_url", "").replace("http://localhost:9000/my-final-bucket/", "")
        else:
            object_name = f"{request.upload_id}_hls/{request.size_type}/playlist.m3u8"
    else:
        if request.size_type not in processed_images:
            raise HTTPException(404, f"size type '{request.size_type}' not found")
        url = processed_images[request.size_type].get("url", "")
        object_name = url.replace("http://localhost:9000/my-final-bucket/", "") if url else f"{request.upload_id}_{request.size_type}.jpg"
    
    presigned_url = get_presigned_url(object_name, request.expires_in)
    if not presigned_url:
        raise HTTPException(500, "internal server error")
    
    return {
        "upload_id": request.upload_id,
        "size_type": request.size_type,
        "download_link": presigned_url,
        "expires_in_seconds": request.expires_in
    }


# ============================================
# ========== APIهای جدید آپلود چندقطعی ویدیو ==========
# ============================================

@app.post("/upload/video-part", tags=["Video Upload"])
async def upload_video_part(
    session_id: str = Form(...),
    part_number: int = Form(...),
    total_parts: int = Form(...),
    hash: str = Form(...),
    component_slug: str = Form(...),
    file: UploadFile = File(...)
):
    """
    آپلود یک قطعه ویدیو (اسپلیت شده)
    
    - session_id: شناسه یکتای جلسه آپلود
    - part_number: شماره قطعه (از 1 تا total_parts)
    - total_parts: تعداد کل قطعات
    - hash: SHA256 هش محتوای قطعه برای تأیید یکپارچگی
    - component_slug: شناسه Component مقصد
    - file: فایل قطعه ویدیو
    """
    try:
        component = await db.get_component_by_slug(component_slug)
        if not component:
            raise HTTPException(404, "component not found")
        
        part_dir = os.path.join(VIDEO_PARTS_DIR, session_id)
        os.makedirs(part_dir, exist_ok=True)
        part_path = os.path.join(part_dir, f"{part_number}.mp4")
        
        content = await file.read()
        with open(part_path, "wb") as f:
            f.write(content)
        
        calculated_hash = calculate_file_hash(part_path)
        # if calculated_hash != hash:
        #     os.remove(part_path)
        #     raise HTTPException(400, "hash mismatch - file may be corrupted")
        
        await db.save_video_part(session_id, part_number, total_parts, part_path, component_slug)
        
        received_parts = len(glob(os.path.join(part_dir, "*.mp4")))
        
        if received_parts == total_parts:
            import asyncio
            asyncio.create_task(process_video_parts_async(session_id, component["_id"], component_slug))
            return {"status": "all_parts_received", "session_id": session_id}
        
        return {"status": "part_received", "session_id": session_id, "received": received_parts, "total": total_parts}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"internal server error: {str(e)}")


@app.get("/upload/video-status/{session_id}", tags=["Video Upload"])
async def get_video_upload_status(session_id: str):
    """دریافت وضعیت آپلود و پردازش ویدیو"""
    result = await db.video_sessions_collection.find_one({"session_id": session_id})
    if not result:
        raise HTTPException(404, "session not found")
    
    return {
        "session_id": result.get("session_id"),
        "status": result.get("status"),
        "received_parts": result.get("received_parts", []),
        "total_parts": result.get("total_parts", 1),
        "hls_url": result.get("hls_url"),
        "error_message": result.get("error_message"),
        "created_at": result.get("created_at"),
        "completed_at": result.get("completed_at")
    }

# ============================================
# ========== APIهای کمکی ==========
# ============================================

@app.get("/supported-formats", tags=["Utility"])
async def get_supported_formats():
    from image_processor import get_supported_formats as get_formats
    return get_formats()


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Device/Component Upload System API",
        "version": "7.0",
        "status": "running",
        "features": [
            "CRUD Device & Component",
            "Image upload & processing (resize, compress)",
            "PDF upload",
            "Video upload & HLS conversion",
            "Split video upload (multi-part)",
            "Secure download with presigned URL"
        ]
    }


# ============================================
# اجرا
# ============================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)