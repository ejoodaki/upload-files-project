import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check_db():
    client = AsyncIOMotorClient("mongodb://admin:admin123@localhost:27017")
    db = client["device_component_db"]
    
    print("=" * 50)
    print("📊 محتویات دیتابیس MongoDB")
    print("=" * 50)
    
    # لیست کالکشن‌ها
    collections = await db.list_collection_names()
    print(f"\n📁 کالکشن‌ها: {collections}")
    
    for col_name in collections:
        collection = db[col_name]
        count = await collection.count_documents({})
        print(f"\n📂 {col_name}: {count} سند")
        
        # نمایش چند سند اول
        cursor = collection.find().limit(3)
        docs = await cursor.to_list(length=3)
        for doc in docs:
            # حذف _id برای خوانایی بهتر
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
            print(f"   - {doc}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(check_db())