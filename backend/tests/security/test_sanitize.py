"""
输入验证与净化模块单元测试
"""
import pytest
from pathlib import Path
import tempfile
import os

from app.utils.sanitize import (
    sanitize_html,
    validate_no_xss,
    strip_html,
    sanitize_path,
    validate_command_arg,
    mask_email,
    mask_phone,
    mask_token,
    mask_sensitive_dict,
    sanitize_for_log,
    sanitize_string,
)


class TestSanitizeHtml:
    """HTML转义测试"""

    def test_basic_escape(self):
        assert sanitize_html("<script>") == "&lt;script&gt;"

    def test_escape_quotes(self):
        assert sanitize_html('"hello"') == "&quot;hello&quot;"

    def test_escape_ampersand(self):
        assert sanitize_html("a&b") == "a&amp;b"

    def test_none_string(self):
        assert sanitize_html(123) == 123

    def test_safe_text_unchanged(self):
        assert sanitize_html("Hello World") == "Hello World"


class TestValidateNoXSS:
    """XSS检测测试"""

    def test_clean_text(self):
        assert validate_no_xss("Hello World") is True

    def test_script_tag(self):
        assert validate_no_xss("<script>alert(1)</script>") is False

    def test_onclick_handler(self):
        assert validate_no_xss('<img onclick="evil()">') is False

    def test_javascript_uri(self):
        assert validate_no_xss('<a href="javascript:alert(1)">') is False

    def test_iframe(self):
        assert validate_no_xss('<iframe src="evil.com">') is False

    def test_svg_onload(self):
        assert validate_no_xss('<svg onload="alert(1)">') is False


class TestStripHtml:
    """HTML标签移除测试"""

    def test_remove_tags(self):
        assert strip_html("<b>bold</b> text") == "bold text"

    def test_nested_tags(self):
        assert strip_html("<div><p>hello</p></div>") == "hello"

    def test_no_tags(self):
        assert strip_html("plain text") == "plain text"

    def test_not_string(self):
        assert strip_html(123) == 123


class TestSanitizePath:
    """路径安全测试"""

    def test_safe_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = sanitize_path("file.txt", base_dir=Path(tmpdir))
            assert str(result).endswith("file.txt")

    def test_path_traversal_blocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="路径遍历"):
                sanitize_path("../../etc/passwd", base_dir=Path(tmpdir))

    def test_path_traversal_subtle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError):
                sanitize_path("foo/../../../etc/passwd", base_dir=Path(tmpdir))


class TestValidateCommandArg:
    """命令注入防御测试"""

    def test_safe_arg(self):
        assert validate_command_arg("hello") is True

    def test_semicolon(self):
        assert validate_command_arg("hello;rm -rf /") is False

    def test_pipe(self):
        assert validate_command_arg("cat /etc/passwd | grep root") is False

    def test_backtick(self):
        assert validate_command_arg("$(whoami)") is False

    def test_not_string(self):
        assert validate_command_arg(123) is False


class TestMaskEmail:
    """邮箱脱敏测试"""

    def test_basic_mask(self):
        assert mask_email("zhangsan@example.com") == "z***n@example.com"

    def test_short_email(self):
        result = mask_email("ab@example.com")
        assert result.startswith("a*")

    def test_invalid_email(self):
        assert mask_email("not-an-email") == "not-an-email"


class TestMaskPhone:
    """手机号脱敏测试"""

    def test_chinese_phone(self):
        assert mask_phone("13812345678") == "138****5678"

    def test_short_phone(self):
        assert mask_phone("12345") == "12345"


class TestMaskToken:
    """Token脱敏测试"""

    def test_mask_token(self):
        assert mask_token("abcdef123456") == "abcd********"

    def test_short_token(self):
        assert mask_token("ab") == "****"


class TestMaskSensitiveDict:
    """字典脱敏测试"""

    def test_mask_password(self):
        result = mask_sensitive_dict({"username": "admin", "password": "secret"})
        assert result["username"] == "admin"
        assert "*" in result["password"]  # 部分掩码

    def test_mask_nested(self):
        result = mask_sensitive_dict({"user": {"password": "secret"}})
        assert "*" in result["user"]["password"]  # 部分掩码

    def test_mask_phone_field(self):
        result = mask_sensitive_dict({"phone": "13812345678"})
        assert result["phone"] == "138****5678"

    def test_mask_email_field(self):
        result = mask_sensitive_dict({"email": "user@example.com"})
        assert "***" in result["email"]


class TestSanitizeForLog:
    """日志脱敏测试"""

    def test_mask_password_in_log(self):
        result = sanitize_for_log("password=secret123")
        assert "secret123" not in result
        assert "***" in result

    def test_mask_token_in_log(self):
        result = sanitize_for_log("token=abc123def456")
        assert "abc123def456" not in result

    def test_mask_phone_in_log(self):
        result = sanitize_for_log("user phone: 13812345678")
        assert "13812345678" not in result
        assert "138****5678" in result

    def test_normal_message_unchanged(self):
        msg = "Hello world"
        assert sanitize_for_log(msg) == msg


class TestSanitizeString:
    """字符串净化测试"""

    def test_strip_whitespace(self):
        assert sanitize_string("  hello  ") == "hello"

    def test_truncate_long_string(self):
        long_str = "a" * 20000
        result = sanitize_string(long_str, max_length=100)
        assert len(result) == 100

    def test_remove_control_chars(self):
        # \x01 is a control character
        result = sanitize_string("hello\x01world")
        assert "\x01" not in result

    def test_keep_newlines_tabs(self):
        result = sanitize_string("hello\nworld\ttab")
        assert "\n" in result
        assert "\t" in result

    def test_not_string(self):
        assert sanitize_string(123) == 123
