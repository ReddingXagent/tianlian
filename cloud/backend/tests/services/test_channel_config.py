"""ChannelConfig 模型 CRUD 单元测试 (卡 8d98ebe3)

被测模块: app/models/channel_config.py — ChannelConfig / ChannelType
隔离键 team_id (FK→teams), channel ENUM, config JSON 存各渠道凭证。
"""
import pytest

from app.models.channel_config import ChannelConfig, ChannelType


def _seed(db, team_id=None, channel=ChannelType.IM, config=None, enabled=True):
    cfg = ChannelConfig(
        team_id=team_id,
        channel=channel,
        config=config or {},
        enabled=enabled,
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


# ========== 枚举 ==========

def test_channel_type_enum_values():
    assert ChannelType.IM.value == "im"
    assert ChannelType.WECOM.value == "wecom"
    assert ChannelType.WEBHOOK.value == "webhook"
    assert ChannelType.SMS.value == "sms"
    assert ChannelType.VOICE.value == "voice"
    assert ChannelType.EMAIL.value == "email"


# ========== Create / Read ==========

def test_create_channel_config_im(test_db):
    db = test_db["session"]
    cfg = _seed(db, team_id=None, channel=ChannelType.IM,
                config={"webhook_url": "https://open.im.cn/open-apis/bot/v2/hook/xxx",
                        "secret": "abc"})
    assert cfg.id is not None
    assert cfg.team_id is None
    assert cfg.channel == ChannelType.IM
    assert cfg.config["webhook_url"].endswith("xxx")
    assert cfg.config["secret"] == "abc"
    assert cfg.enabled is True
    assert cfg.created_at is not None


def test_create_each_channel_type(test_db):
    db = test_db["session"]
    for ch in ChannelType:
        cfg = _seed(db, team_id=1, channel=ch)
        assert cfg.channel == ch


def test_config_stores_smtp_fields(test_db):
    db = test_db["session"]
    cfg = _seed(db, channel=ChannelType.EMAIL, config={
        "smtp_host": "smtp.qq.com", "smtp_port": 465,
        "smtp_user": "u", "smtp_pass": "p",
        "smtp_from": "noreply@tianlian.com",
    })
    db.expire_all()
    fresh = db.query(ChannelConfig).filter(ChannelConfig.id == cfg.id).one()
    assert fresh.config["smtp_host"] == "smtp.qq.com"
    assert fresh.config["smtp_port"] == 465


def test_config_stores_sms_and_voice_fields(test_db):
    db = test_db["session"]
    sms = _seed(db, channel=ChannelType.SMS, config={
        "sms_access_key": "AK", "sms_secret": "SK",
        "sign_name": "天链科技", "template_code": "SMS_001",
    })
    voice = _seed(db, channel=ChannelType.VOICE, config={
        "voice_access_key": "AK2", "voice_secret": "SK2",
        "voice_caller": "4001234567", "voice_template_code": "TTS_002",
    })
    assert sms.config["sign_name"] == "天链科技"
    assert voice.config["voice_caller"] == "4001234567"


# ========== Update ==========

def test_update_config_and_enabled(test_db):
    db = test_db["session"]
    cfg = _seed(db, channel=ChannelType.WEBHOOK, config={"webhook_url": "https://old"})
    cfg.config = {"webhook_url": "https://new", "secret": "s"}
    cfg.enabled = False
    db.commit()
    db.refresh(cfg)
    assert cfg.config["webhook_url"] == "https://new"
    assert cfg.enabled is False


# ========== team_id 隔离查询 ==========

def test_query_by_team_and_channel(test_db):
    db = test_db["session"]
    _seed(db, team_id=10, channel=ChannelType.IM, config={"webhook_url": "t10"})
    _seed(db, team_id=20, channel=ChannelType.IM, config={"webhook_url": "t20"})
    _seed(db, team_id=10, channel=ChannelType.SMS)

    hit = db.query(ChannelConfig).filter(
        ChannelConfig.team_id == 10,
        ChannelConfig.channel == ChannelType.IM,
    ).first()
    assert hit is not None
    assert hit.config["webhook_url"] == "t10"

    # team_id 隔离: team=20 不应拿到 team=10 的 sms
    other = db.query(ChannelConfig).filter(
        ChannelConfig.team_id == 20,
        ChannelConfig.channel == ChannelType.SMS,
    ).first()
    assert other is None


def test_query_disabled_channel(test_db):
    db = test_db["session"]
    _seed(db, team_id=1, channel=ChannelType.IM, enabled=False)
    hit = db.query(ChannelConfig).filter(
        ChannelConfig.team_id == 1,
        ChannelConfig.channel == ChannelType.IM,
        ChannelConfig.enabled == True,  # noqa: E712
    ).first()
    assert hit is None


# ========== Delete ==========

def test_delete_channel_config(test_db):
    db = test_db["session"]
    cfg = _seed(db, team_id=1, channel=ChannelType.EMAIL)
    pk = cfg.id
    db.delete(cfg)
    db.commit()
    assert db.query(ChannelConfig).filter(ChannelConfig.id == pk).first() is None
