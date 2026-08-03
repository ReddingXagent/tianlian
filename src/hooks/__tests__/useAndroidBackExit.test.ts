import { renderHook } from '@testing-library/react-native';
import { BackHandler, ToastAndroid } from 'react-native';
import { useAndroidBackExit, DOUBLE_BACK_EXIT_MS, EXIT_TOAST_TEXT } from '../useAndroidBackExit';

type BackCb = () => boolean;

interface NavOptions {
  tabIndex?: number;
  parentIndex?: number;
}

function makeNavigation({ tabIndex = 0, parentIndex = 0 }: NavOptions = {}) {
  const navigate = jest.fn();
  const navigation = {
    getParent: () => ({ getState: () => ({ index: parentIndex }) }),
    getState: () => ({ index: tabIndex }),
    navigate,
  };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return { navigation: navigation as any, navigate };
}

describe('useAndroidBackExit (Android硬件返回键治理)', () => {
  let backCb: BackCb | null = null;
  const removeSub = jest.fn();

  beforeEach(() => {
    backCb = null;
    removeSub.mockClear();
    jest.spyOn(BackHandler, 'addEventListener').mockImplementation(((event: string, cb: BackCb) => {
      backCb = cb;
      return { remove: removeSub };
    }) as typeof BackHandler.addEventListener);
    jest.spyOn(BackHandler, 'exitApp').mockImplementation(() => undefined);
    jest.spyOn(ToastAndroid, 'show').mockImplementation(() => undefined);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('挂载即注册 hardwareBackPress, 卸载移除', () => {
    const { navigation } = makeNavigation();
    const { unmount } = renderHook(() => useAndroidBackExit(navigation));
    expect(BackHandler.addEventListener).toHaveBeenCalledWith('hardwareBackPress', expect.any(Function));
    expect(backCb).not.toBeNull();
    unmount();
    expect(removeSub).toHaveBeenCalledTimes(1);
  });

  it('详情页盖住tabs(parent index>0): 不拦截, 返回false让原生back弹栈', () => {
    const { navigation } = makeNavigation({ parentIndex: 1 });
    renderHook(() => useAndroidBackExit(navigation));
    expect(backCb!()).toBe(false);
    expect(BackHandler.exitApp).not.toHaveBeenCalled();
  });

  it('非Home root tab: back先跳Home不退出', () => {
    const { navigation, navigate } = makeNavigation({ tabIndex: 2 });
    renderHook(() => useAndroidBackExit(navigation));
    expect(backCb!()).toBe(true);
    expect(navigate).toHaveBeenCalledWith('Home');
    expect(BackHandler.exitApp).not.toHaveBeenCalled();
    expect(ToastAndroid.show).not.toHaveBeenCalled();
  });

  it('tab state未知(getState undefined): 不拦截退回原生行为', () => {
    const navigation = {
      getParent: () => ({ getState: () => ({ index: 0 }) }),
      getState: () => undefined,
      navigate: jest.fn(),
    };
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    renderHook(() => useAndroidBackExit(navigation as any));
    expect(backCb!()).toBe(false);
  });

  it('Home tab首按: toast提示不退出', () => {
    const { navigation } = makeNavigation({ tabIndex: 0 });
    renderHook(() => useAndroidBackExit(navigation));
    expect(backCb!()).toBe(true);
    expect(ToastAndroid.show).toHaveBeenCalledWith(EXIT_TOAST_TEXT, ToastAndroid.SHORT);
    expect(BackHandler.exitApp).not.toHaveBeenCalled();
  });

  it('Home tab 2秒内再按: exitApp', () => {
    const nowSpy = jest.spyOn(Date, 'now');
    const t0 = 1_000_000;
    nowSpy.mockReturnValueOnce(t0).mockReturnValueOnce(t0 + DOUBLE_BACK_EXIT_MS - 1);
    const { navigation } = makeNavigation({ tabIndex: 0 });
    renderHook(() => useAndroidBackExit(navigation));
    expect(backCb!()).toBe(true); // 首按 toast
    expect(backCb!()).toBe(true); // 二按退出
    expect(BackHandler.exitApp).toHaveBeenCalledTimes(1);
  });

  it('Home tab超过2秒再按: 窗口重置, 只toast不退出', () => {
    const nowSpy = jest.spyOn(Date, 'now');
    const t0 = 1_000_000;
    nowSpy.mockReturnValueOnce(t0).mockReturnValueOnce(t0 + DOUBLE_BACK_EXIT_MS + 1);
    const { navigation } = makeNavigation({ tabIndex: 0 });
    renderHook(() => useAndroidBackExit(navigation));
    expect(backCb!()).toBe(true);
    expect(backCb!()).toBe(true);
    expect(BackHandler.exitApp).not.toHaveBeenCalled();
    expect(ToastAndroid.show).toHaveBeenCalledTimes(2);
  });
});
