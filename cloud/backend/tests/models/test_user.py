#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
User 模型测试
"""
import pytest
from app.models.user import User, Team

class TestUserModel:
    def test_user_columns(self):
        cols = [c.name for c in User.__table__.columns]
        assert "id" in cols
        assert "username" in cols
        assert "password_hash" in cols
        assert "real_name" in cols
        assert "role" in cols
        assert "status" in cols
        assert "phone" in cols
        assert "phone" in cols
        assert "latitude" in cols  # User uses latitude
        assert "level" in cols
        assert "team_id" in cols
        assert "created_at" in cols
        assert "updated_at" in cols

    def test_username_uniqueness(self):
        assert User.__table__.columns["username"].unique

    def test_team_columns(self):
        cols = [c.name for c in Team.__table__.columns]
        assert "id" in cols
        assert "name" in cols
        assert "description" in cols

    def test_user_relationships(self):
        assert hasattr(User, "team")
        assert hasattr(User, "team")  # User has team_id FK

    def test_user_default_status(self):
        assert User.__table__.columns["status"].default.arg == "active"