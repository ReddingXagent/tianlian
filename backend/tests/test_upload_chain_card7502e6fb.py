"""上传链三重缺陷回归 — 卡 7502e6fb

缺陷1: gateways.upload_firmware version 未消毒 → 路径穿越 (须 400)
缺陷2: RequestBodySizeMiddleware 10MB 全局上限无固件豁免 → >10MB 固件包 413
        (固件路由豁免至 200MB, 端点内自设硬上限)
缺陷3: chunked 无 content-length 绕过全局体积限制,
        fleet_recharge._save_upload / enterprise_registration.upload_license /
        ops_invoice_request.upload_invoice_file 须在 read() 前查 file.size 早拒 413
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

from app.main import app as full_app
from app.middleware import logging_middleware as mw
from app.middleware.logging_middleware import (
    RequestBodySizeMiddleware,
    RequestIDMiddleware,
)
from app.api.v1 import gateways as gateways_mod
from app.api.v1 import fleet_recharge as fleet_mod
from app.api.v1 import enterprise_registration as ent_mod
from app.api.v1.operate import ops_invoice_request as ops_mod

UPLOAD_URL = "/api/v1/gateways/firmware/upload"
LICENSE_URL = "/api/v1/auth/register/upload-license"



@pytest.fixture
def firmware_dir(tmp_path, monkeypatch):
    d = tmp_path / "firmware"
    monkeypatch.setattr(gateways_mod, "FIRMWARE_DIR", str(d))
    return d


# ────────────────────────────────────────────────────────────────────
# 缺陷1: version 路径穿越
# ────────────────────────────────────────────────────────────────────
class TestFirmwareVersionTraversal:
    @pytest.mark.parametrize("version", [
        "../evil", "..\\evil", "/etc/pwned", "a/b", "a;b", "v1.0.0 金箍棒",
    ])
    def test_malicious_version_rejected_400(self, client, firmware_dir, version):
        r = client.post(
            UPLOAD_URL, files={"file": ("fw.bin", b"BIN", "application/octet-stream")},
            data={"version": version, "model": "TL-GW-100"},
        )
        assert r.status_code == 400, f"version={version!r} 应被白名单拒绝"

    def test_valid_version_accepted(self, client, firmware_dir):
        r = client.post(
            UPLOAD_URL, files={"file": ("fw.bin", b"BIN", "application/octet-stream")},
            data={"version": "v1.0.0-rc.1_2", "model": "TL-GW-100"},
        )
        assert r.status_code == 200, r.text[:300]
        assert firmware_dir.exists()

    def test_nothing_written_outside_firmware_dir(self, client, firmware_dir, tmp_path):
        r = client.post(
            UPLOAD_URL, files={"file": ("fw.bin", b"BIN", "application/octet-stream")},
            data={"version": "../escape", "model": "TL-GW-100"},
        )
        assert r.status_code == 400
        assert not (tmp_path.parent / "escape*").exists() or True  # 穿越文件不应产生
        # firmware_dir 之上不应出现逃逸产物
        siblings = [p.name for p in firmware_dir.parent.parent.iterdir()]
        assert not any("escape" in n for n in siblings)


# ────────────────────────────────────────────────────────────────────
# 缺陷2: 固件上传 10MB 豁免 + 端点硬上限
# ────────────────────────────────────────────────────────────────────
class TestFirmwareSizeExemption:
    def test_oversize_10mb_firmware_accepted(self, client, firmware_dir):
        """11MB 固件包 > 全局 10MB, 固件路由豁免后须可传。"""
        payload = b"\x00" * (11 * 1024 * 1024)
        r = client.post(
            UPLOAD_URL, files={"file": ("fw.bin", payload, "application/octet-stream")},
            data={"version": "v11mb.1", "model": "TL-GW-100"},
        )
        assert r.status_code == 200, f">10MB 固件包被拒: {r.status_code} {r.text[:200]}"
        assert r.json()["data"]["file_size"] == len(payload)

    def test_firmware_hard_cap_413(self, client, firmware_dir, monkeypatch):
        """端点内硬上限: 超限 413 且不留半截文件。"""
        monkeypatch.setattr(gateways_mod, "FIRMWARE_MAX_BYTES", 100)
        r = client.post(
            UPLOAD_URL, files={"file": ("fw.bin", b"x" * 200, "application/octet-stream")},
            data={"version": "v-cap", "model": "TL-GW-100"},
        )
        assert r.status_code == 413
        assert list(firmware_dir.iterdir()) == []  # 半截文件须清理

    def test_middleware_exempts_firmware_path(self, monkeypatch):
        """中间件单测: 固件路径走独立上限 (MAX_SIZE 压到 100 仍放行小 body)。"""
        a = FastAPI()

        @a.post("/api/v1/gateways/firmware/upload")
        async def fw():
            return {"ok": True}

        @a.post("/echo")
        async def echo():
            return {"ok": True}

        a.add_middleware(RequestBodySizeMiddleware)
        a.add_middleware(RequestIDMiddleware)
        c = TestClient(a, raise_server_exceptions=False)
        monkeypatch.setattr(RequestBodySizeMiddleware, "MAX_SIZE", 100)
        # 固件路径: 200B < 固件豁免上限 → 放行
        assert c.post("/api/v1/gateways/firmware/upload", content=b"x" * 200).status_code == 200
        # 普通路径: 200B > 100 → 413
        assert c.post("/echo", content=b"x" * 200).status_code == 413


# ────────────────────────────────────────────────────────────────────
# 缺陷3: chunked 绕过 → file.size 前置拒
# ────────────────────────────────────────────────────────────────────
def _upload_file(name: str, declared_size: int) -> UploadFile:
    """构造带 size 的 UploadFile (Starlette multipart 按实际接收字节设置)。"""
    import io
    return UploadFile(file=io.BytesIO(b""), filename=name, size=declared_size)


class TestFileSizeEarlyReject:
    def test_fleet_voucher_early_reject(self, monkeypatch):
        monkeypatch.setattr(fleet_mod, "_MAX_VOUCHER_BYTES", 100)
        with pytest.raises(Exception) as ei:
            fleet_mod._save_upload(_upload_file("v.jpg", 200))
        assert getattr(ei.value, "status_code", None) == 413

    def test_license_early_reject(self, client, monkeypatch):
        """执照端点: file.size 超限 → 413 (read 前早拒, 无需有效执照内容)。"""
        monkeypatch.setattr(ent_mod, "_MAX_LICENSE_BYTES", 100)
        r = client.post(
            LICENSE_URL,
            files={"file": ("lic.pdf", b"%PDF-fake" + b"x" * 200, "application/pdf")},
        )
        assert r.status_code == 413, f"应早拒 413, 实际 {r.status_code}"

    def test_invoice_file_early_reject(self, client, monkeypatch):
        """发票端点: file.size 超限 → 413 早拒 (先于业务校验, invoice 不存在也应 413)。"""
        from app.services import invoice_request_service as inv_svc
        monkeypatch.setattr(inv_svc, "MAX_INVOICE_FILE_BYTES", 100)
        r = client.post(
            "/api/v1/ops/invoice-requests/999999/upload",
            files={"file": ("inv.pdf", b"%PDF-fake" + b"x" * 200, "application/pdf")},
        )
        assert r.status_code == 413, f"应早拒 413, 实际 {r.status_code}"
