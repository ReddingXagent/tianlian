/**
 * 核心前端单元测试 - 天链V3
 */
import { render } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { describe, it, expect } from '@jest/globals'

describe('天链V3 前端核心组件', () => {
  it('所有核心页面模块可加载', () => {
    const pages = [
      '../pages/Dashboard',
      '../pages/WorkOrders',
      '../pages/AlarmNotices',
      '../pages/AuditLog',
      '../pages/Stations',
      '../pages/Devices',
      '../pages/Alarms',
      '../pages/Users',
      '../pages/Teams',
    ]
    for (const p of pages) {
      const mod = require(p)
      expect(mod.default).toBeDefined()
    }
  })

  it('App 结构定义完整', () => {
    const App = require('../App').default
    expect(App).toBeDefined()
  })
})
