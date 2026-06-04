import asyncio
from database import devices_collection, components_collection
from bson import ObjectId

async def seed_database():
    # پاک کردن دیتای قبلی
    await devices_collection.delete_many({})
    await components_collection.delete_many({})
    
    # ساخت دستگاه نمونه
    macbook = {
        "name": "MacBook Pro M3",
        "brand": "Apple",
        "category": "laptop",
        "upload_rules": {
            "allowed_formats": ["jpg", "png", "mp4", "pdf"],
            "max_size_mb": 15
        }
    }
    
    result = await devices_collection.insert_one(macbook)
    device_id = result.inserted_id
    print(f"✅ دستگاه اضافه شد با ID: {device_id}")
    
    # ساخت قطعه نمونه
    component = {
        "name": "M3 Pro Chip",
        "type": "processor",
        "parent_device_id": str(device_id),
        "specs": {"cores": 12, "nm": 3},
        "upload_rules": {
            "allowed_formats": ["jpg", "png", "pdf"],
            "max_size_mb": 5
        }
    }
    
    await components_collection.insert_one(component)
    print("✅ قطعه اضافه شد")
    
    print("\n📌 برای آپلود فایل از این Device ID استفاده کن:")
    print(f"Device ID: {device_id}")

if __name__ == "__main__":
    asyncio.run(seed_database())