/**
 * chat 服务 + VoiceManager 单元测试 (夜班 AI 对话补测)
 *
 * 覆盖:
 * - sendChatMessage: 成功 / 网络错误透传 / 业务码错误透传 / payload 构造
 * - VoiceManager (独立实例): 默认注册 / 可用性过滤 / 激活切换 / fallback / 无可用抛错
 * - 浏览器语音 API 缺失优雅降级: 模块单例构造不崩 + web_speech 被过滤出可用列表 + 受控抛错
 * - startSTT: provider 不可用错误路径 (getUserMedia 未触达) + 录音→识别成功路径
 * - speakText / stopSpeaking: 走激活 provider + 幂等
 * - getVoiceConfig
 *
 * jsdom 不提供 SpeechRecognition / speechSynthesis / MediaRecorder / mediaDevices,
 * 默认即 "浏览器语音 API 缺失" 场景; 需要存在性的用例用 Object.defineProperty 临时注入再清理。
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// 隔离被测服务自身逻辑: 整体 mock '../../api' (拦截器链已有 interceptor.test 覆盖)
const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));
vi.mock('../../api', () => ({
  default: { get: apiGet, post: apiPost },
}));

import {
  VoiceManager,
  voiceManager,
  sendChatMessage,
  startSTT,
  speakText,
  stopSpeaking,
  getVoiceConfig,
  type STTProvider,
  type TTSProvider,
} from '../chat';

// ---------- helpers: 临时注入/清理浏览器语音 API ----------
function defineWindowProp(name: string, value: unknown) {
  Object.defineProperty(window, name, { value, configurable: true, writable: true });
}
function deleteWindowProp(name: string) {
  try {
    delete (window as any)[name];
  } catch {
    /* ignore */
  }
}

beforeEach(() => {
  // 单例激活状态复位到默认 web_speech
  voiceManager.setActiveSTT('web_speech');
  voiceManager.setActiveTTS('web_speech');
  apiGet.mockReset();
  apiPost.mockReset();
});

afterEach(() => {
  // 清理本文件可能 stub 的浏览器 API (确保 'xxx' in window 回到 false)
  deleteWindowProp('SpeechRecognition');
  deleteWindowProp('webkitSpeechRecognition');
  deleteWindowProp('speechSynthesis');
  try {
    delete (navigator as any).mediaDevices;
  } catch {
    /* ignore */
  }
  try {
    delete (global as any).MediaRecorder;
  } catch {
    /* ignore */
  }
});

// ==================== sendChatMessage ====================
describe('sendChatMessage', () => {
  const okResp = {
    answer: '你好', confidence: 0.9, sources: [], actions: [], needs_human: false,
  };

  it('成功: POST /chat 并返回 resp.data', async () => {
    apiPost.mockResolvedValue({ data: okResp });
    const r = await sendChatMessage('在吗');
    expect(apiPost).toHaveBeenCalledWith('/chat', { message: '在吗' });
    expect(r).toEqual(okResp);
  });

  it('带非空 history 与 context 时拼入 payload', async () => {
    apiPost.mockResolvedValue({ data: okResp });
    const history = [{ role: 'user' as const, content: '历史问题' }];
    await sendChatMessage('msg', history, { page_type: 'device_list' });
    expect(apiPost).toHaveBeenCalledWith('/chat', {
      message: 'msg',
      history,
      context: { page_type: 'device_list' },
    });
  });

  it('history 为空数组时不拼入 history 字段', async () => {
    apiPost.mockResolvedValue({ data: okResp });
    await sendChatMessage('msg', []);
    expect(apiPost).toHaveBeenCalledWith('/chat', { message: 'msg' });
  });

  it('history 为 undefined 时不拼入 history 字段', async () => {
    apiPost.mockResolvedValue({ data: okResp });
    await sendChatMessage('msg');
    expect(apiPost).toHaveBeenCalledWith('/chat', { message: 'msg' });
  });

  it('网络错误: api.post reject → 透传 reject', async () => {
    apiPost.mockRejectedValue(new Error('Network Error'));
    await expect(sendChatMessage('x')).rejects.toThrow('Network Error');
  });

  it('业务码错误: 拦截器转换后的带 code 错误透传 (sendChatMessage 不吞错)', async () => {
    const bizErr = Object.assign(new Error('内部错误'), {
      code: 500,
      response: { code: 500, message: '内部错误' },
    });
    apiPost.mockRejectedValue(bizErr);
    await expect(sendChatMessage('x')).rejects.toMatchObject({ code: 500, message: '内部错误' });
  });
});

// ==================== getVoiceConfig ====================
describe('getVoiceConfig', () => {
  it('返回 /chat/voice-config 的 data', async () => {
    const cfg = { provider: 'web_speech', available_providers: ['web_speech', 'cloud_a_asr'] };
    apiGet.mockResolvedValue({ data: cfg });
    const r = await getVoiceConfig();
    expect(apiGet).toHaveBeenCalledWith('/chat/voice-config');
    expect(r).toEqual(cfg);
  });

  it('api 报错时透传', async () => {
    apiGet.mockRejectedValue(new Error('boom'));
    await expect(getVoiceConfig()).rejects.toThrow('boom');
  });
});

