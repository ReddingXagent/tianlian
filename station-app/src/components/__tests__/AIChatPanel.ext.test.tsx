/**
 * AIChatPanel.ext — Platform.OS android branch coverage
 * L207/212: Platform.OS === 'ios' ? 'Menlo' : 'monospace' — cover android branch
 * L442/451: if (updated[lastIdx]?.id === assistantMsgId) false branch — id mismatch
 */
import { Platform } from 'react-native';

// Mock Platform.OS to 'android' before module import
jest.mock('react-native/Libraries/Utilities/Platform', () => ({
  OS: 'android',
  select: (obj: Record<string, unknown>) => obj.android || obj.default,
}));

jest.mock('../../services/ai', () => ({
  chat: jest.fn(),
}));

/* eslint-disable import/first -- jest.mock 必须先于被测模块 import (hoist 语义) */
import { AIChatPanel } from '../AIChatPanel';
import { chat } from '../../services/ai';
import { render, fireEvent, act, waitFor } from '@testing-library/react-native';
import React from 'react';

describe('AIChatPanel.ext', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders with Platform.OS=android (monospace font branch)', () => {
    const { getByPlaceholderText } = render(<AIChatPanel />);
    expect(getByPlaceholderText('输入你的问题…')).toBeTruthy();
  });

  it('completes chat flow successfully', async () => {
    (chat as jest.Mock).mockImplementation(({ onChunk }) => {
      // Simulate streaming chunks
      if (onChunk) onChunk('hello');
      return Promise.resolve({ content: 'hello world', role: 'assistant' });
    });

    const { getByPlaceholderText, getByText } = render(<AIChatPanel />);
    
    fireEvent.changeText(getByPlaceholderText('输入你的问题…'), 'test');
    await act(async () => {
      fireEvent.press(getByText('↑'));
    });

    await waitFor(() => {
      expect(chat).toHaveBeenCalled();
    });
  });

  it('handles chat error', async () => {
    (chat as jest.Mock).mockRejectedValue(new Error('network'));

    const { getByPlaceholderText, getByText } = render(<AIChatPanel />);
    
    fireEvent.changeText(getByPlaceholderText('输入你的问题…'), 'test');
    await act(async () => {
      fireEvent.press(getByText('↑'));
    });

    await waitFor(() => {
      expect(chat).toHaveBeenCalled();
    });
  });
});
