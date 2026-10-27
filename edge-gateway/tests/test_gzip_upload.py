"""F-gzip: CloudClient 上行 gzip 压缩单元测试

覆盖:
- 大 payload (>= compress_threshold) → gzip + Content-Encoding: gzip
- 小 payload → 明文发送
- compress_enabled=False → 明文发送
- 服务端 4xx 拒绝 gzip → 本会话永久关闭压缩, 立即明文重试成功 (自适应降级)
- 大遥测批量压缩率验证
"""

import gzip
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.cloud_client import CloudClient
from config import CloudConfig

BIG_PAYLOAD = {
    "records": [
        {"device_id": i, "power": 60.5, "voltage": 400, "current": 150, "soc": 55}
        for i in range(50)
    ],
    "pod_id": "GW-GZIP",
}
SMALL_PAYLOAD = {"records": [{"device_id": 1}], "pod_id": "GW-GZIP"}


def _make_client(status_codes, compress=True, threshold=64):
    config = CloudConfig(
        base_url="http://localhost:8000",
        heartbeat_interval=0,
        register_on_startup=False,
        deregister_on_shutdown=False,
        compress_enabled=compress,
        compress_threshold=threshold,
    )
    cc = CloudClient(config, gateway_id="GW-GZIP")
    responses = []
    for code in status_codes:
        resp = MagicMock()
        resp.status_code = code
        resp.text = ""
        responses.append(resp)
    cc._client = AsyncMock()
    cc._client.post = AsyncMock(side_effect=responses)
    return cc


class TestGzipUpload:

    @pytest.mark.asyncio
    async def test_large_payload_compressed(self):
        cc = _make_client([200])
        ok = await cc._post_with_retry("/api/v1/telemetry/batch-report", BIG_PAYLOAD, "t")
        assert ok is True
        kwargs = cc._client.post.call_args.kwargs
        assert kwargs["headers"].get("Content-Encoding") == "gzip"
        assert kwargs["headers"].get("Content-Type") == "application/json"
        assert json.loads(gzip.decompress(kwargs["content"])) == BIG_PAYLOAD

    @pytest.mark.asyncio
    async def test_small_payload_plain(self):
        cc = _make_client([200])
        ok = await cc._post_with_retry("/x", SMALL_PAYLOAD, "t")
        assert ok is True
        kwargs = cc._client.post.call_args.kwargs
        assert "Content-Encoding" not in kwargs["headers"]
        assert json.loads(kwargs["content"]) == SMALL_PAYLOAD

    @pytest.mark.asyncio
    async def test_compress_disabled(self):
        cc = _make_client([200], compress=False)
        ok = await cc._post_with_retry("/x", BIG_PAYLOAD, "t")
        assert ok is True
        kwargs = cc._client.post.call_args.kwargs
        assert "Content-Encoding" not in kwargs["headers"]
        assert json.loads(kwargs["content"]) == BIG_PAYLOAD

    @pytest.mark.asyncio
    async def test_gzip_rejected_adaptive_fallback(self):
        """服务端拒绝 gzip (4xx) → 关压缩 + 立即明文重试

        注: headers dict 在回退时被原地修改, 断言以 content 字节为准
        (首次请求 content 为 gzip 流, 回退后为明文 JSON)。
        """
        cc = _make_client([400, 200])
        ok = await cc._post_with_retry("/x", BIG_PAYLOAD, "t")
        assert ok is True
        assert cc._gzip_disabled is True
        assert cc._client.post.await_count == 2
        first = cc._client.post.await_args_list[0].kwargs
        second = cc._client.post.await_args_list[1].kwargs
        # 首次请求发出 gzip 流
        assert json.loads(gzip.decompress(first["content"])) == BIG_PAYLOAD
        # 回退后明文重发
        assert json.loads(second["content"]) == BIG_PAYLOAD
        assert "Content-Encoding" not in second["headers"]

    @pytest.mark.asyncio
    async def test_plain_rejected_no_retry(self):
        """明文被 4xx 拒绝 → 不重试, 直接失败 (保持原行为)"""
        cc = _make_client([400])
        ok = await cc._post_with_retry("/x", SMALL_PAYLOAD, "t")
        assert ok is False
        assert cc._client.post.await_count == 1

    def test_compression_ratio(self):
        """大遥测批量 gzip 压缩率应显著 (<0.6)"""
        body = json.dumps(BIG_PAYLOAD).encode("utf-8")
        ratio = len(gzip.compress(body)) / len(body)
        assert ratio < 0.6
