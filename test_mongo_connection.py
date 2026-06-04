import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def test():
    try:
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        db = client["device_component_db"]
        
        # تست اتصال
        await client.admin.command('ping')
        print("✅ اتصال به MongoDB موفق بود!")
        
        # ایجاد یک کالکشن تست
        collection = db["test_collection"]
        await collection.insert_one({"test": "data"})
        print("✅ سند تست درج شد!")
        
        # نمایش کالکشن‌ها
        collections = await db.list_collection_names()
        print(f"📁 کالکشن‌ها: {collections}")
        
        await client.close()
        
    except Exception as e:
        print(f"❌ خطا: {e}")

asyncio.run(test())