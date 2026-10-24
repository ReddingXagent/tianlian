"""
数字孪生数据模型
"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime

from app.models.digital_twin import ThreeDModelType

# ========== 设备数字孪生配置 ==========

class DigitalTwinModelBase(BaseModel):
    """设备数字孪生配置基类"""
    model_type: ThreeDModelType = Field(..., description="3D模型类型")
    
    # 3D变换参数
    scale_x: float = Field(1.0, ge=0.1, le=10.0, description="X轴缩放")
    scale_y: float = Field(1.0, ge=0.1, le=10.0, description="Y轴缩放")
    scale_z: float = Field(1.0, ge=0.1, le=10.0, description="Z轴缩放")
    position_x: float = Field(0.0, description="X轴位置")
    position_y: float = Field(0.0, description="Y轴位置")
    position_z: float = Field(0.0, description="Z轴位置")
    rotation_x: float = Field(0.0, ge=0.0, le=6.283, description="X轴旋转（弧度）")
    rotation_y: float = Field(0.0, ge=0.0, le=6.283, description="Y轴旋转（弧度）")
    rotation_z: float = Field(0.0, ge=0.0, le=6.283, description="Z轴旋转（弧度）")
    
    # 材质颜色
    color_primary: str = Field("#1890ff", description="主色")
    color_secondary: str = Field("#52c41a", description="次要色")
    color_accent: str = Field("#faad14", description="强调色")
    
    # 动画配置
    animations: Dict[str, Any] = Field(default_factory=dict, description="动画配置")
    
    # 状态映射
    status_mapping: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="状态到颜色/动画的映射"
    )

class DigitalTwinModelCreate(DigitalTwinModelBase):
    """创建设备数字孪生配置"""
    device_id: int = Field(..., description="设备ID")

class DigitalTwinModelUpdate(BaseModel):
    """更新设备数字孪生配置"""
    model_type: Optional[ThreeDModelType] = None
    scale_x: Optional[float] = None
    scale_y: Optional[float] = None
    scale_z: Optional[float] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    position_z: Optional[float] = None
    rotation_x: Optional[float] = None
    rotation_y: Optional[float] = None
    rotation_z: Optional[float] = None
    color_primary: Optional[str] = None
    color_secondary: Optional[str] = None
    color_accent: Optional[str] = None
    animations: Optional[Dict[str, Any]] = None
    status_mapping: Optional[Dict[str, Dict[str, Any]]] = None

class DigitalTwinModelResponse(DigitalTwinModelBase):
    """设备数字孪生配置响应"""
    id: int
    device_id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# ========== 场景配置 ==========

class CameraConfig(BaseModel):
    """相机配置"""
    position: List[float] = Field([0, 10, 15], description="相机位置")
    fov: float = Field(50, ge=10, le=120, description="视野角度")
    near: float = Field(0.1, gt=0, description="近裁剪面")
    far: float = Field(1000, gt=0, description="远裁剪面")

class LightConfig(BaseModel):
    """灯光配置"""
    type: str = Field(..., description="灯光类型: ambient, directional, point, spot")
    color: str = Field("#ffffff", description="灯光颜色")
    intensity: float = Field(1.0, ge=0, le=5, description="灯光强度")
    position: Optional[List[float]] = None  # 定向光/点光源位置
    target: Optional[List[float]] = None    # 聚光灯目标位置
    distance: Optional[float] = None        # 最大距离
    angle: Optional[float] = None           # 聚光灯角度
    penumbra: Optional[float] = None        # 半影区大小

class GridConfig(BaseModel):
    """网格配置"""
    enabled: bool = Field(True, description="是否显示网格")
    size: float = Field(50, gt=0, description="网格大小")
    divisions: int = Field(50, gt=0, description="网格分割数")
    colorCenterLine: str = Field("#666666", description="中心线颜色")
    colorGrid: str = Field("#444444", description="网格颜色")

class AxesConfig(BaseModel):
    """坐标轴配置"""
    enabled: bool = Field(True, description="是否显示坐标轴")
    size: float = Field(5, gt=0, description="坐标轴大小")

class GroundConfig(BaseModel):
    """地面配置"""
    enabled: bool = Field(True, description="是否显示地面")
    color: str = Field("#333333", description="地面颜色")
    opacity: float = Field(0.8, ge=0, le=1, description="透明度")

class SceneConfig(BaseModel):
    """场景配置"""
    camera: CameraConfig = Field(default_factory=CameraConfig, description="相机配置")
    lights: List[LightConfig] = Field(
        default_factory=lambda: [
            LightConfig(type="ambient", color="#ffffff", intensity=0.5),
            LightConfig(type="directional", position=[5, 10, 5], color="#ffffff", intensity=0.8)
        ],
        description="灯光配置"
    )
    grid: GridConfig = Field(default_factory=GridConfig, description="网格配置")
    axes: AxesConfig = Field(default_factory=AxesConfig, description="坐标轴配置")
    ground: GroundConfig = Field(default_factory=GroundConfig, description="地面配置")

class DigitalTwinSceneBase(BaseModel):
    """数字孪生场景基类"""
    name: str = Field(..., description="场景名称")
    scene_config: SceneConfig = Field(default_factory=SceneConfig, description="场景配置")

class DigitalTwinSceneCreate(DigitalTwinSceneBase):
    """创建场景配置"""
    station_id: int = Field(..., description="站点ID")

class DigitalTwinSceneUpdate(BaseModel):
    """更新场景配置"""
    name: Optional[str] = None
    scene_config: Optional[SceneConfig] = None

class DigitalTwinSceneResponse(DigitalTwinSceneBase):
    """场景配置响应"""
    id: int
    station_id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# ========== 组合响应 ==========

class DeviceDigitalTwinConfig(BaseModel):
    """设备及其数字孪生配置"""
    device: Dict[str, Any]  # 设备基本信息
    digital_twin_config: DigitalTwinModelResponse

class StationDigitalTwinResponse(BaseModel):
    """站点完整数字孪生配置响应"""
    station: Dict[str, Any]  # 站点基本信息
    scene: DigitalTwinSceneResponse
    devices: Optional[List[DeviceDigitalTwinConfig]] = None

# ========== 状态可视化 ==========

class StatusVisualization(BaseModel):
    """状态可视化参数"""
    color: str = Field(..., description="颜色")
    animation: str = Field(..., description="动画类型: none, pulse, glow, blink, slow_pulse")
    intensity: float = Field(1.0, ge=0, le=1, description="强度")
    glow: bool = Field(False, description="是否发光")
    pulse_rate: float = Field(1.0, gt=0, description="脉冲速率")

class DigitalTwinDataPointCreate(BaseModel):
    """创建数据映射点"""
    param_key: str = Field(..., max_length=100, description="遥测参数键")
    display_name: str = Field(..., max_length=100, description="显示名称")
    unit: str = Field("", max_length=20, description="单位")
    visual_type: str = Field("color", description="映射类型: color/scale/position/animation/text")
    normal_range: Optional[Dict[str, Any]] = Field(None, description="正常范围")
    warn_range: Optional[Dict[str, Any]] = Field(None, description="告警范围")
    danger_range: Optional[Dict[str, Any]] = Field(None, description="危险范围")
    normal_color: str = Field("#52c41a", max_length=20, description="正常颜色")
    warn_color: str = Field("#faad14", max_length=20, description="告警颜色")
    danger_color: str = Field("#ff4d4f", max_length=20, description="危险颜色")
    show_value: bool = Field(True, description="是否显示数值")
    show_unit: bool = Field(True, description="是否显示单位")
    decimal_places: int = Field(1, description="小数位数")

class DigitalTwinDataPointResponse(BaseModel):
    """数据映射点响应"""
    id: int
    device_id: int
    param_key: str
    display_name: str
    unit: str
    visual_type: str
    normal_range: Optional[Dict[str, Any]] = None
    warn_range: Optional[Dict[str, Any]] = None
    danger_range: Optional[Dict[str, Any]] = None
    normal_color: str
    warn_color: str
    danger_color: str
    show_value: bool
    show_unit: bool
    decimal_places: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class DeviceStatusVisualization(BaseModel):
    """设备状态可视化响应"""
    device_id: int
    device_name: str
    device_status: str
    health_score: float
    visualization: StatusVisualization
    last_update: Optional[datetime] = None