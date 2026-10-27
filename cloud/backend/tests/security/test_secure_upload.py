"""
安全文件上传模块单元测试
"""
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.utils.secure_upload import SecureFileUploader, ALLOWED_EXTENSIONS


def create_mock_upload_file(filename, content, content_type=None):
    """创建模拟的 UploadFile 对象"""
    mock_file = MagicMock()
    mock_file.size = len(content)
    mock_file.filename = filename
    mock_file.content_type = content_type

    # 模拟 read 行为
    read_count = [0]
    content_bytes = content if isinstance(content, bytes) else content.encode()

    async def mock_read(n=8192):
        if read_count[0] == 0:
            read_count[0] += 1
            return content_bytes[:n]
        read_count[0] += 1
        return b""

    async def mock_read_small(n=8):
        read_count[0] = 0
        return content_bytes[:n]

    # 第一次 read(8) 读魔数，第二次 read(8192) 读内容
    calls = [0]
    async def mock_read_seq(n=8192):
        calls[0] += 1
        if calls[0] == 1:
            return content_bytes[:n]
        elif calls[0] == 2:
            return content_bytes[n:] if len(content_bytes) > n else b""
        return b""

    mock_file.read = mock_read_seq
    mock_file.seek = MagicMock()
    return mock_file


class TestValidateExtension:
    """文件扩展名校验测试"""

    def test_allowed_extension(self):
        uploader = SecureFileUploader()
        ext = uploader._validate_extension("report.pdf")
        assert ext == ".pdf"

    def test_case_insensitive(self):
        uploader = SecureFileUploader()
        ext = uploader._validate_extension("image.PNG")
        assert ext == ".png"

    def test_blocked_extension(self):
        uploader = SecureFileUploader()
        with pytest.raises(Exception):  # HTTPException
            uploader._validate_extension("evil.exe")

    def test_blocked_script(self):
        uploader = SecureFileUploader()
        with pytest.raises(Exception):
            uploader._validate_extension("hack.php")

    def test_blocked_shell(self):
        uploader = SecureFileUploader()
        with pytest.raises(Exception):
            uploader._validate_extension("script.sh")


class TestMagicHeaderValidation:
    """魔数校验测试"""

    def test_valid_jpg(self):
        uploader = SecureFileUploader()
        # \xff\xd8\xff 是 JPG 魔数
        uploader._validate_magic(b'\xff\xd8\xff\xe0', '.jpg')  # 应该通过

    def test_valid_png(self):
        uploader = SecureFileUploader()
        uploader._validate_magic(b'\x89PNG\r\n\x1a\n', '.png')  # 应该通过

    def test_valid_pdf(self):
        uploader = SecureFileUploader()
        uploader._validate_magic(b'%PDF-1.4', '.pdf')  # 应该通过

    def test_mismatch_blocked(self):
        uploader = SecureFileUploader()
        # PDF 魔数但声明为 .txt，应该拒绝
        with pytest.raises(Exception):
            uploader._validate_magic(b'%PDF-1.4', '.txt')

    def test_unknown_magic_passes(self):
        uploader = SecureFileUploader()
        # 未知魔数但扩展名合法，应该放行 (纯文本没有固定魔数)
        uploader._validate_magic(b'hello world', '.txt')  # 应该通过

    def test_docx_is_zip(self):
        uploader = SecureFileUploader()
        # docx 本质是 ZIP，应该通过
        uploader._validate_magic(b'PK\x03\x04', '.docx')


class TestSaveFile:
    """文件保存测试"""

    @pytest.mark.asyncio
    async def test_save_with_traversal_blocked(self):
        """路径遍历应该被阻止"""
        with tempfile.TemporaryDirectory() as tmpdir:
            uploader = SecureFileUploader(upload_dir=tmpdir)

            mock_file = MagicMock()
            mock_file.filename = "../../../etc/passwd"
            mock_file.size = 100

            with pytest.raises(Exception):
                await uploader.save_file(mock_file)

    @pytest.mark.asyncio
    async def test_subdirectory_sanitization(self):
        """子目录名应该被净化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            uploader = SecureFileUploader(upload_dir=tmpdir)

            content = b"hello"
            mock_file = MagicMock()
            mock_file.filename = "test.txt"
            mock_file.size = len(content)

            # Proper mock: tracks position, handles seek(0)
            pos = [0]
            async def mock_read(n=8192):
                chunk = content[pos[0]:pos[0]+n]
                pos[0] += len(chunk)
                return chunk

            def mock_seek(p):
                pos[0] = p

            mock_file.read = mock_read
            mock_file.seek = mock_seek

            # 恶意子目录名应该被净化
            original_name, saved_path = await uploader.save_file(
                mock_file, subdirectory="evil/../hack"
            )
            # 路径遍历被移除
            assert ".." not in str(saved_path)


class TestSecureUploaderInit:
    """初始化测试"""

    def test_default_settings(self):
        uploader = SecureFileUploader()
        assert uploader.max_size == 10 * 1024 * 1024
        assert '.jpg' in uploader.allowed_extensions
        assert '.pdf' in uploader.allowed_extensions

    def test_custom_max_size(self):
        uploader = SecureFileUploader(max_size=5 * 1024 * 1024)
        assert uploader.max_size == 5 * 1024 * 1024

    def test_custom_extensions(self):
        uploader = SecureFileUploader(allowed_extensions={'.txt'})
        assert uploader.allowed_extensions == {'.txt'}

    def test_creates_upload_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            upload_dir = os.path.join(tmpdir, "new_uploads")
            uploader = SecureFileUploader(upload_dir=upload_dir)
            assert os.path.exists(upload_dir)
