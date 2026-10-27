/**
 * ProfileScreen ext — unknown role fallback (line 38)
 * map[role] || role — when role is not in the map
 */
import { render } from '@testing-library/react-native';
import ProfileScreen from '../ProfileScreen';
import { useAuthStore } from '../../store/authStore';

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: jest.fn() }),
}));

jest.mock('../../store/authStore', () => ({
  useAuthStore: jest.fn(),
}));

const mockLogout = jest.fn();

describe('ProfileScreen.ext unknown role', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockLogout.mockResolvedValue(undefined);
  });

  it('shows raw role string when role is not in map', () => {
    (useAuthStore as unknown as jest.Mock).mockReturnValue({
      user: {
        id: 1, username: 'test', nickname: '测试用户', email: '', phone: '',
        role: 'supervisor', // not in map → should display raw 'supervisor'
        stationIds: [], createdAt: '', updatedAt: '',
      },
      logout: mockLogout,
    });
    const { getByText } = render(<ProfileScreen />);
    expect(getByText('supervisor')).toBeTruthy();
  });
});
