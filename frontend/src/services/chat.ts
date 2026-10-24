/**
 * 天链助手 - 对话服务 + 可插拔语音STT/TTS
 *
 * 架构:
 * - 对话API: /api/v1/chat (后端FastAPI)
 * - 语音模式: 支持Web Speech API + 自定义云端API，通过配置切换
 *
 * 丁哥要求:
 * 1. STT/TTS不在天链服务器(1.6G内存)跑语音模型
 * 2. 可插拔架构，支持多provider切换
 * 3. 默认使用浏览器Web Speech API (零成本、零服务器负载)
 */

import api from '../api';

// ==================== 类型定义 ====================

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface ChatRequest {
  message: string;
  history?: ChatMessage[];
  context?: Record<string, unknown>;
  stream?: boolean;
}

export interface ChatResponse {
  answer: string;
  confidence: number;
  sources: string[];
  actions: { label: string; url: string }[];
  needs_human: boolean;
  usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
}

export interface VoiceConfig {
  provider: string;
  available_providers: string[];
  stt_endpoint?: string;
  tts_endpoint?: string;
}

// ==================== 语音提供商接口 ====================

export interface STTProvider {
  name: string;
  label: string;
  /** 语音识别: 音频Blob → 文本 */
  recognize(audioBlob: Blob): Promise<string>;
  /** 是否可用 */
  isAvailable(): boolean;
}

export interface TTSProvider {
  name: string;
  label: string;
  /** 语音合成: 文本 → 播放 */
  speak(text: string): Promise<void>;
  /** 停止播放 */
  stop(): void;
  /** 是否正在播放 */
  isSpeaking(): boolean;
  /** 是否可用 */
  isAvailable(): boolean;
}

// ==================== Web Speech API 实现 ====================

class WebSpeechSTTProvider implements STTProvider {
  name = 'web_speech';
  label = '浏览器语音识别';

  isAvailable(): boolean {
    return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  }

  async recognize(audioBlob: Blob): Promise<string> {
    // Web Speech API 直接使用浏览器麦克风，不需要传入audioBlob
    // 这里使用实时识别
    return new Promise((resolve, reject) => {
      const SpeechRecognitionAPI =
        window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechRecognitionAPI) {
        reject(new Error('浏览器不支持语音识别'));
        return;
      }

      const recognition = new SpeechRecognitionAPI();
      recognition.lang = 'zh-CN';
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;

      recognition.onresult = (event: SpeechRecognitionEvent) => {
        const text = event.results[0][0].transcript;
        resolve(text);
      };

      recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
        reject(new Error(`语音识别错误: ${event.error}`));
      };

      recognition.onend = () => {
        // 如果没有触发onresult，超时处理
      };

      try {
        recognition.start();
      } catch (e) {
        reject(new Error(`启动语音识别失败: ${e}`));
      }

      // 超时保护
      setTimeout(() => {
        recognition.stop();
        reject(new Error('语音识别超时'));
      }, 15000);
    });
  }
}

class WebSpeechTTSProvider implements TTSProvider {
  name = 'web_speech';
  label = '浏览器语音合成';
  private _speaking = false;
  private _utterance: SpeechSynthesisUtterance | null = null;

  isAvailable(): boolean {
    return 'speechSynthesis' in window;
  }

  async speak(text: string): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!window.speechSynthesis) {
        reject(new Error('浏览器不支持语音合成'));
        return;
      }

      window.speechSynthesis.cancel();

      this._utterance = new SpeechSynthesisUtterance(text);
      this._utterance.lang = 'zh-CN';
      this._utterance.rate = 1.0;
      this._utterance.pitch = 1.0;

      // 尝试使用中文语音
      const voices = window.speechSynthesis.getVoices();
      const zhVoice = voices.find(
        (v) => v.lang.startsWith('zh') || v.lang.startsWith('cmn')
      );
      if (zhVoice) {
        this._utterance.voice = zhVoice;
      }

      this._utterance.onstart = () => {
        this._speaking = true;
      };

      this._utterance.onend = () => {
        this._speaking = false;
        this._utterance = null;
        resolve();
      };

      this._utterance.onerror = (event) => {
        this._speaking = false;
        this._utterance = null;
        reject(new Error(`语音合成错误: ${event.error}`));
      };

      window.speechSynthesis.speak(this._utterance);
    });
  }

  stop(): void {
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    this._speaking = false;
    this._utterance = null;
  }

  isSpeaking(): boolean {
    return this._speaking;
  }
}

// ==================== 云端API提供商占位 ====================

class CloudProviderSTTProvider implements STTProvider {
  name = 'cloud_a_asr';
  label = '云端语音识别';

  isAvailable(): boolean {
    // 需要后端配置API Key
    return true;
  }

  async recognize(audioBlob: Blob): Promise<string> {
    // 通过后端转发到云服务商ASR
    const reader = new FileReader();
    const base64 = await new Promise<string>((resolve, reject) => {
      reader.onload = () => {
        const result = reader.result as string;
        resolve(result.split(',')[1]);
      };
      reader.onerror = reject;
      reader.readAsDataURL(audioBlob);
    });

    const resp = await api.post('/chat/stt', {
      audio_base64: base64,
      format: 'wav',
      sample_rate: 16000,
    });
    return resp.data.text;
  }
}

