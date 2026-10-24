/**
 * useFleetRealtime Hook 测试
 *
 * 核心验证：WS 连接 + 断连自动降级轮询
 * - 未连接 → polling 模式，定时调用 pollFn
 * - 连接成功 → realtime 模式，停止轮询
 * - 断连恢复 → 重启轮询
 * - 收到 WS 数据 → 触发 onData
 * - enabled=false → idle，不连接不轮询
 */
import { renderHook, act } from '@testing-library/react';
import { useFleetRealtime } from '../useFleetRealtime';

vi.mock('../../config/websocket', () => ({
  WS_CONFIG: {
    reconnectInterval: 100,
    maxReconnectAttempts: 5,
    heartbeatInterval: 100000,
    connectionTimeout: 10,
  },
  WSMessage: {} as any,
  WSConnectionState: '' as any,
  WSChannelType: '' as any,
  WS_ENDPOINTS: { dashboard: 'ws://test/dashboard' },
}));

let lastCreatedWsMock: any = null;

function createWsMock(): any {
  return {
    readyState: 1,
    onopen: null as ((e?: Event) => void) | null,
    onmessage: null as ((e: { data: string }) => void) | null,
    onerror: null as ((e: Event) => void) | null,
    onclose: null as ((e: CloseEvent) => void) | null,
    send: vi.fn(),
    close: vi.fn(),
  };
}

const MockWebSocketClass = function MockWebSocket(this: any, _url: string) {
  const instance = createWsMock();
  lastCreatedWsMock = instance;
  return instance;
} as any;
MockWebSocketClass.OPEN = 1;
MockWebSocketClass.CONNECTING = 0;

beforeEach(() => {
  vi.useFakeTimers();
  lastCreatedWsMock = null;
  (global as any).WebSocket = MockWebSocketClass;
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useFleetRealtime', () => {
  it('未连接时进入 polling 模式并定时轮询', () => {
    const pollFn = vi.fn();
    const { result } = renderHook(() =>
      useFleetRealtime({ endpoint: 'ws://test/fleet/queue/1', pollFn, pollIntervalMs: 1000 })
    );

    expect(result.current.mode).toBe('polling');

    act(() => { vi.advanceTimersByTime(1000); });
    expect(pollFn).toHaveBeenCalledTimes(1);

    act(() => { vi.advanceTimersByTime(1000); });
    expect(pollFn).toHaveBeenCalledTimes(2);
  });

  it('连接成功后切换到 realtime 模式并停止轮询', () => {
    const pollFn = vi.fn();
    const { result } = renderHook(() =>
      useFleetRealtime({ endpoint: 'ws://test/fleet/queue/1', pollFn, pollIntervalMs: 1000 })
    );

    act(() => { vi.advanceTimersByTime(2000); });
    const callsBefore = pollFn.mock.calls.length;
    expect(callsBefore).toBeGreaterThanOrEqual(1);

    // 触发 WS 连接成功
    act(() => { if (lastCreatedWsMock?.onopen) lastCreatedWsMock.onopen(); });

    expect(result.current.mode).toBe('realtime');

    // 推进时间，轮询不再触发
    act(() => { vi.advanceTimersByTime(5000); });
    expect(pollFn.mock.calls.length).toBe(callsBefore);
  });

  it('断连后回退到 polling 模式', () => {
    const pollFn = vi.fn();
    const { result } = renderHook(() =>
      useFleetRealtime({ endpoint: 'ws://test/fleet/queue/1', pollFn, pollIntervalMs: 1000 })
    );

    // 先连上
    act(() => { if (lastCreatedWsMock?.onopen) lastCreatedWsMock.onopen(); });
    expect(result.current.mode).toBe('realtime');

    const callsBefore = pollFn.mock.calls.length;

    // 断连
    act(() => {
      if (lastCreatedWsMock?.onclose) lastCreatedWsMock.onclose({ code: 1006, reason: 'abnormal', wasClean: false } as CloseEvent);
    });

    expect(result.current.mode).toBe('polling');

    act(() => { vi.advanceTimersByTime(1000); });
    expect(pollFn.mock.calls.length).toBeGreaterThan(callsBefore);
  });

  it('收到 WS 数据消息时触发 onData', () => {
    const onData = vi.fn();
    renderHook(() =>
      useFleetRealtime({ endpoint: 'ws://test/fleet/queue/1', pollFn: vi.fn(), onData })
    );

    act(() => { if (lastCreatedWsMock?.onopen) lastCreatedWsMock.onopen(); });

    const dataMessage = {
      type: 'data',
      channel: 'fleet_queue',
      payload: { total: 5, waiting_count: 3 },
      timestamp: '2026-07-24T00:00:00Z',
    };

    act(() => {
      if (lastCreatedWsMock?.onmessage) lastCreatedWsMock.onmessage({ data: JSON.stringify(dataMessage) });
    });

    expect(onData).toHaveBeenCalledWith(dataMessage.payload);
  });

  it('enabled=false 时不连接不轮询 (idle)', () => {
    const pollFn = vi.fn();
    const { result } = renderHook(() =>
      useFleetRealtime({ endpoint: 'ws://test/fleet/queue/1', pollFn, pollIntervalMs: 1000, enabled: false })
    );

    expect(result.current.mode).toBe('idle');
    expect(lastCreatedWsMock).toBeNull();

    act(() => { vi.advanceTimersByTime(5000); });
    expect(pollFn).not.toHaveBeenCalled();
  });
});
