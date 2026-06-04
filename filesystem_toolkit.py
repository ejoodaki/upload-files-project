import os
import shutil
import glob
from pathlib import Path

class FilesystemToolkit:
    """
    یک ابزار امن برای مدیریت فایل‌ها در پوشه مشخص
    """
    
    def __init__(self, base_path: str, read_only: bool = False):
        self.base_path = Path(base_path).resolve()
        self.read_only = read_only
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def _resolve_path(self, relative_path: str) -> Path:
        """تبدیل مسیر نسبی به مطلق و بررسی امنیت"""
        target = (self.base_path / relative_path).resolve()
        if not str(target).startswith(str(self.base_path)):
            raise PermissionError(f"دسترسی به خارج از پوشه مجاز نیست: {relative_path}")
        return target
    
    def read_file(self, file_path: str) -> str:
        """خواندن محتویات یک فایل"""
        path = self._resolve_path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"فایل پیدا نشد: {file_path}")
        return path.read_text(encoding='utf-8')
    
    def write_file(self, file_path: str, content: str):
        """ایجاد یا بازنویسی فایل"""
        if self.read_only:
            raise PermissionError("در حالت Read-Only نمی‌توان نوشت")
        path = self._resolve_path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    
    def save_uploaded_file(self, relative_path: str, file_content: bytes) -> str:
        """ذخیره فایل آپلودی کاربر"""
        if self.read_only:
            raise PermissionError("در حالت Read-Only نمی‌توان نوشت")
        path = self._resolve_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(file_content)
        return str(path)
    
    def delete_file(self, file_path: str):
        """حذف فایل"""
        if self.read_only:
            raise PermissionError("در حالت Read-Only نمی‌توان حذف کرد")
        path = self._resolve_path(file_path)
        if path.exists():
            path.unlink()
    
    def find_files(self, pattern: str) -> list:
        """جستجوی فایل‌ها با الگوی glob"""
        search_path = self.base_path / pattern
        matches = glob.glob(str(search_path), recursive=True)
        return [str(Path(m).relative_to(self.base_path)) for m in matches]
    
    def list_directory(self, dir_path: str = "") -> list:
        """لیست محتویات یک پوشه"""
        path = self._resolve_path(dir_path)
        if not path.exists():
            return []
        return [str(p.relative_to(self.base_path)) for p in path.iterdir()]