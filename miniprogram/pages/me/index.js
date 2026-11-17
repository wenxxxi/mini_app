const { request, login } = require('../../utils/request');
const { todayStr, shiftDate } = require('../../utils/date');
const { pendingCount, flush } = require('../../utils/store');

Page({
  data: {
    user: null,
    dayStartHour: 4,
    pending: 0,
    exporting: false,
  },

  onShow() {
    this.load();
  },

  async load() {
    try {
      const user = await request('/api/me');
      getApp().globalData.user = user;
      getApp().globalData.dayStartHour = user.day_start_hour;
      this.setData({ user, dayStartHour: user.day_start_hour, pending: pendingCount() });
    } catch (err) {
      wx.showToast({ title: err.message, icon: 'none' });
    }
  },

  async onDayStartChange(e) {
    const hour = Number(e.detail.value);
    try {
      const user = await request('/api/me', { method: 'PATCH', data: { day_start_hour: hour } });
      getApp().globalData.dayStartHour = user.day_start_hour;
      this.setData({ user, dayStartHour: user.day_start_hour });
      wx.showToast({ title: '已保存', icon: 'success' });
    } catch (err) {
      wx.showToast({ title: err.message, icon: 'none' });
    }
  },

  async syncPending() {
    await flush();
    this.setData({ pending: pendingCount() });
    wx.showToast({ title: `剩余 ${pendingCount()} 条`, icon: 'none' });
  },

  async exportData() {
    if (this.data.exporting) return;
    this.setData({ exporting: true });
    try {
      const to = todayStr(0);
      const from = shiftDate(to, -89);
      const [reviews, countdowns] = await Promise.all([
        request(`/api/reviews?from=${from}&to=${to}`),
        request('/api/countdowns?include_past=true'),
      ]);
      const text = JSON.stringify({ exported_at: new Date().toISOString(), reviews, countdowns });
      await new Promise((resolve, reject) => {
        wx.setClipboardData({ data: text, success: resolve, fail: reject });
      });
      wx.showToast({ title: '已复制到剪贴板', icon: 'success' });
    } catch (err) {
      wx.showToast({ title: err.message, icon: 'none' });
    } finally {
      this.setData({ exporting: false });
    }
  },

  async relogin() {
    try {
      wx.removeStorageSync('token');
      await login();
      await this.load();
      wx.showToast({ title: '已重新登录', icon: 'success' });
    } catch (err) {
      wx.showToast({ title: err.message, icon: 'none' });
    }
  },
});
