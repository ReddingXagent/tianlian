import { renderHook, act, waitFor } from '@testing-library/react-native';
import { vehicleApi } from '../../services/api';
import { useVehicles } from '../useVehicles';
import { Vehicle } from '../../types';

jest.mock('../../services/api', () => ({
  vehicleApi: {
    getList: jest.fn(),
    add: jest.fn(),
    remove: jest.fn(),
    setDefault: jest.fn(),
  },
}));

const mockVehicle = (id: number): Vehicle => ({
  id,
  plate: `京A${id}`,
  brand: '特斯拉',
  model: 'Model 3',
  color: '白色',
  vin: 'VIN123',
  isDefault: id === 1,
} as never);

describe('useVehicles', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should load vehicles on mount', async () => {
    (vehicleApi.getList as jest.Mock).mockResolvedValue({
      data: [mockVehicle(1), mockVehicle(2)],
    });

    const { result } = renderHook(() => useVehicles());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.vehicles).toHaveLength(2);
    expect(result.current.error).toBeNull();
  });

  it('should set error on load failure', async () => {
    (vehicleApi.getList as jest.Mock).mockRejectedValue(new Error('服务器错误'));

    const { result } = renderHook(() => useVehicles());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('服务器错误');
  });

  it('should set default error on non-Error throw', async () => {
    (vehicleApi.getList as jest.Mock).mockRejectedValue('fail');

    const { result } = renderHook(() => useVehicles());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('获取车辆列表失败');
  });

  it('should handle refresh', async () => {
    (vehicleApi.getList as jest.Mock).mockResolvedValue({ data: [mockVehicle(1)] });

    const { result } = renderHook(() => useVehicles());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    (vehicleApi.getList as jest.Mock).mockResolvedValue({ data: [mockVehicle(2)] });

    await act(async () => {
      await result.current.handleRefresh();
    });

    expect(result.current.refreshing).toBe(false);
    expect(result.current.vehicles[0].id).toBe(2);
  });

  it('should add vehicle successfully', async () => {
    (vehicleApi.getList as jest.Mock).mockResolvedValue({ data: [] });
    (vehicleApi.add as jest.Mock).mockResolvedValue({});

    const { result } = renderHook(() => useVehicles());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    let addResult: { success: boolean } | undefined;
    await act(async () => {
      addResult = await result.current.addVehicle({
        plate: '京B123',
        brand: '比亚迪',
        model: '汉EV',
        color: '黑色',
        vin: 'VIN456',
        isDefault: false,
      });
    });

    expect(addResult?.success).toBe(true);
    expect(vehicleApi.add).toHaveBeenCalled();
    expect(vehicleApi.getList).toHaveBeenCalledTimes(2); // initial + reload
  });

  it('should handle add vehicle axios error', async () => {
    (vehicleApi.getList as jest.Mock).mockResolvedValue({ data: [] });
    (vehicleApi.add as jest.Mock).mockRejectedValue({
      response: { data: { message: '车牌已存在' } },
    });

    const { result } = renderHook(() => useVehicles());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    let addResult: { success: boolean; errorMessage?: string } | undefined;
    await act(async () => {
      addResult = await result.current.addVehicle({
        plate: '京B123',
        brand: '比亚迪',
        model: '汉EV',
        color: '黑色',
        vin: 'VIN456',
        isDefault: false,
      });
    });

    expect(addResult?.success).toBe(false);
    expect(addResult?.errorMessage).toBe('车牌已存在');
  });

  it('should handle add vehicle network error', async () => {
    (vehicleApi.getList as jest.Mock).mockResolvedValue({ data: [] });
    (vehicleApi.add as jest.Mock).mockRejectedValue(new Error('Network'));

    const { result } = renderHook(() => useVehicles());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    let addResult: { success: boolean; isNetworkError?: boolean } | undefined;
    await act(async () => {
      addResult = await result.current.addVehicle({
        plate: '京B123',
        brand: '比亚迪',
        model: '汉EV',
        color: '黑色',
        vin: 'VIN456',
        isDefault: false,
      });
    });

    expect(addResult?.success).toBe(false);
    expect(addResult?.isNetworkError).toBe(true);
  });

  it('should remove vehicle successfully', async () => {
    (vehicleApi.getList as jest.Mock).mockResolvedValue({ data: [mockVehicle(1)] });
    (vehicleApi.remove as jest.Mock).mockResolvedValue({});

    const { result } = renderHook(() => useVehicles());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    let removeResult: boolean;
    await act(async () => {
      removeResult = await result.current.removeVehicle(1);
    });

    expect(removeResult).toBe(true);
    expect(vehicleApi.remove).toHaveBeenCalledWith(1);
  });

  it('should handle remove vehicle failure', async () => {
    (vehicleApi.getList as jest.Mock).mockResolvedValue({ data: [mockVehicle(1)] });
    (vehicleApi.remove as jest.Mock).mockRejectedValue(new Error('fail'));

    const { result } = renderHook(() => useVehicles());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    let removeResult: boolean;
    await act(async () => {
      removeResult = await result.current.removeVehicle(1);
    });

    expect(removeResult).toBe(false);
  });

  it('should set default vehicle successfully', async () => {
    (vehicleApi.getList as jest.Mock).mockResolvedValue({ data: [mockVehicle(1), mockVehicle(2)] });
    (vehicleApi.setDefault as jest.Mock).mockResolvedValue({});

    const { result } = renderHook(() => useVehicles());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    let setResult: boolean;
    await act(async () => {
      setResult = await result.current.setDefaultVehicle(2);
    });

    expect(setResult).toBe(true);
    expect(vehicleApi.setDefault).toHaveBeenCalledWith(2);
  });

  it('should handle set default failure', async () => {
    (vehicleApi.getList as jest.Mock).mockResolvedValue({ data: [mockVehicle(1)] });
    (vehicleApi.setDefault as jest.Mock).mockRejectedValue(new Error('fail'));

    const { result } = renderHook(() => useVehicles());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    let setResult: boolean;
    await act(async () => {
      setResult = await result.current.setDefaultVehicle(1);
    });

    expect(setResult).toBe(false);
  });
});
