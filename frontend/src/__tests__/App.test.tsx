/**
 * 天链V3 - App组件测试
 */
import { render } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'

describe('App组件', () => {
  it('应能渲染路由结构', () => {
    const App = require('../App').default
    const { container } = render(
      <BrowserRouter><App /></BrowserRouter>
    )
    expect(container).toBeTruthy()
  })
})
