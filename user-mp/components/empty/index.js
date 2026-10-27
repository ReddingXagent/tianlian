// components/empty/index.js
Component({
  properties: {
    visible: {
      type: Boolean,
      value: false
    },
    text: {
      type: String,
      value: '暂无数据'
    },
    icon: {
      type: String,
      value: ''
    },
    showAction: {
      type: Boolean,
      value: false
    },
    actionText: {
      type: String,
      value: '重试'
    }
  },

  methods: {
    onAction() {
      this.triggerEvent('action');
    }
  }
});
