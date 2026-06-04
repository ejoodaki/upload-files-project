from PIL import Image, ImageDraw, ImageFont
import os

# ایجاد پوشه برای عکس‌های تست
os.makedirs("test_images", exist_ok=True)

# 1. عکس کوچک (50x50 پیکسل - خطا می‌دهد)
img = Image.new('RGB', (50, 50), color='red')
draw = ImageDraw.Draw(img)
draw.text((10, 20), "Small", fill='white')
img.save("test_images/small_image.jpg")
print("✅ عکس کوچک ساخته شد: test_images/small_image.jpg (50x50px)")

# 2. عکس با ابعاد normal (800x600)
img = Image.new('RGB', (800, 600), color='blue')
draw = ImageDraw.Draw(img)
draw.text((350, 280), "Normal Size", fill='white')
img.save("test_images/normal_image.jpg")
print("✅ عکس نرمال ساخته شد: test_images/normal_image.jpg (800x600px)")

# 3. عکس بزرگ (4000x3000 - نزدیک به حد مجاز)
img = Image.new('RGB', (4000, 3000), color='green')
draw = ImageDraw.Draw(img)
draw.text((1800, 1450), "Large Image", fill='white')
img.save("test_images/large_image.jpg")
print("✅ عکس بزرگ ساخته شد: test_images/large_image.jpg (4000x3000px)")

# 4. عکس با حجم بالا (کیفیت بالا)
img = Image.new('RGB', (3000, 2000), color='purple')
for i in range(100):
    draw.rectangle([i*30, i*20, (i+1)*30, (i+1)*20], fill='yellow')
img.save("test_images/high_quality.jpg", quality=95)
print("✅ عکس با کیفیت بالا ساخته شد: test_images/high_quality.jpg")

print("\n📂 همه عکس‌ها در پوشه 'test_images' ذخیره شدن")
print("برای تست آپلود از این عکس‌ها استفاده کن:")
print("  - small_image.jpg → خطای ابعاد کوچک")
print("  - normal_image.jpg → آپلود موفق")
print("  - large_image.jpg → احتمال خطای حجم")