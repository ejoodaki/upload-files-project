from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import uuid
import re
from typing import Optional, Dict, Any

# ============================================
# تنظیمات اتصال به MongoDB (در Docker با اسم سرویس)
# ============================================

MONGODB_URL = "mongodb://admin:admin123@mongodb:27017"
DATABASE_NAME = "device_component_ai"

# اتصال به دیتابیس
client = AsyncIOMotorClient(MONGODB_URL)
database = client[DATABASE_NAME]

# کالکشن‌ها
devices_collection = database["devices"]
components_collection = database["components"]
uploads_collection = database["uploads"]
temp_uploads_collection = database["temp_uploads"]
device_component_collection = database["device_component"]
video_sessions_collection = database["video_sessions"]  # جدید برای ویدیوهای چندقطعی


# ============================================
# توابع کمکی
# ============================================

def generate_slug(name: str) -> str:
    """تبدیل نام به slug"""
    slug = name.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


def get_default_upload_rules() -> Dict[str, Any]:
    """قوانین پیش‌فرض آپلود برای قطعات (با ساختار آرایه)"""
    return {
        "default": {
            "max_size_kb": 10240,
            "min_width": 100,
            "min_height": 100,
            "max_width": 4000,
            "max_height": 4000
        },
        "rules_by_mime": [
            {
                "mime_type": "image/jpeg",
                "max_size_kb": 5120,
                "min_width": 200,
                "min_height": 200,
                "max_width": 3000,
                "max_height": 3000
            },
            {
                "mime_type": "image/jpg",
                "max_size_kb": 5120,
                "min_width": 200,
                "min_height": 200,
                "max_width": 3000,
                "max_height": 3000
            },
            {
                "mime_type": "image/png",
                "max_size_kb": 5120,
                "min_width": 200,
                "min_height": 200,
                "max_width": 3000,
                "max_height": 3000
            },
            {
                "mime_type": "image/gif",
                "max_size_kb": 2048,
                "max_width": 800,
                "max_height": 600
            },
            {
                "mime_type": "image/webp",
                "max_size_kb": 3072,
                "min_width": 100,
                "min_height": 100,
                "max_width": 3000,
                "max_height": 3000
            },
            {
                "mime_type": "video/mp4",
                "max_size_kb": 51200,
                "max_duration_seconds": 60,
                "min_width": 480,
                "min_height": 360
            },
            {
                "mime_type": "video/mov",
                "max_size_kb": 51200,
                "max_duration_seconds": 60,
                "min_width": 480,
                "min_height": 360
            },
            {
                "mime_type": "video/avi",
                "max_size_kb": 30720,
                "max_duration_seconds": 30,
                "min_width": 480,
                "min_height": 360
            },
            {
                "mime_type": "video/mkv",
                "max_size_kb": 40960,
                "max_duration_seconds": 45,
                "min_width": 480,
                "min_height": 360
            },
            {
                "mime_type": "video/webm",
                "max_size_kb": 51200,
                "max_duration_seconds": 60,
                "min_width": 480,
                "min_height": 360
            },
            {
                "mime_type": "application/pdf",
                "max_size_kb": 10240
            }
        ]
    }


# ============================================
# Device CRUD
# ============================================

async def create_device(data: Dict[str, Any]) -> str:
    """ایجاد دستگاه جدید"""
    device_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    device = {
        "_id": device_id,
        "name": data.get("name"),
        "brand": data.get("brand"),
        "model": data.get("model"),
        "category": data.get("category"),
        "price": data.get("price", 0),
        "created_at": now,
        "updated_at": now
    }
    await devices_collection.insert_one(device)
    return device_id


