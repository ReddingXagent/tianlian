"""
YAML 设备模板加载器 - 配置驱动设备接入

功能：
    - 扫描 templates/ 目录下的 YAML 模板文件
    - 按 category（inverter/pcs/meter/charger/bms）索引
    - 内存缓存 + 文件修改时间检测热重载
    - 支持运行时注册新模板

设计参考：
    evcc 的 charger/meter template 模式

Author: TianLian V3 Team
"""
import logging
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

import yaml

logger = logging.getLogger(__name__)


@dataclass
class DeviceTemplate:
    """设备模板数据类

    Attributes:
        device_type: 设备类型标识（如 inverter_eahi_20k）
        manufacturer: 制造商名称
        model: 型号
        category: 设备类别（inverter/pcs/meter/charger/bms）
        protocol: 通信协议（modbus_rtu/mqtt/rest/ocpp）
        connection: 连接参数
        registers: 寄存器/数据点定义列表
        source_file: 模板来源文件路径
    """
    device_type: str
    manufacturer: str
    model: str
    category: str
    protocol: str
    connection: Dict[str, Any] = field(default_factory=dict)
    registers: List[Dict[str, Any]] = field(default_factory=list)
    source_file: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "device_type": self.device_type,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "category": self.category,
            "protocol": self.protocol,
            "connection": self.connection,
            "registers": self.registers,
        }