class CloudProviderTTSProvider implements TTSProvider {
  name = 'cloud_a_tts';
  label = '云端语音合成';
  private _audio: HTMLAudioElement | null = null;

  isAvailable(): boolean {
    return true;
  }

  async speak(text: string): Promise<void> {
    // 通过后端转发到云服务商TTS
    const resp = await api.post('/chat/tts', {
      text,
      voice: 'default',
      speed: 1.0,
    }, { responseType: 'blob' });

    const url = URL.createObjectURL(resp.data);
    this._audio = new Audio(url);
    this._audio.play();

    return new Promise((resolve) => {
      if (this._audio) {
        this._audio.onended = () => {
          URL.revokeObjectURL(url);
          resolve();
        };
      } else {
        resolve();
      }
    });
  }

  stop(): void {
    if (this._audio) {
      this._audio.pause();
      this._audio = null;
    }
  }

  isSpeaking(): boolean {
    return this._audio !== null && !this._audio.paused;
  }
}

// ==================== 语音管理器 ====================

export class VoiceManager {
  private _sttProviders: Map<string, STTProvider> = new Map();
  private _ttsProviders: Map<string, TTSProvider> = new Map();
  private _activeSTTProvider: string = 'web_speech';
  private _activeTTSProvider: string = 'web_speech';

  constructor() {
    // 注册默认的Web Speech provider
    this.registerSTTProvider(new WebSpeechSTTProvider());
    this.registerTTSProvider(new WebSpeechTTSProvider());

    // 注册云端provider
    this.registerSTTProvider(new CloudProviderSTTProvider());
    this.registerTTSProvider(new CloudProviderTTSProvider());
  }

  registerSTTProvider(provider: STTProvider): void {
    this._sttProviders.set(provider.name, provider);
  }

  registerTTSProvider(provider: TTSProvider): void {
    this._ttsProviders.set(provider.name, provider);
  }

  setActiveSTT(name: string): boolean {
    if (this._sttProviders.has(name)) {
      this._activeSTTProvider = name;
      return true;
    }
    return false;
  }

  setActiveTTS(name: string): boolean {
    if (this._ttsProviders.has(name)) {
      this._activeTTSProvider = name;
      return true;
    }
    return false;
  }

  getSTTProvider(): STTProvider {
    const provider = this._sttProviders.get(this._activeSTTProvider);
    if (!provider || !provider.isAvailable()) {
      // fallback to web_speech
      const fallback = this._sttProviders.get('web_speech');
      if (fallback?.isAvailable()) {
        this._activeSTTProvider = 'web_speech';
        return fallback;
      }
      throw new Error('没有可用的语音识别提供商');
    }
    return provider;
  }

  getTTSProvider(): TTSProvider {
    const provider = this._ttsProviders.get(this._activeTTSProvider);
    if (!provider || !provider.isAvailable()) {
      const fallback = this._ttsProviders.get('web_speech');
      if (fallback?.isAvailable()) {
        this._activeTTSProvider = 'web_speech';
        return fallback;
      }
      throw new Error('没有可用的语音合成提供商');
    }
    return provider;
  }

  getAvailableSTTProviders(): string[] {
    return Array.from(this._sttProviders.entries())
      .filter(([_, p]) => p.isAvailable())
      .map(([name, p]) => `${name}:${p.label}`);
  }

  getAvailableTTSProviders(): string[] {
    return Array.from(this._ttsProviders.entries())
      .filter(([_, p]) => p.isAvailable())
      .map(([name, p]) => `${name}:${p.label}`);
  }

  getActiveSTTName(): string {
    return this._activeSTTProvider;
  }

  getActiveTTSName(): string {
    return this._activeTTSProvider;
  }
}

// 全局单例
export const voiceManager = new VoiceManager();

// ==================== 对话API ====================

export async function sendChatMessage(
  message: string,
  history?: ChatMessage[],
  context?: Record<string, unknown>
): Promise<ChatResponse> {
  const payload: ChatRequest = { message };
  if (history && history.length > 0) payload.history = history;
  if (context) payload.context = context;

  const resp = await api.post('/chat', payload);
  return resp.data;
}

// ==================== 语音服务 ====================

export async function startSTT(): Promise<string> {
  const provider = voiceManager.getSTTProvider();
  // 使用浏览器麦克风录制
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const mediaRecorder = new MediaRecorder(stream, {
    mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : 'audio/webm',
  });

  const chunks: Blob[] = [];
  mediaRecorder.ondataavailable = (e) => {
    if (e.data.size > 0) chunks.push(e.data);
  };

  return new Promise((resolve, reject) => {
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      const audioBlob = new Blob(chunks, { type: 'audio/webm' });

      try {
        const text = await provider.recognize(audioBlob);
        resolve(text);
      } catch (e) {
        reject(e);
      }
    };

    mediaRecorder.onerror = () => {
      stream.getTracks().forEach((t) => t.stop());
      reject(new Error('录音失败'));
    };

    mediaRecorder.start();
    // 自动停止（静音检测或超时）
    setTimeout(() => {
      if (mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
      }
    }, 10000);
  });
}

export function speakText(text: string): Promise<void> {
  const provider = voiceManager.getTTSProvider();
  return provider.speak(text);
}

export function stopSpeaking(): void {
  const provider = voiceManager.getTTSProvider();
  provider.stop();
}

export async function getVoiceConfig(): Promise<VoiceConfig> {
  return (await api.get('/chat/voice-config')).data;
}

