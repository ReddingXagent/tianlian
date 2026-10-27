/**
 * react-i18next 测试桩
 *
 * 为什么需要它：项目 src/i18n.ts 与 20+ 组件 `import { useTranslation } from 'react-i18next'`,
 * 但 react-i18next / i18next / i18next-browser-languagedetector 三个包均未安装
 * (package.json 未声明，node_modules 缺失)。生产构建 (vite build) 同样会失败。
 *
 * 为什么用 alias 而非 vi.mock：vitest 对未安装模块无法注册 vi.mock —— 注册时仍需
 * resolve 真实模块路径，找不到包即报 "Failed to resolve import"。用 resolve.alias
 * 把 'react-i18next' 指向此真实存在的桩文件，resolve 才会成功，组件才能 import。
 *
 * 测试范围：单元测试只渲染组件（useTranslation），不 import main.tsx → 不触发 i18n.ts
 * 初始化链路，因此无需 stub i18next / detector。
 *
 * ⚠️ 这是一个测试兜底，不修复生产依赖缺失。生产构建问题需单独处理（安装包或移除 i18n）。
 */
export const useTranslation = (_ns?: unknown) => ({
  t: (key: string, fallback?: string) => fallback ?? key,
  i18n: {
    language: 'zh-CN',
    changeLanguage: () => Promise.resolve(),
    exists: () => true,
  },
  ready: true,
});

export const Trans = ({ children }: any) => children;
export const withTranslation = () => (Comp: any) => Comp;
export const I18nextProvider = ({ children }: any) => children;
export const initReactI18next = { type: '3rdParty', init: () => {} };
