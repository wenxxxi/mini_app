const { request } = require('../../utils/request');
const { countdownParts } = require('../../utils/date');

Page({
  data: {
    items: [],
    current: null,
    parts: null,
    loading: true,
  },

  onShow() {
    this.load();
    this.startTimer();
  },

  onHide() {
    this.stopTimer();
  },

  onUnload() {
    this.stopTimer();
  },

  async load() {
    try {
      const items = await request('/api/countdowns');
      const currentId = this.data.current ? this.data.current.id : null;
      const current = items.find((item) => item.id === currentId) || items[0] || null;
      this.setData({
        items,
        current,
        parts: current ? countdownParts(current.target_at) : null,
        loading: false,
      });
    } catch (err) {
      wx.showToast({ title: err.message, icon: 'none' });
      this.setData({ loading: false });
    }
  },

  startTimer() {
    this.stopTimer();
    this.timer = setInterval(() => {
      if (!this.data.current) return;
      this.setData({ parts: countdownParts(this.data.current.target_at) });
    }, 1000);
  },

  stopTimer() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  },

  select(e) {
    const id = e.currentTarget.dataset.id;
    const current = this.data.items.find((item) => item.id === id);
    if (!current) return;
    this.setData({ current, parts: countdownParts(current.target_at) });
  },

  add() {
    wx.navigateTo({ url: '/pages/countdown-edit/index' });
  },

  edit(e) {
    const id = e.currentTarget.dataset.id || (this.data.current && this.data.current.id);
    if (!id) return;
    wx.navigateTo({ url: `/pages/countdown-edit/index?id=${id}` });
  },

  noop() {},
});
