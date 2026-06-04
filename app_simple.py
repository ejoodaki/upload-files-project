from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import shutil
from datetime import datetime
from bson import ObjectId
from database import devices_collection, uploads_collection

app = FastAPI(title="Simple Upload System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.get("/devices")
async def get_devices():
    devices = await devices_collection.find().to_list(length=100)
    for device in devices:
        device["_id"] = str(device["_id"])
    return {"devices": devices}

@app.post("/upload/{device_id}")
async def upload_file(device_id: str, file: UploadFile = File(...)):
    # پیدا کردن دستگاه
    try:
        item = await devices_collection.find_one({"_id": ObjectId(device_id)})
    except:
        item = await devices_collection.find_one({"_id": device_id})
    
    if not item:
        raise HTTPException(404, f"دستگاهی با شناسه {device_id} پیدا نشد")
    
    # ذخیره فایل
    os.makedirs(f"{UPLOAD_DIR}/{device_id}", exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    file_path = f"{UPLOAD_DIR}/{device_id}/{timestamp}_{file.filename}"
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    
    # ذخیره در دیتابیس
    upload_doc = {
        "file_name": file.filename,
        "file_path": file_path,
        "file_size_mb": round(file_size_mb, 2),
        "device_id": device_id,
        "device_name": item.get("name"),
        "uploaded_at": datetime.now()
    }
    
    result = await uploads_collection.insert_one(upload_doc)
    
    return {
        "success": True,
        "message": "فایل با موفقیت آپلود شد",
        "upload_id": str(result.inserted_id),
        "file_name": file.filename,
        "size_mb": round(file_size_mb, 2)
    }

@app.get("/uploads/{device_id}")
async def get_uploads(device_id: str):
    uploads = await uploads_collection.find({"device_id": device_id}).to_list(length=100)
    for upload in uploads:
        upload["_id"] = str(upload["_id"])
    return {"uploads": uploads}

@app.get("/")
async def root():
    return {"message": "Server is running!", "device_id": "69ec58f638c50cb782cd531a"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app_simple:app", host="127.0.0.1", port=8000, reload=True)