class TemplateLoader:
    """
    YAML 设备模板加载器

    扫描指定目录下的 .yaml 文件，解析为 DeviceTemplate 对象，
    按 device_type 和 category 双索引缓存，支持基于文件 mtime 的热重载。

    Usage:
        >>> loader = TemplateLoader(template_dir="app/gateway/templates")
        >>> loader.load_all()
        >>> template = loader.get_template("inverter_eahi_20k")
        >>> by_cat = loader.get_by_category("inverter")
    """

    # 标准模板必填字段
    REQUIRED_FIELDS = {"device_type", "manufacturer", "model", "category", "protocol"}

    # 允许的设备类别
    VALID_CATEGORIES = {"inverter", "pcs", "meter", "charger", "bms"}

    def __init__(self, template_dir: str = ""):
        """
        Args:
            template_dir: YAML 模板目录路径，默认为当前目录下的 templates
        """
        if not template_dir:
            template_dir = str(Path(__file__).parent / "templates")

        self._template_dir = Path(template_dir)

        # 双索引缓存
        self._by_device_type: Dict[str, DeviceTemplate] = {}
        self._by_category: Dict[str, List[DeviceTemplate]] = {}

        # 文件 mtime 快照（用于热重载检测）
        self._file_mtimes: Dict[str, float] = {}

        # 线程安全锁
        self._lock = threading.RLock()

        # 已加载标志
        self._loaded = False

    # ── 公共 API ─────────────────────────────────────────────

    @property
    def template_dir(self) -> Path:
        """返回模板目录路径"""
        return self._template_dir

    def load_all(self) -> int:
        """扫描并加载所有 YAML 模板

        Returns:
            int: 成功加载的模板数量
        """
        with self._lock:
            self._by_device_type.clear()
            self._by_category.clear()
            self._file_mtimes.clear()

            count = 0
            if not self._template_dir.is_dir():
                logger.warning("模板目录不存在: %s", self._template_dir)
                self._loaded = True
                return 0

            for file_path in sorted(self._template_dir.glob("*.yaml")):
                try:
                    template = self._load_one(file_path)
                    self._index(template)
                    self._file_mtimes[str(file_path)] = file_path.stat().st_mtime
                    count += 1
                except Exception as e:
                    logger.error("加载模板失败 %s: %s", file_path.name, e)

            self._loaded = True
            logger.info("加载完成: %d 个设备模板", count)
            return count

    def reload_if_changed(self) -> int:
        """检测文件修改并热重载变更的模板

        Returns:
            int: 重载的模板数量（0 表示无变化）
        """
        updated_count = 0

        with self._lock:
            if not self._template_dir.is_dir():
                return 0

            for file_path in sorted(self._template_dir.glob("*.yaml")):
                key = str(file_path)
                current_mtime = file_path.stat().st_mtime

                if key not in self._file_mtimes or self._file_mtimes[key] != current_mtime:
                    try:
                        template = self._load_one(file_path)
                        self._remove_by_source_file(key)  # 清旧条目防 category 重复累积 (缺陷B)
                        self._index(template)
                        self._file_mtimes[key] = current_mtime
                        updated_count += 1
                        logger.debug("热重载: %s", file_path.name)
                    except Exception as e:
                        logger.error("热重载失败 %s: %s", file_path.name, e)

            # 检测已删除的文件
            current_files = {str(p) for p in self._template_dir.glob("*.yaml")}
            removed = set(self._file_mtimes.keys()) - current_files
            for removed_key in removed:
                logger.info("模板文件已删除: %s", removed_key)
                self._remove_by_source_file(removed_key)  # 同步清索引防 get_template 返旧模板 (缺陷A)
                del self._file_mtimes[removed_key]

        return updated_count

    def get_template(self, device_type: str) -> Optional[DeviceTemplate]:
        """按 device_type 获取设备模板

        Args:
            device_type: 设备类型标识

        Returns:
            Optional[DeviceTemplate]: 找到的模板，或 None
        """
        with self._lock:
            return self._by_device_type.get(device_type)

    def get_by_category(self, category: str) -> List[DeviceTemplate]:
        """按类别获取所有设备模板

        Args:
            category: 设备类别

        Returns:
            List[DeviceTemplate]: 该类别下的模板列表
        """
        with self._lock:
            return list(self._by_category.get(category, []))

    def list_device_types(self) -> Dict[str, str]:
        """列出所有设备类型 -> 协议类型映射

        Returns:
            Dict[str, str]: {device_type: protocol}
        """
        with self._lock:
            return {dt: t.protocol for dt, t in self._by_device_type.items()}

    def list_all(self) -> List[DeviceTemplate]:
        """列出所有已加载的模板"""
        with self._lock:
            return list(self._by_device_type.values())

    def register_template(self, template: DeviceTemplate) -> None:
        """运行时注册模板（用于 CLI add 命令，不写文件）

        Args:
            template: 要注册的模板对象
        """
        self._validate_template(template.to_dict())
        with self._lock:
            self._index(template)
            logger.info("运行时注册模板: %s", template.device_type)

    def add_template_from_file(self, file_path: str) -> DeviceTemplate:
        """从文件添加并索引模板

        Args:
            file_path: YAML 文件路径

        Returns:
            DeviceTemplate: 加载的模板
        """
        path = Path(file_path)
        template = self._load_one(path)
        with self._lock:
            self._index(template)
            self._file_mtimes[str(path)] = path.stat().st_mtime
        return template

    @staticmethod
    def validate_template_file(file_path: str) -> Dict[str, Any]:
        """验证单个 YAML 模板文件

        Args:
            file_path: 文件路径

        Returns:
            Dict: {"valid": bool, "errors": [...], "warnings": [...]}
        """
        result = {"valid": True, "errors": [], "warnings": []}

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            result["valid"] = False
            result["errors"].append(f"YAML 解析错误: {e}")
            return result
        except FileNotFoundError:
            result["valid"] = False
            result["errors"].append(f"文件不存在: {file_path}")
            return result

        if not isinstance(data, dict):
            result["valid"] = False
            result["errors"].append("YAML 内容必须是字典类型")
            return result

        # 检查必填字段
        missing = TemplateLoader.REQUIRED_FIELDS - set(data.keys())
        if missing:
            result["valid"] = False
            result["errors"].append(f"缺少必填字段: {missing}")

        # 检查 category 合法性
        if "category" in data and data["category"] not in TemplateLoader.VALID_CATEGORIES:
            result["valid"] = False
            result["errors"].append(f"无效的 category: {data['category']}，合法值: {TemplateLoader.VALID_CATEGORIES}")

        # 检查 device_type 命名规范
        if "device_type" in data:
            dt = data["device_type"]
            parts = str(dt).split("_")
            if len(parts) < 2:
                result["warnings"].append(f"device_type 建议使用 category_manufacturer_model 格式，如 inverter_eahi_20k")

        return result

    # ── 内部方法 ─────────────────────────────────────────────

    def _load_one(self, file_path: Path) -> DeviceTemplate:
        """从单个 YAML 文件加载模板

        Args:
            file_path: YAML 文件路径

        Returns:
            DeviceTemplate: 解析的模板对象

        Raises:
            ValueError: YAML 内容无效
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError("YAML 内容不是字典")

        self._validate_template(data)

        return DeviceTemplate(
            device_type=data["device_type"],
            manufacturer=data.get("manufacturer", "Unknown"),
            model=data.get("model", "Unknown"),
            category=data["category"],
            protocol=data["protocol"],
            connection=data.get("connection", {}),
            registers=data.get("registers", []),
            source_file=str(file_path),
        )

    def _validate_template(self, data: Dict[str, Any]) -> None:
        """验证模板数据完整性

        Args:
            data: 模板字典

        Raises:
            ValueError: 验证失败
        """
        missing = self.REQUIRED_FIELDS - set(data.keys())
        if missing:
            raise ValueError(f"缺少必填字段: {missing}")

        category = data.get("category", "")
        if category and category not in self.VALID_CATEGORIES:
            raise ValueError(f"无效的 category '{category}'，合法值: {self.VALID_CATEGORIES}")

    def _index(self, template: DeviceTemplate) -> None:
        """将模板加入双索引

        Args:
            template: 要索引的模板对象
        """
        # device_type 索引
        self._by_device_type[template.device_type] = template

        # category 索引
        if template.category not in self._by_category:
            self._by_category[template.category] = []
        self._by_category[template.category].append(template)

    def _remove_by_source_file(self, source_file: str) -> None:
        """按来源文件从双索引移除模板（热重载删除/变更前清理旧条目）

        修复 reload_if_changed 两处索引残留:
        - 删除分支仅清 _file_mtimes, 索引未清 → get_template 返已删文件旧模板 (缺陷A)
        - 变更分支 _index 对 category list 为 append 不查重 → get_by_category 重复 (缺陷B)

        load_all 路径先 clear 全量重建, 不经此方法, 行为不受影响。

        Args:
            source_file: 模板来源文件路径 (与 _file_mtimes 的 key / DeviceTemplate.source_file 同源)
        """
        # device_type 索引: 剔除该来源文件对应的所有模板
        stale_dts = [
            dt for dt, t in self._by_device_type.items()
            if t.source_file == source_file
        ]
        for dt in stale_dts:
            del self._by_device_type[dt]

        # category 索引: 逐类别剔除该来源文件的模板 (列表推导重建, 不破坏 load_all 路径)
        for category, templates in self._by_category.items():
            self._by_category[category] = [
                t for t in templates if t.source_file != source_file
            ]


# ── 全局加载器实例 ─────────────────────────────────────────

_global_loader: Optional[TemplateLoader] = None
_loader_lock = threading.Lock()


def get_template_loader(template_dir: Optional[str] = None) -> TemplateLoader:
    """获取全局模板加载器（单例）

    Args:
        template_dir: 模板目录路径（首次调用时生效）

    Returns:
        TemplateLoader: 全局实例

    Note:
        并发安全（模块级单例层）:
        - 模块锁 _loader_lock 内仅做 构造 + 发布赋值, 不做重 IO;
          原实现把 load_all() 全目录扫描 + YAML 解析放在锁内, 并发首调时其余线程
          全部阻塞在 _loader_lock 上, 文件系统慢时表现为 hang。
        - load_all() 移到模块锁外, 由实例级 RLock(self._lock) + _loaded 标志保证
          多线程首调只加载一次, 后到线程读到已加载状态;
        - 全局引用读一次到局部变量, 杜绝 return 处重读与 reset_template_loader 的竞态。
    """
    global _global_loader

    loader = _global_loader
    if loader is None:
        with _loader_lock:
            loader = _global_loader
            if loader is None:
                loader = TemplateLoader(template_dir=template_dir or "")
                _global_loader = loader

    # 重 IO 移到模块锁外; 实例 RLock + _loaded 标志保证只加载一次
    with loader._lock:
        if not loader._loaded:
            loader.load_all()

    return loader


def reset_template_loader() -> None:
    """重置全局加载器（用于测试）

    Note:
        纳入 _loader_lock, 与 get_template_loader 的构造临界区互斥, 避免 reset 与 get
        并发时 get 的全局重读撞上裸 None 写而返回 None / 半构造实例。
    """
    global _global_loader
    with _loader_lock:
        _global_loader = None
