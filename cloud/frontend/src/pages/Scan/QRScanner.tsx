/**
 * 摄像头二维码扫描器组件
 * 使用 jsQR 库进行二维码识别
 */
import React, { useRef, useEffect, useState } from 'react';
import { Button, Typography, Space, message } from 'antd';
import { CameraOutlined, ReloadOutlined } from '@ant-design/icons';
import jsQR from 'jsqr';

const { Text } = Typography;

interface QRScannerProps {
  onScan: (qrCode: string) => void;
  onError?: (error: string) => void;
}

const QRScanner: React.FC<QRScannerProps> = ({ onScan, onError }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState('');
  const animationRef = useRef<number>();

  useEffect(() => {
    if (scanning) {
      startCamera();
    } else {
      stopCamera();
    }
    // Cleanup on unmount
    return () => {
      stopCamera();
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [scanning]);

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' }
      });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        scanQRCode();
      }
    } catch (err) {
      const errorMsg = '无法访问摄像头，请检查权限或使用手动输入';
      setError(errorMsg);
      onError?.(errorMsg);
    }
  };

  const stopCamera = () => {
    if (videoRef.current?.srcObject) {
      const stream = videoRef.current.srcObject as MediaStream;
      stream.getTracks().forEach(track => track.stop());
      videoRef.current.srcObject = null;
    }
  };

  const scanQRCode = () => {
    if (!videoRef.current || !canvasRef.current || !scanning) return;

    const video = videoRef.current;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');

    if (!ctx || video.readyState !== video.HAVE_ENOUGH_DATA) {
      // 等待视频准备好
      animationRef.current = requestAnimationFrame(scanQRCode);
      return;
    }

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    
    // 使用 jsQR 库识别二维码
    const code = jsQR(imageData.data, imageData.width, imageData.height);
    
    if (code) {
      // 找到二维码
      onScan(code.data);
      setScanning(false);
      message.success('二维码识别成功！');
      return;
    }

    // 继续扫描
    animationRef.current = requestAnimationFrame(scanQRCode);
  };

  return (
    <div>
      <Space direction="vertical" style={{ width: '100%' }}>
        <Button
          type="primary"
          icon={<CameraOutlined />}
          block
          onClick={() => setScanning(!scanning)}
        >
          {scanning ? '停止扫描' : '开始扫描'}
        </Button>

        {error && <Text type="danger">{error}</Text>}

        {scanning && (
          <div style={{ position: 'relative' }}>
            <video
              ref={videoRef}
              style={{
                width: '100%',
                borderRadius: 8,
                background: '#000'
              }}
              autoPlay
              playsInline
            />
            <canvas
              ref={canvasRef}
              style={{ display: 'none' }}
            />
            {/* 扫码框 */}
            <div
              style={{
                position: 'absolute',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                width: '60%',
                height: '60%',
                border: '2px solid #ff5a36',
                borderRadius: 8,
                boxShadow: '0 0 0 2000px rgba(0,0,0,0.3)'
              }}
            />
          </div>
        )}

        {/* 测试按钮（模拟扫码） */}
        {scanning && (
          <Button
            type="dashed"
            onClick={() => {
              onScan('TL-DEV001');
              setScanning(false);
              stopCamera();
            }}
            block
            style={{ marginTop: 8 }}
          >
            模拟扫码（测试用）
          </Button>
        )}
      </Space>
    </div>
  );
};

export default QRScanner;