/**
 * DigitalTwinCanvas - 纯 R3F 声明式 3D 画布
 * 使用 @react-three/fiber Canvas + @react-three/drei 辅助组件
 */
import React, { useRef, useMemo, useCallback, useEffect } from 'react';
import { Canvas, useThree, useFrame } from '@react-three/fiber';
import {
  OrbitControls,
  Grid,
  Environment,
  ContactShadows,
  Html,
} from '@react-three/drei';
import * as THREE from 'three';
import { Device3DModel } from './Device3DModel';

// ==================== 类型定义 ====================
interface DeviceItem {
  device: {
    id: number;
    name: string;
    type: string;
    status: string;
    health_score: number;
    model?: string;
    location?: string;
    last_heartbeat?: string;
    total_run_hours?: number;
    total_generation_kwh?: number;
    total_charge_kwh?: number;
  };
  digital_twin_config?: {
    id: number;
    model_type: string;
    scale_x: number;
    scale_y: number;
    scale_z: number;
    position_x: number;
    position_y: number;
    position_z: number;
    color_primary: string;
    animations: Record<string, any>;
    status_mapping: Record<string, any>;
  };
}

interface DigitalTwinCanvasProps {
  station: any;
  scene: any;
  devices: DeviceItem[];
  selectedDeviceId: number | null;
  onDeviceSelect: (deviceId: number) => void;
  viewMode: 'overview' | 'first_person' | 'free';
  scale: number;
  realtimeData: any;
}

// ==================== 灯光设置 ====================
const SceneLights: React.FC<{ scene?: any }> = ({ scene }) => {
  const dirLightRef = useRef<THREE.DirectionalLight>(null!);

  return (
    <>
      <ambientLight intensity={0.4} color="#b0c4de" />
      <directionalLight
        ref={dirLightRef}
        position={[10, 20, 10]}
        intensity={1.2}
        color="#ffffff"
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
        shadow-camera-far={80}
        shadow-camera-near={0.5}
        shadow-camera-left={-25}
        shadow-camera-right={25}
        shadow-camera-top={25}
        shadow-camera-bottom={-25}
      />
      <pointLight position={[0, 15, 0]} intensity={0.3} color="#fef0ed" />
      <hemisphereLight args={['#87ceeb', '#333333', 0.3]} />
    </>
  );
};

// ==================== 地面 ====================
const Ground: React.FC = () => (
  <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]} receiveShadow>
    <planeGeometry args={[60, 60]} />
    <meshStandardMaterial
      color="#2a2a3e"
      roughness={0.9}
      metalness={0.1}
      transparent
      opacity={0.9}
    />
  </mesh>
);

// ==================== 设备网格布局 ====================
const DeviceLayout: React.FC<{
  devices: DeviceItem[];
  selectedDeviceId: number | null;
  onDeviceSelect: (id: number) => void;
  realtimeData: any;
}> = ({ devices, selectedDeviceId, onDeviceSelect, realtimeData }) => {
  // 根据设备数量自动布局
  const positions = useMemo(() => {
    const pos: [number, number, number][] = [];
    const cols = Math.min(devices.length, 4);
    const spacingX = 6;
    const spacingZ = 6;
    const offsetX = -(cols - 1) * spacingX / 2;

    devices.forEach((_, i) => {
      const row = Math.floor(i / cols);
      const col = i % cols;
      pos.push([
        offsetX + col * spacingX,
        0,
        row * spacingZ - 2,
      ]);
    });
    return pos;
  }, [devices.length]);

  return (
    <group>
      {devices.map((item, idx) => (
        <Device3DModel
          key={item.device.id}
          device={item.device}
          position={positions[idx] || [0, 0, 0]}
          isSelected={item.device.id === selectedDeviceId}
          onSelect={onDeviceSelect}
          realtimeData={realtimeData?.devices?.[item.device.id]}
          showLabels
        />
      ))}
    </group>
  );
};

// ==================== 相机控制器 ====================
const CameraController: React.FC<{
  viewMode: string;
  targetScale: number;
}> = ({ viewMode, targetScale }) => {
  const controlsRef = useRef<any>(null);

  const getCameraProps = () => {
    switch (viewMode) {
      case 'overview':
        return { position: [18, 14, 18] as [number, number, number], target: [0, 0, 0] as [number, number, number] };
      case 'first_person':
        return { position: [0, 2, 8] as [number, number, number], target: [0, 2, 0] as [number, number, number] };
      case 'free':
      default:
        return { position: [12, 10, 12] as [number, number, number], target: [0, 0, 0] as [number, number, number] };
    }
  };

  const camProps = getCameraProps();

  return (
    <OrbitControls
      ref={controlsRef}
      target={camProps.target}
      enableDamping
      dampingFactor={0.08}
      minDistance={3}
      maxDistance={60}
      maxPolarAngle={Math.PI / 2 + 0.1}
    />
  );
};