// ==================== VoiceManager (独立实例, 完全隔离) ====================
describe('VoiceManager (独立实例)', () => {
  let vm: VoiceManager;
  beforeEach(() => {
    vm = new VoiceManager();
  });

  it('构造注册默认 provider, 默认激活 web_speech', () => {
    expect(vm.getActiveSTTName()).toBe('web_speech');
    expect(vm.getActiveTTSName()).toBe('web_speech');
    // cloud_provider provider 默认可用
    expect(vm.getAvailableSTTProviders()).toEqual(
      expect.arrayContaining(['cloud_a_asr:云端语音识别']),
    );
    expect(vm.getAvailableTTSProviders()).toEqual(
      expect.arrayContaining(['cloud_a_tts:云端语音合成']),
    );
  });

  it('浏览器语音 API 缺失时, web_speech 被排除出可用列表 (仅 cloud_provider 可用)', () => {
    // jsdom 现状断言
    expect('SpeechRecognition' in window || 'webkitSpeechRecognition' in window).toBe(false);
    expect('speechSynthesis' in window).toBe(false);

    const stt = vm.getAvailableSTTProviders();
    const tts = vm.getAvailableTTSProviders();
    expect(stt).not.toContain(expect.stringMatching(/^web_speech:/));
    expect(tts).not.toContain(expect.stringMatching(/^web_speech:/));
    expect(stt).toContain('cloud_a_asr:云端语音识别');
    expect(tts).toContain('cloud_a_tts:云端语音合成');
  });

  it('getSTTProvider: 激活项不可用且 fallback 不可用 → 抛受控错误 (不崩 TypeError)', () => {
    // 默认 active=web_speech, jsdom 下不可用, fallback 仍是 web_speech
    expect(() => vm.getSTTProvider()).toThrow('没有可用的语音识别提供商');
  });

  it('getTTSProvider: 激活项不可用且 fallback 不可用 → 抛受控错误', () => {
    expect(() => vm.getTTSProvider()).toThrow('没有可用的语音合成提供商');
  });

  it('setActiveSTT 未知 provider → 返回 false, 激活项不变', () => {
    const before = vm.getActiveSTTName();
    expect(vm.setActiveSTT('does-not-exist')).toBe(false);
    expect(vm.getActiveSTTName()).toBe(before);
  });

  it('setActiveSTT 已注册 provider → 返回 true 并切换', () => {
    expect(vm.setActiveSTT('cloud_a_asr')).toBe(true);
    expect(vm.getActiveSTTName()).toBe('cloud_a_asr');
  });

  it('setActiveTTS 已注册 provider → 返回 true 并切换', () => {
    expect(vm.setActiveTTS('cloud_a_tts')).toBe(true);
    expect(vm.getActiveTTSName()).toBe('cloud_a_tts');
  });

  it('registerSTTProvider + getSTTProvider 返回自定义可用 provider', () => {
    const mock: STTProvider = {
      name: 'mock-stt', label: 'M', isAvailable: () => true,
      recognize: vi.fn().mockResolvedValue('hi'),
    };
    vm.registerSTTProvider(mock);
    expect(vm.setActiveSTT('mock-stt')).toBe(true);
    expect(vm.getSTTProvider()).toBe(mock);
  });

  it('getSTTProvider: 激活项不可用但 web_speech 可用 → fallback 到 web_speech 并回写激活项', () => {
    // 让 web_speech 可用
    defineWindowProp('SpeechRecognition', function MockSR() {});
    const broken: STTProvider = {
      name: 'broken', label: 'B', isAvailable: () => false, recognize: vi.fn(),
    };
    vm.registerSTTProvider(broken);
    expect(vm.setActiveSTT('broken')).toBe(true);

    const got = vm.getSTTProvider();
    expect(got.name).toBe('web_speech');
    expect(vm.getActiveSTTName()).toBe('web_speech'); // 激活项被回写
  });

  it('getTTSProvider: 激活项不可用但 web_speech 可用 → fallback 到 web_speech', () => {
    defineWindowProp('speechSynthesis', {});
    const broken: TTSProvider = {
      name: 'broken-tts', label: 'B', isAvailable: () => false,
      speak: vi.fn(), stop: vi.fn(), isSpeaking: () => false,
    };
    vm.registerTTSProvider(broken);
    expect(vm.setActiveTTS('broken-tts')).toBe(true);

    const got = vm.getTTSProvider();
    expect(got.name).toBe('web_speech');
    expect(vm.getActiveTTSName()).toBe('web_speech');
  });

  it('registerTTSProvider + setActiveTTS + getTTSProvider 返回自定义 provider', () => {
    const mock: TTSProvider = {
      name: 'mock-tts', label: 'M', isAvailable: () => true,
      speak: vi.fn().mockResolvedValue(undefined), stop: vi.fn(), isSpeaking: () => false,
    };
    vm.registerTTSProvider(mock);
    expect(vm.setActiveTTS('mock-tts')).toBe(true);
    expect(vm.getTTSProvider()).toBe(mock);
  });
});

