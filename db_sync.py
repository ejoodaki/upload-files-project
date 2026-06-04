from pymongo import MongoClient
from datetime import datetime
import os

# اتصال همگام (sync) به MongoDB
MONGO_URL = os.getenv("MONGO_URL", "mongodb://admin:admin123@mongodb:27017")
client = MongoClient(MONGO_URL)
db = client.device_component_upload

# Collections
components_collection = db.components
devices_collection = db.devices
temp_uploads_collection = db.temp_uploads
video_sessions_collection = db.video_sessions

def get_component_by_id_sync(component_id: str):
    return components_collection.find_one({"_id": component_id})

def update_component_images_sync(component_id: str, images: dict):
    return components_collection.update_one(
        {"_id": component_id},
        {"$set": {"images": images}}
    )

def update_video_session_status_sync(session_id: str, status: str, hls_url: str = None, error: str = None):
    update_data = {"status": status}
    if hls_url:
        update_data["hls_url"] = hls_url
    if error:
        update_data["error_message"] = error
    if status == "completed":
        update_data["completed_at"] = datetime.now().isoformat()
    return video_sessions_collection.update_one(
        {"session_id": session_id},
        {"$set": update_data},
        upsert=True
    )

def update_temp_upload_status_sync(upload_id: str, status: str, processed_images: dict = None, error_message: str = None):
    update_data = {"status": status}
    if processed_images:
        update_data["processed_images"] = processed_images
    if error_message:
        update_data["error_message"] = error_message
    if status == "completed":
        update_data["completed_at"] = datetime.now().isoformat()
    return temp_uploads_collection.update_one(
        {"upload_id": upload_id},
        {"$set": update_data}
    )

def get_temp_upload_status_sync(upload_id: str):
    return temp_uploads_collection.find_one({"upload_id": upload_id})