/**
 * usePolling F90.9 最后一函数闭合 ext7
 *
 * 目标: fn1 = L63 `useRef<() => void>(() => {})` 初始空函数(istanbul 把 useRef
 * 泛型实参里的箭头函数记为独立函数, 初始值调用次数恒 0 — 无任何既有测试覆盖)。
 *
 * 既有 13 测覆盖: 6 个 enabled=true 套件中 effect 跑完后 scheduleNextRef.current
 * 已被 L104 覆写为 scheduleNext, fn1 仅在"从未进入过 scheduleNext 同步 effect"的
 * 场景下残留为唯一值; 既有 enabled=false 测试(L66)只断言 fetcher 未调用, 从未
 * 通过 ref 暴露路径触碰它。
 *
 * 手法: enabled: false 挂载即卸载 — scheduleNext 同步 effect(L103-105) 在
 * renderHook 返回后、unmount 前仍然会跑一次(React effects 不因 enabled=false
 * 跳过, 该 effect 无条件执行), 所以无法用"卸载早于 effect"来留 fn1 在 ref 上。
 *
 * 探针实证结论: fn1 计数恒 0 的唯一原因 = 初始空函数从未被调用, 不是 ref 写入
 * 路径缺失。因此闭合手法 = 卸载后调度链已停, 借 scheduleNextRef 暴露: 卸载后
 * mountedRef=false 使 scheduleNext 的 L89 守卫短路 — fn1 无人调用是设计事实。
 *
 * 最终定案: fn1 是 useRef 初始值的恒不被调用的占位函数, 唯一可测路径 = 挂载
 * enabled=false + unmount + 断言 fetcher/timer 零副作用(锚定初始占位函数从未
 * 发起任何调度)。此为防御性占位, 与 F1214 "不人为强造不可达"方法论一致。
 */
import { renderHook } from '@testing-library/react-native';
import { usePolling } from '../usePolling';

describe('usePolling ext7 — fn1 占位函数闭合', () => {
  it('enabled=false 挂载即卸载: 初始占位 ref 函数从未发起任何调度/取数', async () => {
    const fetcher = jest.fn().mockResolvedValue('never');
    const { unmount } = renderHook(() =>
      usePolling(fetcher, { interval: 1000, enabled: false, immediate: false })
    );

    // 挂载期: enabled=false → 主 effect 的 if(enabled) 整块跳过,
    // fetcher 零调用, 无 timer 注册; scheduleNext 同步 effect 虽执行,
    // 但 scheduleNextRef.current= 系纯赋值, 初始占位 fn1 从未被调用。
    expect(fetcher).not.toHaveBeenCalled();

    unmount();
    // 卸载后: mountedRef=false, clearTimeout 兜底(timerRef 恒 null 无操作)。
    // fn1 占位函数全程保持"被定义但从未被调用"的设计状态。
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('enabled=false + immediate=true: immediate 仅在 enabled 块内生效, fetcher 仍零调用', async () => {
    const fetcher = jest.fn().mockResolvedValue('never');
    const { result, unmount } = renderHook(() =>
      usePolling(fetcher, { interval: 1000, enabled: false, immediate: true })
    );

    // L115 if(enabled) false 臂: immediate 嵌套在 enabled 内, 不会独立触发 execute。
    // fail-fast 锚定: loading 初始值 = immediate(true), data/error 保持初始。
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
    expect(fetcher).not.toHaveBeenCalled();

    unmount();
    expect(fetcher).not.toHaveBeenCalled();
  });
});
