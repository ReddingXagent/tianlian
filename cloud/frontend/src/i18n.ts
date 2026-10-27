/**
 * i18n 初始化配置
 * 支持中文 (zh-CN) 和英文 (en) 双语
 * 语言检测优先级: localStorage > 浏览器语言 > 中文
 */
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import zhCN from './locales/zh-CN.json';
import en from './locales/en.json';

const SUPPORTED_LANGS = ['zh-CN', 'en'];

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      'zh-CN': { translation: zhCN },
      'en': { translation: en },
    },
    fallbackLng: 'zh-CN',
    debug: false,
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ['localStorage', 'navigator', 'htmlTag'],
      caches: ['localStorage'],
      lookupLocalStorage: 'i18nextLng',
    },
    returnObjects: false,
    returnNull: false,
  });

// 语言代码标准化: en → en, zh-CN → zh-CN
i18n.on('languageChanged', (lng) => {
  if (!SUPPORTED_LANGS.includes(lng)) {
    const normalized = lng.startsWith('zh') ? 'zh-CN' : 'en';
    if (normalized !== lng) {
      i18n.changeLanguage(normalized);
    }
  }
  document.documentElement.lang = lng;
});

export default i18n;