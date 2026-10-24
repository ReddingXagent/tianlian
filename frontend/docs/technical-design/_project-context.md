# Project Context Snapshot

## 1. 工程概览
- Root: `/Users/xxx/.openclaw/workspace/projects/tianlian-v3/frontend`
- package.json: yes
- src/: yes

## 2. 依赖与脚本
- Scripts:
  - `build`: `vite build`
  - `dev`: `vite`
  - `format`: `prettier --write "src/**/*.{ts,tsx,js,jsx,json,css,md}"`
  - `format:check`: `prettier --check "src/**/*.{ts,tsx,js,jsx,json,css,md}"`
  - `lint`: `eslint src --ext .ts,.tsx`
  - `preview`: `vite preview`
  - `test`: `vitest run`
  - `test:all`: `vitest run --coverage && npm run test:e2e`
  - `test:coverage`: `vitest run --coverage`
  - `test:e2e`: `playwright test`
  - `test:e2e:ci`: `playwright test --reporter=html,json,list`
  - `test:e2e:debug`: `playwright test --debug`
  - `test:e2e:report`: `playwright show-report test-results/html`
  - `test:e2e:ui`: `playwright test --ui`
  - `test:jest`: `jest`
  - `test:jest:coverage`: `jest --coverage`
  - `test:ui`: `vitest --ui`
  - `test:unit`: `vitest run`
  - `test:watch`: `vitest`
  - `typecheck`: `tsc --noEmit`
- Key dependencies:
  - `@ant-design/icons`: `^5.2.6`
  - `@playwright/test`: `^1.60.0`
  - `@react-three/drei`: `^9.122.0`
  - `@react-three/fiber`: `^8.18.0`
  - `@testing-library/jest-dom`: `^6.9.1`
  - `@testing-library/react`: `^16.3.2`
  - `@testing-library/user-event`: `^14.6.1`
  - `@types/file-saver`: `^2.0.7`
  - `@types/jest`: `^30.0.0`
  - `@types/node`: `^25.5.0`
  - `@types/react`: `^18.2.43`
  - `@types/react-dom`: `^18.2.17`
  - `@types/three`: `^0.184.1`
  - `@vitejs/plugin-react`: `^4.2.1`
  - `@vitest/coverage-v8`: `^4.1.7`
  - `@vitest/ui`: `^4.1.7`
  - `antd`: `^5.12.0`
  - `axios`: `^1.6.2`
  - `dayjs`: `^1.11.10`
  - `echarts`: `^6.0.0`
  - `echarts-for-react`: `^3.0.6`
  - `file-saver`: `^2.0.5`
  - `happy-dom`: `^20.9.0`
  - `jest`: `^30.4.2`
  - `jest-environment-jsdom`: `^30.4.1`
  - `jsdom`: `^29.1.1`
  - `jsqr`: `^1.4.0`
  - `less`: `^4.6.4`
  - `msw`: `^2.14.6`
  - `react`: `^18.2.0`
  - `react-dom`: `^18.2.0`
  - `react-quill-new`: `^3.8.3`
  - `react-router-dom`: `^6.20.0`
  - `three`: `^0.160.1`
  - `ts-jest`: `^29.4.9`
  - `typescript`: `^5.3.3`
  - `vite`: `^5.0.8`
  - `vite-plugin-pwa`: `^1.3.0`
  - `vitest`: `^4.1.7`
  - `workbox-precaching`: `^7.4.1`
  - `xlsx`: `^0.18.5`

## 3. 配置文件
- TypeScript configs:
  - `tsconfig.json`
  - `tsconfig.node.json`
- Build configs:
  - `vite.config.ts`

## 4. 目录结构线索
- src subdirectories:
  - `src/__tests__`
  - `src/api`
  - `src/components`
  - `src/config`
  - `src/hooks`
  - `src/locales`
  - `src/pages`
  - `src/services`
  - `src/store`
  - `src/types`
  - `src/utils`

## 5. 规范文档
- 未发现 AGENTS.md/policies/docs 规范文件
- 需要在详细设计文档“待确认项”补充规范缺失说明

## 6. 方案约束建议（供详细设计引用）
- 优先沿用现有目录与命名模式，避免引入新分层。
- 新增技术选型需标注依据来源和兼容策略。
- 未找到明确规范时，以现有实现中的主流模式为准并标注假设。
