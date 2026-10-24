"""
天链 V3 - 编码生成器服务

方案二：纯业务语义编码
- 团队：T + 区域码(2) + 序号(4) = 7位
- 站点：Z + 区域码(2) + 序号(4) = 7位
- 网关：G + 区域码(2) + 序号(6) = 9位
- 设备：D + 设备类型(2) + 序号(6) = 9位
"""
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, update
from app.core.database import SessionLocal
from app.models.code_sequence import CodeSequence
import logging

logger = logging.getLogger(__name__)


class CodeGenerator:
    """
    编码生成器 - 使用数据库序列表保证并发安全
    
    区域码 + 类型码互相独立序列
    """
    
    # 区域码（国标省码）
    REGIONS = {
        'HN': '河南', 'GD': '广东', 'JS': '江苏', 'SD': '山东',
        'ZJ': '浙江', 'FJ': '福建', 'SC': '四川', 'HB': '湖北',
        'HUN': '湖南', 'BJ': '北京', 'SH': '上海', 'GX': '广西',
        'SN': '陕西', 'CQ': '重庆', 'LN': '辽宁',
    }
    
    # 设备类型码
    DEVICE_TYPES = {
        'pv_inverter': 'PV',      # 光伏逆变器
        'pcs': 'PCS',              # 储能PCS
        'battery': 'BAT',          # 储能电池
        'charger_dc': 'CHG',       # 直流充电桩
        'charger_ac': 'CHG',       # 交流充电桩
        'meter': 'MET',            # 电表
        'gateway': 'GTW',          # 网关
    }
    
    # 编码前缀
    PREFIXES = {
        'team': 'T',
        'station': 'Z',
        'gateway': 'G',
        'device': 'D',
    }
    
    # 序号位数
    SEQ_LENGTHS = {
        'team': 4,      # 0001
        'station': 4,   # 0001
        'gateway': 6,   # 000001
        'device': 6,    # 000001
    }

    @staticmethod
    def _format_seq(seq_num: int, length: int) -> str:
        """
        序号格式化 + 溢出校验 (卡0aec53a8缺陷3)。

        旧代码 str(n).zfill(length) 无上限, 超 10**length 后码变长违反规格
        (如 team 第10000个 → THN10000 8位)。现校验超上限 raise ValueError。
        """
        max_val = 10 ** length - 1
        if seq_num < 0 or seq_num > max_val:
            raise ValueError(
                f"序号溢出: seq={seq_num} 超过 {length} 位上限 ({max_val})"
            )
        return str(seq_num).zfill(length)

    @staticmethod
    def _get_or_create_sequence(db: Session, key: str) -> Optional[CodeSequence]:
        """
        获取或创建序列记录（使用行锁保证并发安全）
        """
        try:
            # 使用 SELECT FOR UPDATE 锁定行
            seq = db.execute(
                select(CodeSequence).where(CodeSequence.key == key).with_for_update()
            ).scalar_one_or_none()

            if not seq:
                seq = CodeSequence(key=key, current_value=0)
                db.add(seq)
                db.flush()  # 立即写入以获取锁

            return seq
        except Exception as e:
            db.rollback()
            logger.error("获取/创建序列[%s]失败: %s", key, e)
            return None
    
    @staticmethod
    def _next_value(db: Session, key: str) -> int:
        """
        获取下一个序列值（并发安全）

        使用原子 UPDATE ... SET current_value = current_value + 1 RETURNING current_value
        保证在 SQLite（无行锁）和 PostgreSQL 上均无 lost update。

        卡0aec53a8缺陷4: IntegrityError 重试不再用 db.rollback()（会破坏共享的调用方事务），
        改用 savepoint (begin_nested)：败方 INSERT 在 savepoint 内失败，仅回滚 savepoint，
        外层调用方事务不受影响，随后重试原子 UPDATE 拿到胜方插入的行。
        """
        result = db.execute(
            update(CodeSequence)
            .where(CodeSequence.key == key)
            .values(current_value=CodeSequence.current_value + 1)
            .returning(CodeSequence.current_value)
        )
        new_val = result.scalar_one_or_none()
        if new_val is not None:
            return new_val

        # 序列行不存在 — 创建（首次调用）
        # 并发时可能两方同时 INSERT，唯一约束保护：败方在 savepoint 内失败，
        # 回滚 savepoint（不破坏调用方事务）后重试原子 UPDATE 命中胜方插入的行。
        from sqlalchemy.exc import IntegrityError
        try:
            nested = db.begin_nested()
            seq = CodeSequence(key=key, current_value=1)
            db.add(seq)
            db.flush()
            nested.commit()
            return 1
        except IntegrityError:
            nested.rollback()
            result = db.execute(
                update(CodeSequence)
                .where(CodeSequence.key == key)
                .values(current_value=CodeSequence.current_value + 1)
                .returning(CodeSequence.current_value)
            )
            return result.scalar_one()
    
    @staticmethod
    def generate_team_code(region: str = 'HN', db: Session = None) -> str:
        """
        生成团队编码

        Args:
            region: 区域码（如 HN, GD）
            db: 数据库session

        Returns:
            编码字符串，如 'THN0001'

        卡0aec53a8: 提交边界交由调用方控制（不内部 commit/rollback）；
        无 db 时内部 session 用 own_db 标记确保 finally 正确关闭。
        """
        own_db = db is None
        if own_db:
            db = SessionLocal()

        try:
            # 验证区域码
            if region not in CodeGenerator.REGIONS:
                logger.warning(f"未知区域码: {region}, 使用默认HN")
                region = 'HN'

            # 序列key: seq:team:HN
            key = f"seq:team:{region}"
            seq_num = CodeGenerator._next_value(db, key)

            # 格式: T + 区域码(2) + 序号(4)
            code = f"T{region}{CodeGenerator._format_seq(seq_num, 4)}"

            logger.info(f"生成团队编码: {code}")
            return code
        finally:
            if own_db and db:
                db.close()
    
    @staticmethod
    def generate_station_code(region: str = 'HN', db: Session = None) -> str:
        """
        生成站点编码
        
        Args:
            region: 区域码
            db: 数据库session
            
        Returns:
            编码字符串，如 'ZHN0001'
        """
        own_db = db is None
        if own_db:
            db = SessionLocal()

        try:
            if region not in CodeGenerator.REGIONS:
                logger.warning(f"未知区域码: {region}, 使用默认HN")
                region = 'HN'

            key = f"seq:station:{region}"
            seq_num = CodeGenerator._next_value(db, key)

            # 格式: Z + 区域码(2) + 序号(4)
            code = f"Z{region}{CodeGenerator._format_seq(seq_num, 4)}"

            logger.info(f"生成站点编码: {code}")
            return code
        finally:
            if own_db and db:
                db.close()
    
    @staticmethod
    def generate_gateway_sn(region: str = 'HN', db: Session = None) -> str:
        """
        生成网关SN
        
        Args:
            region: 区域码
            db: 数据库session
            
        Returns:
            编码字符串，如 'GHN000001'
        """
        own_db = db is None
        if own_db:
            db = SessionLocal()

        try:
            if region not in CodeGenerator.REGIONS:
                logger.warning(f"未知区域码: {region}, 使用默认HN")
                region = 'HN'

            key = f"seq:gateway:{region}"
            seq_num = CodeGenerator._next_value(db, key)

            # 格式: G + 区域码(2) + 序号(6)
            code = f"G{region}{CodeGenerator._format_seq(seq_num, 6)}"

            logger.info(f"生成网关SN: {code}")
            return code
        finally:
            if own_db and db:
                db.close()
    
    @staticmethod
    def generate_device_sn(device_type: str, region: str = 'HN', db: Session = None) -> str:
        """
        生成设备SN
        
        Args:
            device_type: 设备类型（如 pv_inverter, pcs）
            region: 区域码
            db: 数据库session
            
        Returns:
            编码字符串，如 'DPV000001'
        """
        own_db = db is None
        if own_db:
            db = SessionLocal()

        try:
            if region not in CodeGenerator.REGIONS:
                logger.warning(f"未知区域码: {region}, 使用默认HN")
                region = 'HN'

            # 获取设备类型码
            type_code = CodeGenerator.DEVICE_TYPES.get(device_type)
            if not type_code:
                logger.warning(f"未知设备类型: {device_type}, 使用默认PV")
                type_code = 'PV'

            # 序列key: seq:device:HN:PV
            key = f"seq:device:{region}:{type_code}"
            seq_num = CodeGenerator._next_value(db, key)

            # 格式: D + 设备类型(2) + 序号(6)
            code = f"D{type_code}{CodeGenerator._format_seq(seq_num, 6)}"

            logger.info(f"生成设备SN: {code} (类型: {device_type}, 区域: {region})")
            return code
        finally:
            if own_db and db:
                db.close()
    
    @staticmethod
    def batch_generate_gateway_sn(count: int, region: str = 'HN', db: Session = None) -> list[str]:
        """
        批量生成网关SN
        
        Args:
            count: 数量（1-1000）
            region: 区域码
            db: 数据库session
            
        Returns:
            编码列表
        """
        if count < 1 or count > 1000:
            raise ValueError("数量必须在1-1000之间")

        own_db = db is None
        if own_db:
            db = SessionLocal()

        try:
            if region not in CodeGenerator.REGIONS:
                logger.warning(f"未知区域码: {region}, 使用默认HN")
                region = 'HN'

            key = f"seq:gateway:{region}"
            codes = []

            for _ in range(count):
                seq_num = CodeGenerator._next_value(db, key)
                code = f"G{region}{CodeGenerator._format_seq(seq_num, 6)}"
                codes.append(code)

            # 保留内部 commit: gateways.py generate_sn_codes 端点不 self-commit,
            # 整个端点(序列自增 + GatewaySN 行)持久化依赖此处提交。
            db.commit()
            logger.info(f"批量生成网关SN: {len(codes)}个, 区域: {region}")
            return codes
        except Exception as e:
            db.rollback()
            logger.error(f"批量生成网关SN失败: {e}")
            raise
        finally:
            if own_db and db:
                db.close()


# 单例实例
code_generator = CodeGenerator()