// ==================== 模块单例 (浏览器 API 缺失下不崩) ====================
describe('voiceManager 模块单例 - 浏览器 API 缺失下优雅降级', () => {
  it('单例在无语音 API 环境下成功构造 (导入即构造, 不崩)', () => {
    expect(voiceManager).toBeInstanceOf(VoiceManager);
  });

  it('speakText 无可用 TTS provider → 受控抛错 (不崩)', () => {
    // 注: getTTSProvider() 在 speakText 内同步抛错 (早于 return provider.speak(text)),
    // 故 speakText 在此场景同步抛错而非 reject —— 源码现状, 此处如实断言受控错误。
    // 正常 `await speakText()` 调用下该同步抛错会被 await 转为 rejection, 不影响调用方。
    voiceManager.setActiveTTS('web_speech'); // jsdom 下不可用
    expect(() => speakText('x')).toThrow('没有可用的语音合成提供商');
  });

  it('stopSpeaking 无可用 TTS provider → 受控抛错 (不崩)', () => {
    voiceManager.setActiveTTS('web_speech');
    expect(() => stopSpeaking()).toThrow('没有可用的语音合成提供商');
  });
});

// ==================== speakText / stopSpeaking (有可用 provider) ====================
describe('speakText / stopSpeaking - 有可用 provider', () => {
  it('speakText 调用激活 provider.speak(text)', async () => {
    const speak = vi.fn().mockResolvedValue(undefined);
    const mock: TTSProvider = {
      name: 'tts-speak', label: 'T', isAvailable: () => true,
      speak, stop: vi.fn(), isSpeaking: () => false,
    };
    voiceManager.registerTTSProvider(mock);
    voiceManager.setActiveTTS('tts-speak');
    await speakText('你好世界');
    expect(speak).toHaveBeenCalledWith('你好世界');
  });

  it('stopSpeaking 调用激活 provider.stop', () => {
    const stop = vi.fn();
    const mock: TTSProvider = {
      name: 'tts-stop', label: 'T', isAvailable: () => true,
      speak: vi.fn(), stop, isSpeaking: () => false,
    };
    voiceManager.registerTTSProvider(mock);
    voiceManager.setActiveTTS('tts-stop');
    stopSpeaking();
    expect(stop).toHaveBeenCalledTimes(1);
  });

  it('stopSpeaking 幂等: 多次调用不抛错', () => {
    const stop = vi.fn();
    const mock: TTSProvider = {
      name: 'tts-stop2', label: 'T', isAvailable: () => true,
      speak: vi.fn(), stop, isSpeaking: () => false,
    };
    voiceManager.registerTTSProvider(mock);
    voiceManager.setActiveTTS('tts-stop2');
    expect(() => {
      stopSpeaking();
      stopSpeaking();
      stopSpeaking();
    }).not.toThrow();
    expect(stop).toHaveBeenCalledTimes(3);
  });
});

// ==================== startSTT ====================
describe('startSTT', () => {
  it('provider 不可用 → 受控 reject, getUserMedia 未被触达', async () => {
    voiceManager.setActiveSTT('web_speech'); // jsdom 下不可用
    const getUserMedia = vi.fn();
    Object.defineProperty(navigator, 'mediaDevices', {
      value: { getUserMedia },
      configurable: true,
    });
    await expect(startSTT()).rejects.toThrow('没有可用的语音识别提供商');
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it('录音 → onstop → provider.recognize: 返回识别文本, 释放麦克风轨道', async () => {
    vi.useFakeTimers();
    const recognize = vi.fn().mockResolvedValue('你好天链');
    const mock: STTProvider = {
      name: 'stt-record', label: 'S', isAvailable: () => true, recognize,
    };
    voiceManager.registerSTTProvider(mock);
    voiceManager.setActiveSTT('stt-record');

    const trackStop = vi.fn();
    Object.defineProperty(navigator, 'mediaDevices', {
      value: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: trackStop }] }),
      },
      configurable: true,
    });

    let instance: any;
    const MockRecorder = vi.fn().mockImplementation(function (this: any) {
      this.state = 'inactive';
      this.ondataavailable = null;
      this.onstop = null;
      this.onerror = null;
      this.start = () => {
        this.state = 'recording';
      };
      this.stop = () => {
        this.state = 'inactive';
        this.ondataavailable?.({ data: { size: 8 } });
        this.onstop?.();
      };
      instance = this;
    }) as any;
    MockRecorder.isTypeSupported = () => true;
    (global as any).MediaRecorder = MockRecorder;

    const p = startSTT();
    // 刷新微任务: 让 getUserMedia 的 resolved 落地, 推进到 new MediaRecorder → instance 赋值
    await Promise.resolve();
    await Promise.resolve();
    expect(instance).toBeDefined();
    // 手动驱动停止 → 触发 onstop → recognize
    instance.stop();
    const text = await p;

    expect(text).toBe('你好天链');
    expect(recognize).toHaveBeenCalledTimes(1);
    expect(trackStop).toHaveBeenCalled(); // 麦克风轨道已释放

    vi.clearAllTimers(); // 清理 startSTT 内 10s 自动停止定时器
    vi.useRealTimers();
  });
});
