import React from 'react';
import { render } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import ProfileScreen from '../ProfileScreen';

// --- mocks ---
const mockGetUserStats = jest.fn();
const mockGetProfile = jest.fn();

jest.mock('../../services/api', () => ({
  statsApi: { getUserStats: (...args: unknown[]) => mockGetUserStats(...args) },
  authApi: { getProfile: (...args: unknown[]) => mockGetProfile(...args) },
}));

const mockNavigate = jest.fn();

jest.mock('../../store/authStore', () => ({
  useAuthStore: () => ({
    user: null, // null user → test fallback branches
    logout: jest.fn().mockResolvedValue(undefined),
    setUser: jest.fn(),
  }),
}));

let mockFocused = true;
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
  useIsFocused: () => mockFocused,
}));

describe('ProfileScreen.ext2 — user=null branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFocused = true;
    mockGetUserStats.mockResolvedValue({ data: {} });
    mockGetProfile.mockResolvedValue({ data: null });
  });

  const renderScreen = () =>
    render(<SafeAreaProvider><ProfileScreen /></SafeAreaProvider>);

  // Line 87: user?.nickname?.charAt(0) || user?.phone?.charAt(0) || '?'
  // With user=null: all optional chains undefined → '?' fallback
  it('shows ? avatar when user is null', () => {
    const { getByText } = renderScreen();
    // Avatar text is '?'
    expect(getByText('?')).toBeTruthy();
  });

  // Line 89: user?.nickname || '用户' → '用户' when null
  it('shows default nickname when user is null', () => {
    const { getByText } = renderScreen();
    expect(getByText('用户')).toBeTruthy();
  });

  // Line 90: user?.phone → undefined when null, phone renders empty
  it('renders without crash when user phone is null', () => {
    const { getByText } = renderScreen();
    expect(getByText('余额')).toBeTruthy();
  });

  // Line 94: user?.balance || 0 → 0 when null
  it('shows balance 0 when user is null', () => {
    const { getByText } = renderScreen();
    expect(getByText('¥0.00')).toBeTruthy();
  });
});
