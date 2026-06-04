import cv2
from PIL import Image
import numpy as np
import os

def smart_analyze_image(image_path, rules):
    """
    تحلیل هوشمند تصویر با ارائه پیشنهادات اصلاحی
    """
    suggestions = []
    errors = []
    warnings = []
    
    try:
        # باز کردن تصویر
        img = cv2.imread(image_path)
        if img is None:
            return {
                "success": False,
                "errors": ["فایل تصویر معتبر نیست یا خراب است"],
                "suggestions": ["یک فایل تصویر معتبر (غیرخراب) انتخاب کنید"],
                "user_message": "❌ فایل تصویر شما قابل خواندن نیست. لطفاً یک تصویر سالم و معتبر آپلود کنید."
            }
        
        height, width = img.shape[:2]
        file_size_mb = os.path.getsize(image_path) / (1024 * 1024)
        
        # === 1. بررسی ابعاد ===
        if "min_width" in rules and width < rules["min_width"]:
            errors.append(f"عرض تصویر ({width}px) کمتر از حد مجاز ({rules['min_width']}px) است")
            suggestions.append(f"✅ عرض تصویر را به حداقل {rules['min_width']}px برسانید")
        
        if "max_width" in rules and width > rules["max_width"]:
            warnings.append(f"عرض تصویر ({width}px) بیشتر از حد توصیه شده ({rules['max_width']}px) است")
            suggestions.append(f"💡 برای آپلود سریع‌تر، عرض تصویر را به {rules['max_width']}px کاهش دهید")
        
        if "min_height" in rules and height < rules["min_height"]:
            errors.append(f"ارتفاع تصویر ({height}px) کمتر از حد مجاز ({rules['min_height']}px) است")
            suggestions.append(f"✅ ارتفاع تصویر را به حداقل {rules['min_height']}px برسانید")
        
        # === 2. بررسی نسبت تصویر ===
        aspect_ratio = width / height
        if aspect_ratio < 0.5 or aspect_ratio > 2.0:
            warnings.append(f"نسبت تصویر {aspect_ratio:.2f} غیرعادی است (تصویر خیلی باریک یا کشیده است)")
            suggestions.append("💡 نسبت ایده‌ال برای تصویر 4:3 یا 16:9 است. تصویر خود را برش بزنید")
        
        # === 3. بررسی کیفیت و وضوح ===
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        if laplacian_var < 100:
            warnings.append("تصویر شما تار یا کم‌کیفیت است")
            suggestions.append("📷 از یک تصویر با فوکوس بهتر استفاده کنید")
        
        # === 4. بررسی روشنایی ===
        brightness = np.mean(gray)
        if brightness < 80:
            warnings.append("تصویر شما خیلی تاریک است")
            suggestions.append("💡 تصویر را در محیط روشن‌تر بگیرید")
        elif brightness > 200:
            warnings.append("تصویر شما خیلی روشن است")
            suggestions.append("💡 تصویر را در محیط با نور کمتر بگیرید")
        
        # === 5. بررسی حجم فایل ===
        max_size = rules.get("max_size_mb", 5)
        if file_size_mb > max_size:
            errors.append(f"حجم فایل {file_size_mb:.1f} مگابایت از حد مجاز {max_size} مگابایت بیشتر است")
            suggestions.append(f"🔄 حجم تصویر را کاهش دهید:\n   - استفاده از سایت TinyPNG\n   - کاهش ابعاد تصویر\n   - تبدیل به فرمت JPEG")
        
        # === 6. نتیجه نهایی ===
        if errors:
            return {
                "success": False,
                "errors": errors,
                "warnings": warnings,
                "suggestions": suggestions,
                "user_message": f"❌ {errors[0]}\n\n💡 راه حل: {suggestions[0] if suggestions else 'لطفاً قوانین را رعایت کنید'}"
            }
        else:
            quality_score = min(100, max(0, 100 - len(warnings) * 10))
            return {
                "success": True,
                "warnings": warnings,
                "suggestions": suggestions,
                "quality_score": quality_score,
                "user_message": f"✅ تصویر تایید شد!\n📊 کیفیت: {quality_score}%\n" + (f"⚠️ {warnings[0]}" if warnings else "")
            }
            
    except Exception as e:
        return {
            "success": False,
            "errors": [f"خطا در تحلیل تصویر: {str(e)}"],
            "suggestions": ["دوباره تلاش کنید"],
            "user_message": "❌ خطا در پردازش تصویر. لطفاً دوباره تلاش کنید."
        }


def smart_analyze_video(video_path, rules):
    """
    تحلیل هوشمند ویدیو
    """
    suggestions = []
    errors = []
    warnings = []
    
    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
        
        # بررسی مدت زمان
        max_duration = rules.get("max_duration_seconds", 300)
        if duration > max_duration:
            errors.append(f"مدت ویدیو {duration:.1f} ثانیه از حد مجاز {max_duration} ثانیه بیشتر است")
            suggestions.append(f"✂️ ویدیو را کوتاه کنید (حداکثر {max_duration // 60} دقیقه)")
        
        # بررسی کیفیت
        if width < 640 or height < 480:
            warnings.append("کیفیت ویدیو پایین است")
            suggestions.append("📹 ویدیو را با کیفیت بالاتر (حداقل 720p) ضبط کنید")
        
        # بررسی حجم
        max_size = rules.get("max_size_mb", 100)
        if file_size_mb > max_size:
            errors.append(f"حجم ویدیو {file_size_mb:.1f} مگابایت از حد مجاز {max_size} مگابایت بیشتر است")
            suggestions.append(f"🔄 حجم ویدیو را با HandBrake کاهش دهید")
        
        cap.release()
        
        if errors:
            return {
                "success": False,
                "errors": errors,
                "warnings": warnings,
                "suggestions": suggestions,
                "user_message": f"❌ {errors[0]}\n\n💡 راه حل: {suggestions[0] if suggestions else 'لطفاً قوانین را رعایت کنید'}"
            }
        else:
            return {
                "success": True,
                "warnings": warnings,
                "suggestions": suggestions,
                "user_message": f"✅ ویدیو تایید شد!\n📹 مدت: {duration:.1f} ثانیه\nکیفیت: {width}x{height}"
            }
            
    except Exception as e:
        return {
            "success": False,
            "errors": [f"خطا: {str(e)}"],
            "suggestions": ["دوباره تلاش کنید"],
            "user_message": "❌ خطا در پردازش ویدیو"
        }