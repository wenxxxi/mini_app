const { ensureLogin } = require('./utils/request');
const { flush } = require('./utils/store');

App({
  globalData: {
    user: null,
    dayStartHour: 4,
  },
  onLaunch() {
    ensureLogin()
      .then(() => flush())
      .catch(() => {});
  },
  onShow() {
    flush().catch(() => {});
  },
});
