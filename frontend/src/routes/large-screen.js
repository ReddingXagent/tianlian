import Vue from 'vue'
import LargeScreen from './components/LargeScreen.vue'

export default {
  path: '/large-screen',
  component: LargeScreen,
  router: { scrollBehavior: () => ({ y: 0 }) },
  props: false
}

// LargeScreen.vue should handle:
// 1. Responsive 1920x1080 layout
// 2. WebSocket connection to /api/v1/dashboard/large-screen
// 3. No sidebar in DOM
// 4. Auto-carousel functionality
