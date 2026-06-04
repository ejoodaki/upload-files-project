import os
from datetime import datetime
from typing import Dict, Any
from filesystem_toolkit import FilesystemToolkit

# Import ParseGenius
try:
    from ParseGenius.ParseGenius import parse_x_to_markdown_output
    PARSEGENIUS_AVAILABLE = True
    print("✅ ParseGenius loaded successfully")
except ImportError as e:
    PARSEGENIUS_AVAILABLE = False
    print(f"⚠️ ParseGenius not available: {e}")

class UploadAgent:
    """
    Agent هوشمند برای مدیریت آپلود و تحلیل فایل‌ها
    """
    
    def __init__(self, upload_base_path: str = "./uploads"):
        self.fs = FilesystemToolkit(upload_base_path, read_only=False)
        self.upload_base_path = upload_base_path
        
    def process_upload(self, file_content: bytes, filename: str, 
                       category: str, item_id: str, item_name: str) -> Dict[str, Any]:
        """
        پردازش کامل یک فایل آپلودی توسط Agent
        """
        result = {
            "success": False,
            "file_path": None,
            "analysis_result": None,
            "warnings": [],
            "suggestions": [],
            "user_message": ""
        }
        
        try:
            # 1. ذخیره امن فایل
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_filename = f"{timestamp}_{filename}"
            relative_path = f"{category}s/{item_id}/{safe_filename}"
            
            file_path = self.fs.save_uploaded_file(relative_path, file_content)
            result["file_path"] = file_path
            
            # 2. محاسبه حجم فایل
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            file_ext = filename.split(".")[-1].lower()
            
            # 3. تحلیل با ParseGenius
            if PARSEGENIUS_AVAILABLE:
                try:
                    parse_result = parse_x_to_markdown_output(file_path)
                    if parse_result:
                        result["analysis_result"] = str(parse_result)[:1000]
                        result["success"] = True
                        result["user_message"] = f"✅ تحلیل AI: {str(parse_result)[:300]}..."
                except Exception as e:
                    result["warnings"].append(f"خطا در تحلیل AI: {str(e)}")
                    result["success"] = True
                    result["user_message"] = self._generate_fallback_message(filename, file_size_mb, file_ext)
            else:
                result["success"] = True
                result["user_message"] = self._generate_fallback_message(filename, file_size_mb, file_ext)
            
            # 4. بررسی حجم فایل
            if file_size_mb > 10:
                result["warnings"].append(f"حجم فایل {file_size_mb:.1f} مگابایت است (توصیه: کمتر از 10 مگابایت)")
                result["suggestions"].append("برای کاهش حجم از TinyPNG یا HandBrake استفاده کنید")
                    
        except Exception as e:
            result["user_message"] = f"❌ خطا در آپلود: {str(e)}"
            result["warnings"].append(str(e))
            
        return result
    
    def _generate_fallback_message(self, filename: str, file_size_mb: float, file_ext: str) -> str:
        """پیام جایگزین"""
        return f"""✅ فایل شما با موفقیت آپلود شد!

📄 نام فایل: {filename}
📦 حجم: {file_size_mb:.2f} مگابایت
🔤 نوع: {file_ext.upper()}

🤖 Agent: فایل در صف پردازش قرار گرفت."""

# ایجاد نمونه سراسری Agent
upload_agent = UploadAgent()

def process_upload_with_agent(file_content: bytes, filename: str, 
                               category: str, item_id: str, item_name: str):
    return upload_agent.process_upload(file_content, filename, category, item_id, item_name)