async def get_all_devices_paginated(page: int = 1, per_page: int = 10, filters: Dict = None) -> Dict[str, Any]:
    """دریافت لیست دستگاه‌ها با Pagination"""
    skip = (page - 1) * per_page
    query = {}
    
    if filters:
        if filters.get("name"):
            query["name"] = {"$regex": filters["name"], "$options": "i"}
        if filters.get("brand"):
            query["brand"] = filters["brand"]
        if filters.get("category"):
            query["category"] = filters["category"]
        if filters.get("min_price"):
            query["price"] = {"$gte": filters["min_price"]}
        if filters.get("max_price"):
            query["price"] = {"$lte": filters["max_price"]}
    
    total = await devices_collection.count_documents(query)
    cursor = devices_collection.find(query).sort("created_at", -1).skip(skip).limit(per_page)
    devices = await cursor.to_list(length=per_page)
    
    for device in devices:
        device["_id"] = str(device["_id"])
    
    return {
        "data": devices,
        "pagination": {
            "currentPage": page,
            "perPage": per_page,
            "totalRecords": total,
            "totalPages": (total + per_page - 1) // per_page
        }
    }


async def get_device_by_id(device_id: str) -> Optional[Dict[str, Any]]:
    """دریافت یک دستگاه با ID"""
    device = await devices_collection.find_one({"_id": device_id})
    if device:
        device["_id"] = str(device["_id"])
    return device


async def update_device(device_id: str, data: Dict[str, Any]) -> bool:
    """به‌روزرسانی دستگاه"""
    data["updated_at"] = datetime.now().isoformat()
    result = await devices_collection.update_one({"_id": device_id}, {"$set": data})
    return result.modified_count > 0


async def delete_device(device_id: str) -> bool:
    """حذف دستگاه"""
    result = await devices_collection.delete_one({"_id": device_id})
    return result.deleted_count > 0


# ============================================
# Component CRUD (با allowed_mime_types)
# ============================================

async def create_component(data: Dict[str, Any]) -> str:
    """ایجاد قطعه جدید"""
    component_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    
    component = {
        "_id": component_id,
        "slug": data.get("slug"),
        "symbol": data.get("symbol"),
        "name": data.get("slug"),
        "allowed_mime_types": data.get("allowed_mime_types", []),
        "type": "unknown",
        "brand": "unknown",
        "specs": {},
        "physical": {},
        "price": 0,
        "upload_rules": data.get("upload_rules", get_default_upload_rules()),
        "images": {},
        "created_at": now,
        "updated_at": now
    }
    await components_collection.insert_one(component)
    return component_id


async def get_all_components_paginated(page: int = 1, per_page: int = 10, filters: Dict = None) -> Dict[str, Any]:
    """دریافت لیست قطعات با Pagination"""
    skip = (page - 1) * per_page
    query = {}
    
    if filters:
        if filters.get("name"):
            query["name"] = {"$regex": filters["name"], "$options": "i"}
        if filters.get("slug"):
            query["slug"] = filters["slug"]
        if filters.get("symbol"):
            query["symbol"] = filters["symbol"]
        if filters.get("type"):
            query["type"] = filters["type"]
        if filters.get("brand"):
            query["brand"] = filters["brand"]
        if filters.get("min_price"):
            query["price"] = {"$gte": filters["min_price"]}
        if filters.get("max_price"):
            query["price"] = {"$lte": filters["max_price"]}
    
    total = await components_collection.count_documents(query)
    cursor = components_collection.find(query).sort("created_at", -1).skip(skip).limit(per_page)
    components = await cursor.to_list(length=per_page)
    
    for comp in components:
        comp["_id"] = str(comp["_id"])
    
    return {
        "data": components,
        "pagination": {
            "currentPage": page,
            "perPage": per_page,
            "totalRecords": total,
            "totalPages": (total + per_page - 1) // per_page
        }
    }


async def get_component_by_id(component_id: str) -> Optional[Dict[str, Any]]:
    """دریافت یک قطعه با ID"""
    component = await components_collection.find_one({"_id": component_id})
    if component:
        component["_id"] = str(component["_id"])
    return component