// ==================== 场景信息覆盖层 ====================
const SceneOverlay: React.FC<{
  station: any;
  deviceCount: number;
  onlineCount: number;
  warningCount: number;
  faultCount: number;
}> = ({ station, deviceCount, onlineCount, warningCount, faultCount }) => (
  <Html fullscreen position={[0, 0, 0]}>
    <div style={{
      position: 'absolute',
      top: 12,
      left: 12,
      background: 'rgba(0, 0, 0, 0.7)',
      borderRadius: 8,
      padding: '8px 14px',
      color: '#fff',
      fontSize: 12,
      pointerEvents: 'none',
      backdropFilter: 'blur(6px)',
    }}>
      <div style={{ fontWeight: 'bold', marginBottom: 4, fontSize: 14 }}>{station?.name || '站点'}</div>
      <div>设备: {deviceCount} | <span style={{ color: '#34a853' }}>在线: {onlineCount}</span> | <span style={{ color: '#f5a623' }}>告警: {warningCount}</span> | <span style={{ color: '#ea4335' }}>故障: {faultCount}</span></div>
    </div>
  </Html>
);

// ==================== 主画布组件 ====================
const DigitalTwinCanvas: React.FC<DigitalTwinCanvasProps> = ({
  station,
  scene,
  devices,
  selectedDeviceId,
  onDeviceSelect,
  viewMode,
  scale,
  realtimeData,
}) => {
  const onlineCount = devices.filter(d => d.device.status === 'online').length;
  const warningCount = devices.filter(d => d.device.status === 'warning' || d.device.status === 'alarm').length;
  const faultCount = devices.filter(d => d.device.status === 'fault').length;

  const handleCreated = useCallback((state: any) => {
    state.gl.shadowMap.enabled = true;
    state.gl.shadowMap.type = THREE.PCFSoftShadowMap;
    state.gl.toneMapping = THREE.ACESFilmicToneMapping;
    state.gl.toneMappingExposure = 1.2;
  }, []);

  if (!devices || devices.length === 0) {
    return (
      <div style={{
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#1e1918',
        borderRadius: 4,
        color: '#999',
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>🔌</div>
          <div>暂无设备数据，请先添加设备到站点</div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ height: '100%', width: '100%', background: '#1e1918', borderRadius: 4, overflow: 'hidden' }}>
      <Canvas
        shadows
        camera={{ position: [18, 14, 18], fov: 50, near: 0.1, far: 500 }}
        onCreated={handleCreated}
        gl={{ antialias: true, alpha: false }}
        style={{ background: 'linear-gradient(180deg, #151210 0%, #1e1918 50%, #252120 100%)' }}
      >
        {/* 灯光 */}
        <SceneLights scene={scene} />

        {/* 雾效 */}
        <fog attach="fog" args={['#1e1918', 25, 80]} />

        {/* 相机控制 */}
        <CameraController viewMode={viewMode} targetScale={scale} />

        {/* 地面 */}
        <Ground />

        {/* 网格辅助线 */}
        <Grid
          args={[50, 50]}
          cellSize={1}
          cellColor="#333355"
          sectionSize={5}
          sectionColor="#444466"
          fadeDistance={40}
          fadeStrength={1}
          position={[0, 0.01, 0]}
        />

        {/* 环境光贴图 */}
        <Environment preset="city" />

        {/* 接触阴影 */}
        <ContactShadows
          position={[0, -0.01, 0]}
          opacity={0.4}
          scale={30}
          blur={2}
          far={10}
        />

        {/* 缩放控制 */}
        <group scale={scale}>
          {/* 设备模型 */}
          <DeviceLayout
            devices={devices}
            selectedDeviceId={selectedDeviceId}
            onDeviceSelect={onDeviceSelect}
            realtimeData={realtimeData}
          />
        </group>

        {/* 场景信息 */}
        <SceneOverlay
          station={station}
          deviceCount={devices.length}
          onlineCount={onlineCount}
          warningCount={warningCount}
          faultCount={faultCount}
        />
      </Canvas>
    </div>
  );
};

export default DigitalTwinCanvas;
