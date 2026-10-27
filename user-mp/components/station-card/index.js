// components/station-card/index.js
const util = require('../../utils/util');
const brandingUtil = require('../../utils/branding');

Component({
  properties: {
    station: {
      type: Object,
      value: {},
      observer: function(newVal) {
        if (!newVal) return;
        const updates = {};
        if (newVal.distance !== undefined) {
          updates.distanceText = util.formatDistance(newVal.distance);
        }
        // 消费 branding 字段做动态品牌渲染
        const branding = brandingUtil.getStationBranding(newVal);
        updates.brandOperator = branding.operatorName;
        updates.brandColor = branding.themeColor;
        updates.brandColorLight = brandingUtil.hexToRgba(branding.themeColor, 0.1);
        updates.brandIsCustom = branding.isCustom;
        this.setData(updates);
      }
    }
  },

  data: {
    distanceText: '',
    brandOperator: '',
    brandColor: '',
    brandColorLight: '',
    brandIsCustom: false
  },

  methods: {
    onTap() {
      this.triggerEvent('tap', { station: this.data.station });
    },

    onFav() {
      this.triggerEvent('favorite', { station: this.data.station });
    },

    onUnfav() {
      this.triggerEvent('unfavorite', { station: this.data.station });
    }
  }
});
