// components/station-card/index.js
const util = require('../../utils/util');

Component({
  properties: {
    station: {
      type: Object,
      value: {},
      observer: function(newVal) {
        if (newVal && newVal.distance !== undefined) {
          this.setData({
            distanceText: util.formatDistance(newVal.distance)
          });
        }
      }
    }
  },

  data: {
    distanceText: ''
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
