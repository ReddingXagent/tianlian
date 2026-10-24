/**
 * Device3DModel - 3D设备模型组件
 * Phase9 - 数字孪生可视化
 *
 * 使用 @react-three/fiber + @react-three/drei 构建参数化3D设备模型
 * 实时数据映射：设备状态→颜色、功率→发光强度、温度→颜色渐变、充电→脉冲动画
 */
import React, { useRef, useState, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import * as THREE from 'three';

// ==================== 状态→颜色映射 ====================
const STATUS_COLORS: Record<string, { body: string; emissive: string; ring: string }> = {
  online:      { body: '#34a853', emissive: '#237804', ring: '#34a853' },   // 正常=绿
  warning:     { body: '#f5a623', emissive: '#d48806', ring: '#f5a623' },   // 告警=黄
  alarm:       { body: '#f5a623', emissive: '#d48806', ring: '#f5a623' },   // 告警=黄 (alias)
  charging:    { body: '#fa8c16', emissive: '#ad6800', ring: '#fa8c16' },   // 充电中=橙
  fault:       { body: '#ea4335', emissive: '#a8071a', ring: '#ea4335' },   // 故障=红
  offline:     { body: '#a6a1a0', emissive: '#434343', ring: '#595959' },   // 离线=灰
  maintenance: { body: '#ff5a36', emissive: '#e54d2e', ring: '#ff5a36' },
};

function getStatusColors(status: string) {
  return STATUS_COLORS[status] || STATUS_COLORS.offline;
}

// 根据温度计算颜色（25°C绿色 → 60°C红色）
function temperatureColor(tempC: number): string {
  if (tempC <= 25) return '#34a853';
  if (tempC >= 70) return '#ea4335';
  const t = (tempC - 25) / 45; // 0~1
  const r = Math.round(82 + t * 173);
  const g = Math.round(196 - t * 120);
  const b = Math.round(26 + t * 53);
  return `rgb(${r},${g},${b})`;
}

// 根据功率计算发光强度（0kW→0.1, 100kW→0.8）
function powerIntensity(powerKw: number): number {
  return Math.min(0.8, 0.1 + (powerKw / 100) * 0.7);
}

// ==================== 动画组件 ====================
const FloatingAnimation: React.FC<{
  children: React.ReactNode;
  active: boolean;
  speed?: number;
  amplitude?: number;
}> = ({ children, active, speed = 1.5, amplitude = 0.02 }) => {
  const groupRef = useRef<THREE.Group>(null!);
  useFrame(({ clock }) => {
    if (groupRef.current && active) {
      groupRef.current.position.y = Math.sin(clock.getElapsedTime() * speed) * amplitude;
    }
  });
  return <group ref={groupRef}>{children}</group>;
};

const RotatingRing: React.FC<{ color: string; radius: number; speed?: number }> = ({
  color, radius, speed = 2,
}) => {
  const meshRef = useRef<THREE.Mesh>(null!);
  useFrame(({ clock }) => {
    if (meshRef.current) meshRef.current.rotation.z = clock.getElapsedTime() * speed;
  });
  return (
    <mesh ref={meshRef} rotation={[Math.PI / 2, 0, 0]} position={[0, 0.05, 0]}>
      <ringGeometry args={[radius, radius + 0.05, 32]} />
      <meshBasicMaterial color={color} transparent opacity={0.5} />
    </mesh>
  );
};

/** 故障闪烁效果 */
const FaultBlink: React.FC<{ children: React.ReactNode; isFault: boolean }> = ({ children, isFault }) => {
  const groupRef = useRef<THREE.Group>(null!);
  useFrame(({ clock }) => {
    if (groupRef.current && isFault) {
      const blink = Math.sin(clock.getElapsedTime() * 6) > 0;
      groupRef.current.visible = blink;
    } else if (groupRef.current) {
      groupRef.current.visible = true;
    }
  });
  return <group ref={groupRef}>{children}</group>;
};

/** 充电脉冲效果 */
const ChargingPulse: React.FC<{ isCharging: boolean; color: string }> = ({ isCharging, color }) => {
  const meshRef = useRef<THREE.Mesh>(null!);
  useFrame(({ clock }) => {
    if (meshRef.current && isCharging) {
      const s = 1 + Math.sin(clock.getElapsedTime() * 3) * 0.15;
      meshRef.current.scale.set(s, s, s);
      (meshRef.current.material as THREE.MeshBasicMaterial).opacity = 0.1 + Math.sin(clock.getElapsedTime() * 3) * 0.1;
    }
  });
  if (!isCharging) return null;
  return (
    <mesh ref={meshRef} position={[0, 0.8, 0]}>
      <sphereGeometry args={[2, 16, 16]} />
      <meshBasicMaterial color={color} transparent opacity={0.15} />
    </mesh>
  );
};

// ==================== 设备模型 ====================
/** 逆变器 3D 模型 */
const InverterModel: React.FC<{
  statusColors: typeof STATUS_COLORS.online;
  intensity: number;
  isSelected: boolean;
}> = ({ statusColors, intensity, isSelected }) => (
  <group>
    <mesh position={[0, 0.75, 0]} castShadow>
      <boxGeometry args={[2, 1.5, 1]} />
      <meshStandardMaterial
        color={isSelected ? '#ff5a36' : statusColors.body}
        emissive={statusColors.emissive}
        emissiveIntensity={intensity}
        metalness={0.8}
        roughness={0.2}
      />
    </mesh>
    {Array.from({ length: 8 }).map((_, i) => (
      <mesh key={`fin-${i}`} position={[-0.95, 0.75, -0.4 + i * 0.114]} castShadow>
        <boxGeometry args={[0.05, 1.3, 0.08]} />
        <meshStandardMaterial color="#333" metalness={0.9} roughness={0.1} />
      </mesh>
    ))}
    <mesh position={[0.5, 1.2, 0.51]}>
      <sphereGeometry args={[0.06, 16, 16]} />
      <meshStandardMaterial
        color={statusColors.body}
        emissive={statusColors.body}
        emissiveIntensity={0.8}
      />
    </mesh>
    {isSelected && (
      <mesh position={[0, 0.75, 0]}>
        <boxGeometry args={[2.2, 1.7, 1.2]} />
        <meshBasicMaterial color="#ff5a36" transparent opacity={0.3} wireframe />
      </mesh>
    )}
  </group>
);

/** 光伏板 3D 模型 */
const PVPanelModel: React.FC<{
  statusColors: typeof STATUS_COLORS.online;
  intensity: number;
  isSelected: boolean;
}> = ({ statusColors, intensity, isSelected }) => (
  <group>
    {/* 太阳能板主体 */}
    <mesh position={[0, 1.2, 0]} rotation={[-Math.PI / 6, 0, 0]} castShadow>
      <boxGeometry args={[3, 0.08, 2]} />
      <meshStandardMaterial
        color="#1e1918"
        metalness={0.9}
        roughness={0.05}
        transparent
        opacity={0.85}
      />
    </mesh>
    {/* 电池网格 - 用细长盒子代替 line，R3F 声明式更稳定 */}
    {Array.from({ length: 5 }).map((_, i) => (
      <mesh key={`gh-${i}`} position={[0, 1.17, -0.8 + i * 0.4]} rotation={[-Math.PI / 6, 0, 0]}>
        <boxGeometry args={[2.9, 0.01, 0.02]} />
        <meshStandardMaterial color="#4dabf7" emissive="#4dabf7" emissiveIntensity={intensity} />
      </mesh>
    ))}
    {Array.from({ length: 7 }).map((_, i) => (
      <mesh key={`gv-${i}`} position={[-1.2 + i * 0.4, 1.17, 0]} rotation={[-Math.PI / 6, 0, 0]}>
        <boxGeometry args={[0.02, 0.01, 1.9]} />
        <meshStandardMaterial color="#4dabf7" emissive="#4dabf7" emissiveIntensity={intensity} />
      </mesh>
    ))}
    {/* 支架 */}
    <mesh position={[0, 0.6, 0]} castShadow>
      <cylinderGeometry args={[0.06, 0.06, 1.2, 8]} />
      <meshStandardMaterial color="#666" metalness={0.8} roughness={0.2} />
    </mesh>
    {/* 底座 */}
    <mesh position={[0, 0, 0]} castShadow>
      <boxGeometry args={[1, 0.1, 1]} />
      <meshStandardMaterial color="#555" metalness={0.7} roughness={0.3} />
    </mesh>
    {isSelected && (
      <mesh position={[0, 1.2, 0]} rotation={[-Math.PI / 6, 0, 0]}>
        <boxGeometry args={[3.2, 0.02, 2.2]} />
        <meshBasicMaterial color="#ff5a36" transparent opacity={0.2} />
      </mesh>
    )}
  </group>
);

/** 储能柜 3D 模型 */
const BatteryModel: React.FC<{
  statusColors: typeof STATUS_COLORS.online;
  intensity: number;
  isSelected: boolean;
  tempColor: string;
  socPercent: number; // 0~100
}> = ({ statusColors, intensity, isSelected, tempColor, socPercent }) => {
  const barCount = 4;
  const litBars = Math.max(1, Math.round((socPercent / 100) * barCount));
  return (
    <group>
      <mesh position={[0, 0.75, 0]} castShadow>
        <boxGeometry args={[1.5, 1.5, 1.5]} />
        <meshStandardMaterial
          color={isSelected ? '#ff5a36' : statusColors.body}
          emissive={statusColors.emissive}
          emissiveIntensity={intensity}
          metalness={0.5}
          roughness={0.5}
        />
      </mesh>
      {/* 电量指示条 - 亮灯数量跟随SOC */}
      {Array.from({ length: barCount }).map((_, i) => (
        <mesh key={`bar-${i}`} position={[-0.8, 0.35 + i * 0.3, 0.76]}>
          <boxGeometry args={[0.3, 0.15, 0.02]} />
          <meshStandardMaterial
            color={i < litBars ? '#34a853' : '#434343'}
            emissive={i < litBars ? '#34a853' : '#000000'}
            emissiveIntensity={i < litBars ? 0.5 : 0}
          />
        </mesh>
      ))}
      {/* 温度指示 */}
      <mesh position={[0.8, 0.75, 0.76]}>
        <boxGeometry args={[0.15, 0.8, 0.02]} />
        <meshStandardMaterial color={tempColor} emissive={tempColor} emissiveIntensity={0.3} />
      </mesh>
      {/* 正负极标识 */}
      <mesh position={[0.4, 1.52, 0]}>
        <cylinderGeometry args={[0.1, 0.1, 0.04, 16]} />
        <meshStandardMaterial color="#ea4335" />
      </mesh>
      <mesh position={[-0.4, 1.52, 0]}>
        <cylinderGeometry args={[0.1, 0.1, 0.04, 16]} />
        <meshStandardMaterial color="#ff5a36" />
      </mesh>
      {isSelected && (
        <mesh position={[0, 0.75, 0]}>
          <boxGeometry args={[1.7, 1.7, 1.7]} />
          <meshBasicMaterial color="#ff5a36" transparent opacity={0.2} wireframe />
        </mesh>
      )}
    </group>
  );
};

/** 充电桩 3D 模型 */
const ChargerModel: React.FC<{
  statusColors: typeof STATUS_COLORS.online;
  intensity: number;
  isSelected: boolean;
  isCharging: boolean;
}> = ({ statusColors, intensity, isSelected, isCharging }) => {
  const topRingRef = useRef<THREE.Mesh>(null!);
  useFrame(({ clock }) => {
    if (topRingRef.current && isCharging) {
      const pulse = 0.8 + Math.sin(clock.getElapsedTime() * 4) * 0.2;
      (topRingRef.current.material as THREE.MeshStandardMaterial).emissiveIntensity = pulse;
    }
  });
  return (
    <group>
      <mesh position={[0, 1, 0]} castShadow>
        <cylinderGeometry args={[0.4, 0.5, 2, 16]} />
        <meshStandardMaterial
          color={isSelected ? '#ff5a36' : statusColors.body}
          emissive={statusColors.emissive}
          emissiveIntensity={intensity}
          metalness={0.7}
          roughness={0.3}
        />
      </mesh>
      <mesh ref={topRingRef} position={[0, 2.05, 0]}>
        <torusGeometry args={[0.4, 0.03, 8, 32]} />
        <meshStandardMaterial
          color={statusColors.body}
          emissive={statusColors.body}
          emissiveIntensity={0.8}
        />
      </mesh>
      <mesh position={[0.6, 0.5, 0]} rotation={[0, 0, Math.PI / 4]} castShadow>
        <cylinderGeometry args={[0.06, 0.04, 0.8, 8]} />
        <meshStandardMaterial color="#333" metalness={0.9} roughness={0.1} />
      </mesh>
      <mesh position={[0, 1.3, 0.42]}>
        <boxGeometry args={[0.3, 0.5, 0.02]} />
        <meshStandardMaterial color="#111" metalness={0.95} roughness={0.05} />
      </mesh>
      {isSelected && (
        <mesh position={[0, 1, 0]}>
          <cylinderGeometry args={[0.55, 0.65, 2.1, 16]} />
          <meshBasicMaterial color="#ff5a36" transparent opacity={0.2} wireframe />
        </mesh>
      )}
    </group>
  );
};

/** 变压器 3D 模型 */
const TransformerModel: React.FC<{
  statusColors: typeof STATUS_COLORS.online;
  intensity: number;
  isSelected: boolean;
}> = ({ statusColors, intensity, isSelected }) => (
  <group>
    <mesh position={[0, 0.8, 0]} castShadow>
      <cylinderGeometry args={[0.8, 1, 1.6, 8]} />
      <meshStandardMaterial
        color={isSelected ? '#ff5a36' : statusColors.body}
        emissive={statusColors.emissive}
        emissiveIntensity={intensity}
        metalness={0.85}
        roughness={0.15}
      />
    </mesh>
    {Array.from({ length: 6 }).map((_, i) => {
      const angle = (i * Math.PI * 2) / 6;
      return (
        <mesh key={`cool-${i}`} position={[Math.cos(angle) * 1.1, 0.8, Math.sin(angle) * 1.1]} castShadow>
          <boxGeometry args={[0.15, 1.4, 0.4]} />
          <meshStandardMaterial color="#777" metalness={0.85} roughness={0.15} />
        </mesh>
      );
    })}
    {Array.from({ length: 3 }).map((_, i) => (
      <mesh key={`ins-${i}`} position={[-0.4 + i * 0.4, 1.7, 0]} castShadow>
        <cylinderGeometry args={[0.08, 0.08, 0.3, 8]} />
        <meshStandardMaterial color="#ddd" metalness={0.3} roughness={0.7} />
      </mesh>
    ))}
    {isSelected && (
      <mesh position={[0, 0.8, 0]}>
        <cylinderGeometry args={[1.2, 1.2, 1.8, 8]} />
        <meshBasicMaterial color="#ff5a36" transparent opacity={0.2} wireframe />
      </mesh>
    )}
  </group>
);

/** 电表 3D 模型 */
const MeterModel: React.FC<{
  statusColors: typeof STATUS_COLORS.online;
  intensity: number;
  isSelected: boolean;
}> = ({ statusColors, intensity, isSelected }) => (
  <group>
    <mesh position={[0, 0.6, 0]} castShadow>
      <boxGeometry args={[0.8, 1.2, 0.3]} />
      <meshStandardMaterial
        color={isSelected ? '#ff5a36' : statusColors.body}
        emissive={statusColors.emissive}
        emissiveIntensity={intensity}
        metalness={0.6}
        roughness={0.4}
      />
    </mesh>
    <mesh position={[0, 0.7, 0.16]}>
      <boxGeometry args={[0.6, 0.4, 0.02]} />
      <meshStandardMaterial color="#111" metalness={0.95} roughness={0.05} />
    </mesh>
    <mesh position={[0, 0.3, 0.16]}>
      <cylinderGeometry args={[0.06, 0.06, 0.02, 16]} />
      <meshStandardMaterial color="#f5a623" emissive="#f5a623" emissiveIntensity={0.3} />
    </mesh>
    {isSelected && (
      <mesh position={[0, 0.6, 0]}>
        <boxGeometry args={[1, 1.4, 0.5]} />
        <meshBasicMaterial color="#ff5a36" transparent opacity={0.2} wireframe />
      </mesh>
    )}
  </group>
);

// ==================== 设备标签 ====================
const DeviceLabel: React.FC<{
  name: string;
  status: string;
  position: [number, number, number];
  realtimeData?: any;
}> = ({ name, status, position, realtimeData }) => {
  const statusColor =
    status === 'online' ? '#34a853' :
    status === 'warning' || status === 'alarm' ? '#f5a623' :
    status === 'fault' ? '#ea4335' :
    status === 'charging' ? '#fa8c16' : '#a6a1a0';

  const statusText =
    status === 'online' ? '在线' :
    status === 'warning' || status === 'alarm' ? '告警' :
    status === 'fault' ? '故障' :
    status === 'charging' ? '充电中' :
    status === 'maintenance' ? '维护中' : '离线';

  return (
    <Html position={position} center distanceFactor={15}>
      <div style={{
        background: 'rgba(0, 0, 0, 0.85)',
        color: '#fff',
        padding: '4px 12px',
        borderRadius: '4px',
        fontSize: '11px',
        whiteSpace: 'nowrap',
        border: '1px solid rgba(255,255,255,0.1)',
        pointerEvents: 'none',
        backdropFilter: 'blur(4px)',
      }}>
        <div style={{ fontWeight: 'bold', marginBottom: '2px' }}>{name}</div>
        <div style={{ color: statusColor, fontSize: '10px' }}>{statusText}</div>
        {realtimeData?.power_kw !== undefined && (
          <div style={{ color: '#ddd', fontSize: '10px', marginTop: 2 }}>
            {realtimeData.power_kw.toFixed(1)} kW
            {realtimeData.temperature_c !== undefined && (
              <> | {realtimeData.temperature_c.toFixed(1)}°C</>
            )}
          </div>
        )}
      </div>
    </Html>
  );
};

// ==================== 主组件 ====================
interface Device3DModelProps {
  device: {
    id: number;
    name: string;
    type: string;
    status: string;
    health_score: number;
    location?: string;
  };
  position: [number, number, number];
  isSelected: boolean;
  onSelect: (id: number) => void;
  realtimeData?: any;
  showLabels?: boolean;
}

export const Device3DModel: React.FC<Device3DModelProps> = ({
  device,
  position,
  isSelected,
  onSelect,
  realtimeData,
  showLabels = true,
}) => {
  const [hovered, setHovered] = useState(false);

  // 从实时数据提取关键指标
  const statusColors = getStatusColors(device.status);
  const powerKw = realtimeData?.power_kw ?? 0;
  const tempC = realtimeData?.temperature_c ?? 25;
  const isFault = device.status === 'fault';
  const isCharging = device.status === 'charging';

  // 计算视觉参数
  const intensity = powerIntensity(powerKw);
  const tempColor = temperatureColor(tempC);
  const socPercent = realtimeData?.metrics?.soc ?? 75; // 默认75%电量

  const renderDeviceModel = () => {
    const active = isSelected || hovered;
    switch (device.type) {
      case 'inverter':
        return <InverterModel statusColors={statusColors} intensity={intensity} isSelected={active} />;
      case 'pv_panel':
        return <PVPanelModel statusColors={statusColors} intensity={intensity} isSelected={active} />;
      case 'battery':
        return <BatteryModel statusColors={statusColors} intensity={intensity} isSelected={active} tempColor={tempColor} socPercent={socPercent} />;
      case 'charger':
        return <ChargerModel statusColors={statusColors} intensity={intensity} isSelected={active} isCharging={isCharging} />;
      case 'transformer':
        return <TransformerModel statusColors={statusColors} intensity={intensity} isSelected={active} />;
      case 'meter':
        return <MeterModel statusColors={statusColors} intensity={intensity} isSelected={active} />;
      default:
        return (
          <mesh position={[0, 0.5, 0]} castShadow>
            <boxGeometry args={[1, 1, 1]} />
            <meshStandardMaterial
              color={active ? '#ff5a36' : statusColors.body}
              emissive={statusColors.emissive}
              emissiveIntensity={intensity}
              metalness={0.6}
              roughness={0.4}
            />
          </mesh>
        );
    }
  };

  return (
    <group
      position={position}
      onClick={(e) => {
        e.stopPropagation();
        onSelect(device.id);
      }}
      onPointerOver={() => { setHovered(true); document.body.style.cursor = 'pointer'; }}
      onPointerOut={() => { setHovered(false); document.body.style.cursor = 'auto'; }}
    >
      <FaultBlink isFault={isFault}>
        <FloatingAnimation active={device.status === 'online' || isCharging} speed={1.2} amplitude={0.015}>
          {renderDeviceModel()}
        </FloatingAnimation>
      </FaultBlink>

      {/* 在线/充电设备旋转光环 */}
      {(device.status === 'online' || isCharging) && (
        <RotatingRing color={statusColors.ring} radius={1.5} speed={isCharging ? 3 : 2} />
      )}

      {/* 充电脉冲 */}
      <ChargingPulse isCharging={isCharging} color={statusColors.body} />

      {/* 设备标签 */}
      {showLabels && (
        <DeviceLabel
          name={device.name}
          status={device.status}
          position={[0, 2.5, 0]}
          realtimeData={realtimeData}
        />
      )}
    </group>
  );
};

export default Device3DModel;
