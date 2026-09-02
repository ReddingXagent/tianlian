/**
 * usePolling 覆盖盲区补测 — F3684 (夜间冲刺档 v2)
 * 目标: L51 execute() 入口 mountedRef.current=false 早退分支
 * 触发路径: 卸载后调用 refresh() (refresh→execute→入口守卫早退, fetcher 不被调用)
 * (station-app F3683 fn63 覆盖的是 resolve 后第二守卫; ops-app 全量跑该场景已覆盖,
 *  本仓独缺的是入口守卫 — immediate 场景下 execute 总是挂载期被调, 唯一卸载后入口是 refresh)
 * L24/27 default-arg 与 L69/71/91 等路径全量跑已被其它套件覆盖(单文件跑缺口是套件分布假象), 不重复补。
 */
import { renderHook, act } from '@testing-library/react-native';
import { usePolling } from '../usePolling';

describe('usePolling — 卸载后refresh: execute入口守卫 (L51)', () => {
  it('卸载后refresh()触发execute入口早退, fetcher零调用', async () => {
    const fetcher = jest.fn(() => Promise.resolve('data'));

    const { result, unmount } = renderHook(() =>
      usePolling(fetcher, { interval: 1000, immediate: false, enabled: true })
    );

    // immediate=false → 只排程 timer, fetcher 未被调用
    expect(fetcher).not.toHaveBeenCalled();

    const refresh = result.current.refresh;
    unmount();

    // 卸载后调用 refresh: setLoading(true) 无效setState, execute() 入口
    // mountedRef.current=false 早退 (L51), fetcher 不被调用
    act(() => {
      refresh();
    });

    expect(fetcher).not.toHaveBeenCalled();
  });
});
