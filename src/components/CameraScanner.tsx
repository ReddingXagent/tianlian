import React, { useCallback, useRef } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Linking } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { parseScanPayload } from '../utils/scanCode';

interface CameraScannerProps {
  /** 扫到并解析成功后回调(已冷却去重) */
  onScan: (code: string) => void;
  /** 关闭相机 */
  onClose: () => void;
}

/** 同一编码冷却窗口: 二维码持续在取景框内会连续触发, 只认第一次 */
const SCAN_COOLDOWN_MS = 2500;

const CameraScanner: React.FC<CameraScannerProps> = ({ onScan, onClose }) => {
  const [permission, requestPermission] = useCameraPermissions();
  const lastScanRef = useRef<{ code: string; at: number }>({ code: '', at: 0 });

  const handleBarCodeScanned = useCallback(
    ({ data }: { data: string }) => {
      const code = parseScanPayload(data);
      if (!code) return;
      const now = Date.now();
      const last = lastScanRef.current;
      if (last.code === code && now - last.at < SCAN_COOLDOWN_MS) return;
      lastScanRef.current = { code, at: now };
      onScan(code);
    },
    [onScan]
  );

  // 权限状态还在加载
  if (!permission) return null;

  if (!permission.granted) {
    return (
      <View style={styles.permissionBox} testID="camera-permission-box">
        <Text style={styles.permissionText}>需要相机权限才能扫码</Text>
        {permission.canAskAgain ? (
          <TouchableOpacity accessibilityRole="button"
            style={styles.permissionBtn}
            onPress={requestPermission}
            testID="camera-request-btn"
          >
            <Text style={styles.permissionBtnText}>授予权限</Text>
          </TouchableOpacity>
        ) : (
          <TouchableOpacity accessibilityRole="button"
            style={styles.permissionBtn}
            onPress={() => Linking.openSettings()}
            testID="camera-settings-btn"
          >
            <Text style={styles.permissionBtnText}>去设置开启</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity accessibilityRole="button" onPress={onClose} testID="camera-cancel-btn">
          <Text style={styles.cancelText}>取消</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.cameraContainer} testID="camera-view">
      <CameraView
        style={styles.camera}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
        onBarcodeScanned={handleBarCodeScanned}
      />
      <View style={styles.overlayHint}>
        <Text style={styles.overlayHintText}>对准充电桩二维码</Text>
      </View>
      <TouchableOpacity
        accessibilityRole="button"
        accessibilityLabel="关闭扫码"
        style={styles.closeBtn}
        onPress={onClose}
        testID="camera-close-btn"
      >
        <Text style={styles.closeBtnText}>✕ 关闭</Text>
      </TouchableOpacity>
    </View>
  );
};

const styles = StyleSheet.create({
  cameraContainer: {
    width: 240,
    height: 200,
    borderRadius: 16,
    overflow: 'hidden',
    backgroundColor: '#000',
  },
  camera: {
    flex: 1,
  },
  overlayHint: {
    position: 'absolute',
    bottom: 8,
    alignSelf: 'center',
    backgroundColor: 'rgba(0,0,0,0.55)',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  overlayHintText: {
    color: '#fff',
    fontSize: 12,
  },
  closeBtn: {
    position: 'absolute',
    top: 8,
    right: 8,
    backgroundColor: 'rgba(0,0,0,0.55)',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  closeBtnText: {
    color: '#fff',
    fontSize: 12,
  },
  permissionBox: {
    width: 240,
    height: 200,
    borderWidth: 2,
    borderColor: '#1a73e8',
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(26, 115, 232, 0.05)',
    padding: 16,
  },
  permissionText: {
    fontSize: 13,
    color: '#333',
    marginBottom: 12,
    textAlign: 'center',
  },
  permissionBtn: {
    backgroundColor: '#1a73e8',
    borderRadius: 8,
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  permissionBtnText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  cancelText: {
    marginTop: 12,
    fontSize: 13,
    color: '#999',
  },
});

export default CameraScanner;