async def get_component_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """دریافت یک قطعه با Slug"""
    component = await components_collection.find_one({"slug": slug})
    if component:
        component["_id"] = str(component["_id"])
    return component


async def get_component_by_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """دریافت یک قطعه با Symbol"""
    component = await components_collection.find_one({"symbol": symbol})
    if component:
        component["_id"] = str(component["_id"])
    return component


async def update_component(component_id: str, data: Dict[str, Any]) -> bool:
    """به‌روزرسانی قطعه"""
    if "slug" in data:
        data["name"] = data["slug"]
    data["updated_at"] = datetime.now().isoformat()
    result = await components_collection.update_one({"_id": component_id}, {"$set": data})
    return result.modified_count > 0


async def delete_component(component_id: str) -> bool:
    """حذف قطعه"""
    result = await components_collection.delete_one({"_id": component_id})
    return result.deleted_count > 0


async def update_component_images(component_id: str, images: Dict[str, Any]) -> bool:
    """به‌روزرسانی تصاویر قطعه"""
    result = await components_collection.update_one(
        {"_id": component_id},
        {"$set": {"images": images, "updated_at": datetime.now().isoformat()}}
    )
    return result.modified_count > 0


# ============================================
# Device-Component Relationship
# ============================================

async def attach_component_to_device(device_id: str, component_id: str, specs: Dict[str, Any]) -> bool:
    """اتصال قطعه به دستگاه"""
    relation_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    relation = {
        "_id": relation_id,
        "device_id": device_id,
        "component_id": component_id,
        "width_mm": specs.get("width_mm"),
        "height_mm": specs.get("height_mm"),
        "weight_g": specs.get("weight_g"),
        "position_x": specs.get("position_x"),
        "position_y": specs.get("position_y"),
        "mobile_specs": specs.get("mobile_specs", {}),
        "tablet_specs": specs.get("tablet_specs", {}),
        "desktop_specs": specs.get("desktop_specs", {}),
        "created_at": now,
        "updated_at": now
    }
    try:
        await device_component_collection.insert_one(relation)
        return True
    except:
        return False


async def get_device_components(device_id: str, page: int = 1, per_page: int = 10) -> Dict[str, Any]:
    """دریافت قطعات متصل به یک دستگاه"""
    skip = (page - 1) * per_page
    
    device = await get_device_by_id(device_id)
    if not device:
        return {"error": "Device not found", "data": [], "pagination": {}}
    
    pipeline = [
        {"$match": {"device_id": device_id}},
        {"$lookup": {"from": "components", "localField": "component_id", "foreignField": "_id", "as": "component"}},
        {"$unwind": "$component"},
        {"$skip": skip},
        {"$limit": per_page}
    ]
    
    cursor = device_component_collection.aggregate(pipeline)
    items = await cursor.to_list(length=per_page)
    
    components = []
    for item in items:
        comp = item["component"]
        comp["_id"] = str(comp["_id"])
        comp["device_specific"] = {
            "width_mm": item.get("width_mm"),
            "height_mm": item.get("height_mm"),
            "weight_g": item.get("weight_g"),
            "position_x": item.get("position_x"),
            "position_y": item.get("position_y"),
            "mobile_specs": item.get("mobile_specs", {}),
            "tablet_specs": item.get("tablet_specs", {}),
            "desktop_specs": item.get("desktop_specs", {})
        }
        components.append(comp)
    
    total = await device_component_collection.count_documents({"device_id": device_id})
    
    return {
        "device": device,
        "data": components,
        "pagination": {
            "currentPage": page,
            "perPage": per_page,
            "totalRecords": total,
            "totalPages": (total + per_page - 1) // per_page
        }
    }


async def remove_component_from_device(device_id: str, component_id: str) -> bool:
    """حذف ارتباط قطعه با دستگاه"""
    result = await device_component_collection.delete_one({
        "device_id": device_id,
        "component_id": component_id
    })
    return result.deleted_count > 0


