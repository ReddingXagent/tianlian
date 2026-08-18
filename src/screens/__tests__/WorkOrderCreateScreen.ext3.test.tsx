/**
 * WorkOrderCreateScreen coverage test — targets Platform.OS ternary branch
 * F1451: WorkOrderCreateScreen.tsx branches 95.23%→100%
 */
import React from 'react';
import { Platform } from 'react-native';
import { render } from '@testing-library/react-native';

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: {} }),
  useNavigation: () => ({ navigate: jest.fn() }),
}));

jest.mock('../../hooks/useWorkOrderCreate', () => ({
  useWorkOrderCreate: jest.fn(() => ({
    form: { type: 'repair', priority: 'medium', stationId: '', deviceId: '', description: '' },
    errors: {},
    submitting: false,
    setField: jest.fn(),
    handleSubmit: jest.fn(),
    resetForm: jest.fn(),
  })),
}));

import WorkOrderCreateScreen from '../WorkOrderCreateScreen';

describe('WorkOrderCreateScreen — Platform.OS !== ios branch', () => {
  it('renders with Platform.OS=android (behavior=height)', () => {
    const originalOS = Platform.OS;
    // @ts-ignore — intentionally overriding for test
    Platform.OS = 'android';
    try {
      const { getByText } = render(<WorkOrderCreateScreen />);
      // Screen renders successfully with behavior="height"
      expect(getByText('工单类型')).toBeTruthy();
    } finally {
      // @ts-ignore
      Platform.OS = originalOS;
    }
  });
});
