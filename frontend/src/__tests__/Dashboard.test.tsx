/**
 * 天链V3 - Dashboard组件测试
 */
import { render } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'

describe('Dashboard组件', () => {
  it('应能加载组件', () => {
    const Dashboard = require('../pages/Dashboard').default
    const { container } = render(
      <BrowserRouter><Dashboard /></BrowserRouter>
    )
    expect(container).toBeTruthy()
  })
})
