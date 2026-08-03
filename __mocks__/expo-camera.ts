import React from 'react';
import { View } from 'react-native';

/**
 * expo-camera jest mock(默认权限已授予)。
 * 需要控制权限状态或模拟扫描的测试, 在测试文件内用 jest.mock('expo-camera', factory) 覆盖。
 */
export const CameraView = (props: React.PropsWithChildren<Record<string, unknown>>) =>
  React.createElement(View, { testID: 'mock-camera-view' }, props.children);

export const useCameraPermissions = (): [
  { status: string; granted: boolean; canAskAgain: boolean },
  () => Promise<{ status: string; granted: boolean; canAskAgain: boolean }>,
] => [
  { status: 'granted', granted: true, canAskAgain: true },
  () => Promise.resolve({ status: 'granted', granted: true, canAskAgain: true }),
];
