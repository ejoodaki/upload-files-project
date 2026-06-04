import sqlite3
import json
import uuid
import re
from datetime import datetime
from typing import Optional, Dict, Any, List

DB_PATH = "uploads.db"

def get_db():
    """دریافت اتصال به دیتابیس"""
    conn = sqlite3.connect(DB_PATH, timeout=10)  # افزایش timeout به 10 ثانیه
    conn.row_factory = sqlite3.Row
    return conn


def generate_slug(name: str) -> str:
    """تبدیل نام به slug (مثال: Intel Core i9 -> intel-core-i9)"""
    slug = name.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


# ============================================
# Device CRUD
# ============================================

def create_device(data: Dict[str, Any]) -> str:
    """ایجاد دستگاه جدید"""
    conn = get_db()
    device_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    
    try:
        conn.execute('''
            INSERT INTO devices (id, name, brand, model, category, price, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (device_id, 
              data.get("name"), 
              data.get("brand"), 
              data.get("model"), 
              data.get("category"), 
              data.get("price", 0),
              now, now))
        conn.commit()
        return device_id
    finally:
        conn.close()


def get_device_by_id(device_id: str) -> Optional[Dict[str, Any]]:
    """دریافت یک دستگاه با ID"""
    conn = get_db()
    try:
        cursor = conn.execute('''
            SELECT id, name, brand, model, category, price, created_at, updated_at
            FROM devices WHERE id = ?
        ''', (device_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        return {
            "id": row[0],
            "name": row[1],
            "brand": row[2],
            "model": row[3],
            "category": row[4],
            "price": row[5],
            "createdAt": row[6],
            "updatedAt": row[7]
        }
    finally:
        conn.close()


def update_device(device_id: str, data: Dict[str, Any]) -> bool:
    """به‌روزرسانی دستگاه"""
    conn = get_db()
    now = datetime.now().isoformat()
    
    try:
        set_parts = []
        values = []
        
        for key in ["name", "brand", "model", "category", "price"]:
            if key in data and data[key] is not None:
                set_parts.append(f"{key} = ?")
                values.append(data[key])
        
        if not set_parts:
            return False
        
        values.append(now)
        values.append(device_id)
        
        query = f"UPDATE devices SET {', '.join(set_parts)}, updated_at = ? WHERE id = ?"
        conn.execute(query, values)
        conn.commit()
        
        return conn.total_changes > 0
    finally:
        conn.close()


def delete_device(device_id: str) -> bool:
    """حذف دستگاه و تمام ارتباطات"""
    conn = get_db()
    try:
        conn.execute("DELETE FROM device_component WHERE device_id = ?", (device_id,))
        conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def get_all_devices_paginated(page: int = 1, per_page: int = 10, filters: Dict = None) -> Dict[str, Any]:
    """دریافت لیست دستگاه‌ها با Pagination و فیلتر"""
    conn = get_db()
    try:
        offset = (page - 1) * per_page
        
        base_query = "SELECT * FROM devices WHERE 1=1"
        params = []
        
        if filters:
            if filters.get("name"):
                base_query += " AND name LIKE ?"
                params.append(f"%{filters['name']}%")
            if filters.get("brand"):
                base_query += " AND brand = ?"
                params.append(filters["brand"])
            if filters.get("category"):
                base_query += " AND category = ?"
                params.append(filters["category"])
            if filters.get("min_price"):
                base_query += " AND price >= ?"
                params.append(filters["min_price"])
            if filters.get("max_price"):
                base_query += " AND price <= ?"
                params.append(filters["max_price"])
        
        # دریافت کل تعداد
        count_query = base_query.replace("SELECT *", "SELECT COUNT(*)", 1)
        total_records = conn.execute(count_query, params).fetchone()[0]
        
        # دریافت داده‌ها
        query = base_query + " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([per_page, offset])
        
        cursor = conn.execute(query, params)
        
        devices = []
        for row in cursor:
            devices.append({
                "id": row[0],
                "name": row[1],
                "brand": row[2],
                "model": row[3],
                "category": row[4],
                "price": row[5],
                "createdAt": row[6],
                "updatedAt": row[7]
            })
        
        # محاسبات pagination
        total_pages = (total_records + per_page - 1) // per_page if total_records > 0 else 1
        
        return {
            "data": devices,
            "pagination": {
                "currentPage": page,
                "perPage": per_page,
                "totalRecords": total_records,
                "totalPages": total_pages,
                "hasPrevious": page > 1,
                "hasNext": page < total_pages,
                "previousPage": page - 1 if page > 1 else None,
                "nextPage": page + 1 if page < total_pages else None,
                "from": offset + 1 if total_records > 0 else 0,
                "to": min(offset + per_page, total_records)
            },
            "filters": filters or {}
        }
    finally:
        conn.close()


# ============================================
# Component CRUD
# ============================================

def create_component(data: Dict[str, Any]) -> str:
    """ایجاد قطعه جدید با slug خودکار"""
    conn = get_db()
    component_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    
    try:
        # ساخت slug
        slug = data.get("slug")
        if not slug:
            slug = generate_slug(data["name"])
        
        # پردازش specs
        specs = data.get("specs", {})
        if isinstance(specs, dict):
            specs = json.dumps(specs, ensure_ascii=False)
        
        # پردازش physical
        physical = data.get("physical", {})
        if isinstance(physical, dict):
            physical = json.dumps(physical, ensure_ascii=False)
        
        # پردازش images
        images = data.get("images", {})
        if isinstance(images, dict):
            images = json.dumps(images, ensure_ascii=False)
        
        conn.execute('''
            INSERT INTO components (id, name, slug, type, brand, specs, physical, images, price, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (component_id, 
              data.get("name"), 
              slug,
              data.get("type"), 
              data.get("brand"), 
              specs,
              physical,
              images,
              data.get("price", 0),
              now, now))
        conn.commit()
        return component_id
    finally:
        conn.close()


def get_component_by_id(component_id: str) -> Optional[Dict[str, Any]]:
    """دریافت یک قطعه با ID"""
    conn = get_db()
    try:
        cursor = conn.execute('''
            SELECT id, name, slug, type, brand, specs, physical, images, price, created_at, updated_at
            FROM components WHERE id = ?
        ''', (component_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        return {
            "id": row[0],
            "name": row[1],
            "slug": row[2],
            "type": row[3],
            "brand": row[4],
            "specs": json.loads(row[5]) if row[5] else {},
            "physical": json.loads(row[6]) if row[6] else {},
            "images": json.loads(row[7]) if row[7] else {},
            "price": row[8],
            "createdAt": row[9],
            "updatedAt": row[10]
        }
    finally:
        conn.close()


def get_component_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """دریافت یک قطعه با Slug"""
    conn = get_db()
    try:
        cursor = conn.execute('''
            SELECT id, name, slug, type, brand, specs, physical, images, price, created_at, updated_at
            FROM components WHERE slug = ?
        ''', (slug,))
        row = cursor.fetchone()
        if not row:
            return None
        
        return {
            "id": row[0],
            "name": row[1],
            "slug": row[2],
            "type": row[3],
            "brand": row[4],
            "specs": json.loads(row[5]) if row[5] else {},
            "physical": json.loads(row[6]) if row[6] else {},
            "images": json.loads(row[7]) if row[7] else {},
            "price": row[8],
            "createdAt": row[9],
            "updatedAt": row[10]
        }
    finally:
        conn.close()


def update_component(component_id: str, data: Dict[str, Any]) -> bool:
    """به‌روزرسانی قطعه"""
    conn = get_db()
    now = datetime.now().isoformat()
    
    try:
        set_parts = []
        values = []
        
        allowed_fields = ["name", "slug", "type", "brand", "specs", "physical", "images", "price"]
        
        for key in allowed_fields:
            if key in data and data[key] is not None:
                set_parts.append(f"{key} = ?")
                if key in ["specs", "physical", "images"] and isinstance(data[key], dict):
                    values.append(json.dumps(data[key], ensure_ascii=False))
                else:
                    values.append(data[key])
        
        if not set_parts:
            return False
        
        values.append(now)
        values.append(component_id)
        
        query = f"UPDATE components SET {', '.join(set_parts)}, updated_at = ? WHERE id = ?"
        conn.execute(query, values)
        conn.commit()
        
        return conn.total_changes > 0
    finally:
        conn.close()


def delete_component(component_id: str) -> bool:
    """حذف قطعه و تمام ارتباطات"""
    conn = get_db()
    try:
        conn.execute("DELETE FROM device_component WHERE component_id = ?", (component_id,))
        conn.execute("DELETE FROM components WHERE id = ?", (component_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def get_all_components_paginated(page: int = 1, per_page: int = 10, filters: Dict = None) -> Dict[str, Any]:
    """دریافت لیست قطعات با Pagination و فیلتر"""
    conn = get_db()
    try:
        offset = (page - 1) * per_page
        
        base_query = "SELECT * FROM components WHERE 1=1"
        params = []
        
        if filters:
            if filters.get("name"):
                base_query += " AND name LIKE ?"
                params.append(f"%{filters['name']}%")
            if filters.get("slug"):
                base_query += " AND slug LIKE ?"
                params.append(f"%{filters['slug']}%")
            if filters.get("type"):
                base_query += " AND type = ?"
                params.append(filters["type"])
            if filters.get("brand"):
                base_query += " AND brand = ?"
                params.append(filters["brand"])
            if filters.get("min_price"):
                base_query += " AND price >= ?"
                params.append(filters["min_price"])
            if filters.get("max_price"):
                base_query += " AND price <= ?"
                params.append(filters["max_price"])
        
        # دریافت کل تعداد
        count_query = base_query.replace("SELECT *", "SELECT COUNT(*)", 1)
        total_records = conn.execute(count_query, params).fetchone()[0]
        
        # دریافت داده‌ها
        query = base_query + " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([per_page, offset])
        
        cursor = conn.execute(query, params)
        
        components = []
        for row in cursor:
            components.append({
                "id": row[0],
                "name": row[1],
                "slug": row[2],
                "type": row[3],
                "brand": row[4],
                "specs": json.loads(row[5]) if row[5] else {},
                "physical": json.loads(row[6]) if row[6] else {},
                "images": json.loads(row[7]) if row[7] else {},
                "price": row[8],
                "createdAt": row[9],
                "updatedAt": row[10]
            })
        
        # محاسبات pagination
        total_pages = (total_records + per_page - 1) // per_page if total_records > 0 else 1
        
        return {
            "data": components,
            "pagination": {
                "currentPage": page,
                "perPage": per_page,
                "totalRecords": total_records,
                "totalPages": total_pages,
                "hasPrevious": page > 1,
                "hasNext": page < total_pages,
                "previousPage": page - 1 if page > 1 else None,
                "nextPage": page + 1 if page < total_pages else None,
                "from": offset + 1 if total_records > 0 else 0,
                "to": min(offset + per_page, total_records)
            },
            "filters": filters or {}
        }
    finally:
        conn.close()


def update_component_images(component_id: str, images: Dict[str, Any]) -> bool:
    """به‌روزرسانی تصاویر قطعه بعد از پردازش"""
    conn = get_db()
    now = datetime.now().isoformat()
    
    try:
        images_json = json.dumps(images, ensure_ascii=False)
        
        conn.execute('''
            UPDATE components 
            SET images = ?, updated_at = ?
            WHERE id = ?
        ''', (images_json, now, component_id))
        conn.commit()
        
        return conn.total_changes > 0
    finally:
        conn.close()


# ============================================
# Device-Component Relationship
# ============================================

def attach_component_to_device(device_id: str, component_id: str, specs: Dict[str, Any]) -> bool:
    """اتصال قطعه به دستگاه با مشخصات فیزیکی و سایزهای نمایش"""
    conn = get_db()
    now = datetime.now().isoformat()
    relation_id = str(uuid.uuid4())
    
    try:
        conn.execute('''
            INSERT INTO device_component 
            (id, device_id, component_id, width_mm, height_mm, weight_g, 
             position_x, position_y, mobile_specs, tablet_specs, desktop_specs, 
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (relation_id, device_id, component_id,
              specs.get("width_mm"), specs.get("height_mm"), specs.get("weight_g"),
              specs.get("position_x"), specs.get("position_y"),
              json.dumps(specs.get("mobile_specs", {})),
              json.dumps(specs.get("tablet_specs", {})),
              json.dumps(specs.get("desktop_specs", {})),
              now, now))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_device_components(device_id: str, page: int = 1, per_page: int = 10) -> Dict[str, Any]:
    """دریافت تمام قطعات متصل به یک دستگاه با مشخصات فیزیکی مخصوص آن دستگاه"""
    conn = get_db()
    try:
        offset = (page - 1) * per_page
        
        # دریافت اطلاعات دستگاه
        device = get_device_by_id(device_id)
        if not device:
            return {"error": "Device not found", "data": [], "pagination": {}}
        
        # دریافت قطعات
        query = '''
            SELECT c.id, c.name, c.slug, c.type, c.brand, c.specs, c.images, c.price,
                   dc.width_mm, dc.height_mm, dc.weight_g, dc.position_x, dc.position_y,
                   dc.mobile_specs, dc.tablet_specs, dc.desktop_specs
            FROM components c
            JOIN device_component dc ON c.id = dc.component_id
            WHERE dc.device_id = ?
            ORDER BY dc.created_at DESC
            LIMIT ? OFFSET ?
        '''
        
        cursor = conn.execute(query, (device_id, per_page, offset))
        
        components = []
        for row in cursor:
            components.append({
                "id": row[0],
                "name": row[1],
                "slug": row[2],
                "type": row[3],
                "brand": row[4],
                "specs": json.loads(row[5]) if row[5] else {},
                "images": json.loads(row[6]) if row[6] else {},
                "price": row[7],
                "deviceSpecific": {
                    "widthMm": row[8],
                    "heightMm": row[9],
                    "weightG": row[10],
                    "positionX": row[11],
                    "positionY": row[12],
                    "mobileSpecs": json.loads(row[13]) if row[13] else {},
                    "tabletSpecs": json.loads(row[14]) if row[14] else {},
                    "desktopSpecs": json.loads(row[15]) if row[15] else {}
                }
            })
        
        # کل تعداد
        total = conn.execute("SELECT COUNT(*) FROM device_component WHERE device_id = ?", (device_id,)).fetchone()[0]
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        
        return {
            "device": device,
            "data": components,
            "pagination": {
                "currentPage": page,
                "perPage": per_page,
                "totalRecords": total,
                "totalPages": total_pages,
                "hasPrevious": page > 1,
                "hasNext": page < total_pages,
                "previousPage": page - 1 if page > 1 else None,
                "nextPage": page + 1 if page < total_pages else None,
                "from": offset + 1 if total > 0 else 0,
                "to": min(offset + per_page, total)
            }
        }
    finally:
        conn.close()


def remove_component_from_device(device_id: str, component_id: str) -> bool:
    """حذف ارتباط قطعه با دستگاه"""
    conn = get_db()
    try:
        conn.execute("DELETE FROM device_component WHERE device_id = ? AND component_id = ?", (device_id, component_id))
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


# ============================================
# Async Upload (Temp/Final)
# ============================================

def create_temp_upload(component_id: str, original_name: str, original_path: str, 
                        file_size_mb: float, file_type: str) -> str:
    """ایجاد رکورد آپلود موقت"""
    conn = get_db()
    upload_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    
    try:
        conn.execute('''
            INSERT INTO temp_uploads (upload_id, component_id, original_name, original_path, 
                                       file_size_mb, file_type, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (upload_id, component_id, original_name, original_path, 
              file_size_mb, file_type, "pending", now))
        conn.commit()
        return upload_id
    finally:
        conn.close()


def update_temp_upload_status(upload_id: str, status: str, 
                               error_message: str = None, 
                               processed_images: Dict = None):
    """به‌روزرسانی وضعیت آپلود موقت"""
    conn = get_db()
    now = datetime.now().isoformat()
    
    try:
        if status == "completed":
            conn.execute('''
                UPDATE temp_uploads 
                SET status = ?, completed_at = ?, processed_images = ?
                WHERE upload_id = ?
            ''', (status, now, json.dumps(processed_images or {}), upload_id))
        elif error_message:
            conn.execute('''
                UPDATE temp_uploads 
                SET status = ?, error_message = ?, completed_at = ?
                WHERE upload_id = ?
            ''', (status, error_message, now, upload_id))
        else:
            conn.execute('''
                UPDATE temp_uploads SET status = ? WHERE upload_id = ?
            ''', (status, upload_id))
        conn.commit()
    finally:
        conn.close()


def get_temp_upload_status(upload_id: str) -> Optional[Dict[str, Any]]:
    """دریافت وضعیت آپلود موقت"""
    conn = get_db()
    try:
        cursor = conn.execute('SELECT * FROM temp_uploads WHERE upload_id = ?', (upload_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        return {
            "id": row[0],
            "uploadId": row[1],
            "componentId": row[2],
            "originalName": row[3],
            "originalPath": row[4],
            "fileSizeMb": row[5],
            "fileType": row[6],
            "status": row[7],
            "errorMessage": row[8],
            "processedImages": json.loads(row[9]) if row[9] else {},
            "createdAt": row[10],
            "completedAt": row[11]
        }
    finally:
        conn.close()


def create_final_asset(component_id: str, device_id: str, original_upload_id: str,
                        file_name: str, file_path: str, file_size_mb: float,
                        mime_type: str, width: int = None, height: int = None,
                        device_type: str = None) -> str:
    """ذخیره فایل نهایی پردازش شده"""
    conn = get_db()
    asset_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    
    try:
        conn.execute('''
            INSERT INTO final_assets 
            (id, component_id, device_id, original_upload_id, file_name, file_path, 
             file_size_mb, mime_type, width, height, device_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (asset_id, component_id, device_id, original_upload_id, file_name, file_path,
              file_size_mb, mime_type, width, height, device_type, now))
        conn.commit()
        return asset_id
    finally:
        conn.close()