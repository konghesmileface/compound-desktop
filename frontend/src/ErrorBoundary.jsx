import React from 'react'

// 兜住子树里的渲染错误(比如浏览器不支持 WebGL 时星系图崩溃),
// 避免整个 App 白屏。
export default class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { err: null } }
  static getDerivedStateFromError(err) { return { err } }
  componentDidCatch(err, info) { console.error('[ErrorBoundary]', err, info) }
  render() {
    if (this.state.err) {
      return this.props.fallback || (
        <div className="empty">
          <div className="e-big">这个视图暂时无法显示</div>
          <div>{String(this.state.err)}</div>
        </div>
      )
    }
    return this.props.children
  }
}
