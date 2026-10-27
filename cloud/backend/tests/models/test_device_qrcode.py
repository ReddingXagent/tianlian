#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Device QRCode 模型测试 — 工作卡 c7523ad8

云快充协议 V1.6：桩编号 14 位纯数字，枪号 = 桩编号 + 2 位枪号(16 位)。
模型需支持一桩多枪（多行 device_id），故：
- device_id 不再 unique（保留 index）；
- 新增 gun_no 列（default=1，nullable=False）；
- (device_id, gun_no) 唯一索引 uq_device_qrcode_device_gun；
- qr_code 仍唯一（现存放 16 位枪号）。
"""
import pytest
from app.models.device_qrcode import DeviceQRCode


class TestDeviceQRCodeModel:
    def test_device_qrcode_columns(self):
        cols = [c.name for c in DeviceQRCode.__table__.columns]
        assert "id" in cols
        assert "device_id" in cols
        assert "qr_code" in cols
        assert "qr_image_path" in cols
        assert "is_active" in cols
        assert "print_count" in cols
        assert "last_print_time" in cols
        # c7523ad8: 新增 gun_no 列
        assert "gun_no" in cols

    def test_qr_code_still_unique_but_device_id_not(self):
        """qr_code 保持唯一；device_id 不再列级唯一（一桩多枪）。"""
        assert DeviceQRCode.__table__.columns["qr_code"].unique is True
        # device_id 的唯一性迁移到 (device_id, gun_no) 复合唯一索引
        # （未设置 unique 时 SQLAlchemy 取值为 None，即 falsy）
        assert not DeviceQRCode.__table__.columns["device_id"].unique

    def test_gun_no_column_attrs(self):
        """gun_no: 默认 1，非空（按枪展开的基准枪号）。"""
        gun_no = DeviceQRCode.__table__.columns["gun_no"]
        assert gun_no.nullable is False
        assert gun_no.default.arg == 1

    def test_device_gun_unique_index(self):
        """(device_id, gun_no) 复合唯一索引存在 — 一桩内每枪唯一。"""
        indexes = DeviceQRCode.__table__.indexes
        matched = [
            ix for ix in indexes
            if set(ix.columns.keys()) == {"device_id", "gun_no"} and ix.unique
        ]
        assert matched, "缺少 (device_id, gun_no) 唯一索引"

    def test_device_qrcode_defaults(self):
        assert DeviceQRCode.__table__.columns["is_active"].default.arg is True
        assert DeviceQRCode.__table__.columns["print_count"].default.arg == 0

    def test_qr_code_length_supports_gun_code(self):
        """qr_code 字段长度足以容纳 16 位枪号（实际 String(200)）。"""
        qr_code = DeviceQRCode.__table__.columns["qr_code"]
        # String(200) 远大于 16 位枪号需求
        assert qr_code.type.length >= 16