# ============================================
# Temp Upload CRUD
# ============================================

async def create_temp_upload(component_id: str, original_name: str, original_path: str, 
                               file_size_mb: float, file_type: str) -> str:
    """ایجاد رکورد آپلود موقت"""
    upload_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    doc = {
        "upload_id": upload_id,
        "component_id": component_id,
        "original_name": original_name,
        "original_path": original_path,
        "file_size_mb": file_size_mb,
        "file_type": file_type,
        "status": "pending",
        "created_at": now
    }
    await temp_uploads_collection.insert_one(doc)
    return upload_id


async def update_temp_upload_status(upload_id: str, status: str, error_message: str = None, processed_images: Dict = None):
    """به‌روزرسانی وضعیت آپلود موقت"""
    update_data = {"status": status}
    if error_message:
        update_data["error_message"] = error_message
    if processed_images:
        update_data["processed_images"] = processed_images
    if status == "completed":
        update_data["completed_at"] = datetime.now().isoformat()
    
    await temp_uploads_collection.update_one(
        {"upload_id": upload_id},
        {"$set": update_data}
    )


async def get_temp_upload_status(upload_id: str) -> Optional[Dict[str, Any]]:
    """دریافت وضعیت آپلود موقت"""
    doc = await temp_uploads_collection.find_one({"upload_id": upload_id})
    if doc:
        doc["_id"] = str(doc["_id"])
        if "processed_images" not in doc:
            doc["processed_images"] = {}
    return doc


# ============================================
# Video Session Management (برای آپلود چندقطعی ویدیو) - جدید
# ============================================

async def save_video_part(session_id: str, part_number: int, total_parts: int, file_path: str, component_slug: str):
    """ذخیره متادیتا قطعه ویدیو"""
    now = datetime.now().isoformat()
    
    existing = await video_sessions_collection.find_one({"session_id": session_id})
    
    if existing:
        received_parts = existing.get("received_parts", [])
        if part_number not in received_parts:
            received_parts.append(part_number)
        await video_sessions_collection.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "component_slug": component_slug,
                    "total_parts": total_parts,
                    "received_parts": received_parts,
                    "updated_at": now
                }
            }
        )
    else:
        await video_sessions_collection.insert_one({
            "session_id": session_id,
            "component_slug": component_slug,
            "total_parts": total_parts,
            "received_parts": [part_number],
            "status": "pending",
            "created_at": now,
            "updated_at": now
        })


async def update_video_session_status(session_id: str, status: str, hls_url: str = None, error: str = None):
    """به‌روزرسانی وضعیت جلسه ویدیو"""
    update_data = {
        "status": status,
        "updated_at": datetime.now().isoformat()
    }
    if hls_url:
        update_data["hls_url"] = hls_url
    if error:
        update_data["error_message"] = error
    
    await video_sessions_collection.update_one(
        {"session_id": session_id},
        {"$set": update_data}
    )


async def get_video_session_status(session_id: str):
    """دریافت وضعیت جلسه ویدیو"""
    return await video_sessions_collection.find_one({"session_id": session_id})


# ============================================
# Final Asset CRUD (اختیاری)
# ============================================

async def create_final_asset(component_id: str, device_id: str, original_upload_id: str,
                               file_name: str, file_path: str, file_size_mb: float,
                               mime_type: str, width: int = None, height: int = None,
                               device_type: str = None) -> str:
    """ذخیره فایل نهایی پردازش شده"""
    asset_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    asset = {
        "_id": asset_id,
        "component_id": component_id,
        "device_id": device_id,
        "original_upload_id": original_upload_id,
        "file_name": file_name,
        "file_path": file_path,
        "file_size_mb": file_size_mb,
        "mime_type": mime_type,
        "width": width,
        "height": height,
        "device_type": device_type,
        "created_at": now
    }
    await database["final_assets"].insert_one(asset)
    return asset_id