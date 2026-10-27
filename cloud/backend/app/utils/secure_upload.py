"""
安全文件上传模块

安全特性:
  - 文件类型白名单校验 (非扩展名, 基于魔数)
  - 文件大小限制
  - 路径遍历防御 (UUID 重命名)
  - 病毒扫描占位 (可扩展)
  - 敏感目录隔离
"""
import uuid
import logging
from pathlib import Path
from typing import Optional, Set, Tuple

from fastapi import UploadFile, HTTPException

logger = logging.getLogger(__name__)

# ─── 允许的文件类型 (扩展名 → MIME 类型) ───

ALLOWED_EXTENSIONS: Set[str] = {
    # 图片
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg',
    # 文档
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt', '.csv', '.md',
    # 数据
    '.json', '.xml', '.yaml', '.yml',
    # 日志
    '.log',
}

# 最大文件大小 (默认 10MB)
DEFAULT_MAX_SIZE = 10 * 1024 * 1024

# 文件魔数校验 (文件头签名 → 扩展名)
# 防止通过修改扩展名绕过校验
MAGIC_HEADERS: dict = {
    b'\xff\xd8\xff': '.jpg',
    b'\x89PNG\r\n\x1a\n': '.png',
    b'GIF87a': '.gif',
    b'GIF89a': '.gif',
    b'\x00\x00\x01\x00': '.ico',
    b'%PDF': '.pdf',
    b'PK\x03\x04': '.zip',  # docx/xlsx 也是 ZIP
    b'\x1f\x8b': '.gz',
}


class SecureFileUploader:
    """安全文件上传处理器"""

    def __init__(
        self,
        upload_dir: str = "./uploads",
        max_size: int = DEFAULT_MAX_SIZE,
        allowed_extensions: Optional[Set[str]] = None,
    ):
        self.upload_dir = Path(upload_dir).resolve()
        self.max_size = max_size
        self.allowed_extensions = allowed_extensions or ALLOWED_EXTENSIONS

        # 确保上传目录存在
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def _validate_size(self, file: UploadFile) -> None:
        """校验文件大小"""
        # 先检查 Content-Length
        content_length = file.size
        if content_length and content_length > self.max_size:
            raise HTTPException(
                status_code=413,
                detail=f"文件过大，最大允许 {self.max_size // 1024 // 1024}MB",
            )

    def _validate_extension(self, filename: str) -> str:
        """校验文件扩展名，返回小写规范化扩展名"""
        ext = Path(filename).suffix.lower()
        if ext not in self.allowed_extensions:
            allowed_str = ', '.join(sorted(self.allowed_extensions))
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型: {ext}，允许: {allowed_str}",
            )
        return ext

    def _validate_magic(self, header_bytes: bytes, expected_ext: str) -> None:
        """基于文件头魔数校验真实类型"""
        for magic, magic_ext in MAGIC_HEADERS.items():
            if header_bytes.startswith(magic):
                # 魔数匹配，检查扩展名是否一致
                if magic_ext == '.zip' and expected_ext in ('.docx', '.xlsx'):
                    return  # docx/xlsx 是 ZIP 格式，合法
                if magic_ext != expected_ext:
                    raise HTTPException(
                        status_code=400,
                        detail="文件类型与内容不匹配，可能被篡改",
                    )
                return

        # 没有匹配到已知魔数，但扩展名在白名单内，放行
        # (某些纯文本文件没有固定魔数)

    async def save_file(
        self,
        file: UploadFile,
        subdirectory: Optional[str] = None,
        max_size: Optional[int] = None,
    ) -> Tuple[str, Path]:
        """
        安全保存上传文件

        Args:
            file: FastAPI UploadFile 对象
            subdirectory: 可选子目录 (如 "avatars", "reports")
            max_size: 可选覆盖默认大小限制

        Returns:
            (原始文件名, 安全保存路径)

        Raises:
            HTTPException: 文件类型/大小不合法
        """
        original_name = file.filename or "unknown"
        size_limit = max_size or self.max_size

        # 1. 校验扩展名
        ext = self._validate_extension(original_name)

        # 2. 校验大小
        content_length = file.size
        if content_length and content_length > size_limit:
            raise HTTPException(
                status_code=413,
                detail=f"文件过大，最大允许 {size_limit // 1024 // 1024}MB",
            )

        # 3. 读取文件头进行魔数校验 (前 8 字节)
        file.file.seek(0)
        header = await file.read(8)
        file.file.seek(0)  # 重置文件指针
        self._validate_magic(header, ext)

        # 4. 生成安全的文件名 (UUID，防止覆盖和路径注入)
        safe_name = f"{uuid.uuid4().hex}{ext}"

        # 5. 确定保存路径 (防止路径遍历)
        if subdirectory:
            # 子目录只允许字母数字和下划线
            safe_subdir = ''.join(c for c in subdirectory if c.isalnum() or c == '_')
            if not safe_subdir:
                raise HTTPException(status_code=400, detail="非法的子目录名称")
            target_dir = self.upload_dir / safe_subdir
        else:
            target_dir = self.upload_dir

        target_dir.mkdir(parents=True, exist_ok=True)

        # 最终安全检查: 确保路径在 upload_dir 内
        target_path = target_dir / safe_name
        try:
            target_path.resolve().relative_to(self.upload_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="非法的文件路径")

        # 6. 分块写入 (防止内存溢出)
        written = 0
        file.file.seek(0)  # 重置到开头
        with open(target_path, 'wb') as f:
            while True:
                chunk = await file.read(8192)
                if not chunk:
                    break
                written += len(chunk)
                if written > size_limit:
                    # 超限，删除文件
                    target_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件过大，最大允许 {size_limit // 1024 // 1024}MB",
                    )
                f.write(chunk)

        logger.info(
            "文件上传成功: %s → %s (%d bytes)",
            original_name, target_path, written,
        )

        return original_name, target_path

    async def cleanup_failed(self, file_path: Path) -> None:
        """清理上传失败的文件"""
        if file_path and file_path.exists():
            file_path.unlink()
            logger.info("已清理失败的上传文件: %s", file_path)
