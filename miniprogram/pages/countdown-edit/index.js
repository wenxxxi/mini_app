const { request } = require('../../utils/request');
const { todayStr, toIso, targetToPicker } = require('../../utils/date');

Page({
  data: {
    id: null,
    title: '',
    date: '',
    time: '09:00',
    note: '',
  },

  async onLoad(query) {
    const today = todayStr(0);
    if (!query.id) {
      this.setData({ date: today });
      return;
    }
    try {
      const items = await request('/api/countdowns?include_past=true');
      const item = items.find((it) => String(it.id) === String(query.id));
      if (!item) {
        wx.showToast({ title: '记录不存在', icon: 'none' });
        return;
      }
      const picker = targetToPicker(item.target_at);
      this.setData({
        id: item.id,
        title: item.title,
        date: picker.date,
        time: picker.time,
        note: item.note || '',
      });
      wx.setNavigationBarTitle({ title: '编辑倒计时' });
    } catch (err) {
      wx.showToast({ title: err.message, icon: 'none' });
    }
  },

  onTitle(e) {
    this.setData({ title: e.detail.value });
  },

  onNote(e) {
    this.setData({ note: e.detail.value });
  },

  onDate(e) {
    this.setData({ date: e.detail.value });
  },

  onTime(e) {
    this.setData({ time: e.detail.value });
  },

  async save() {
    const { id, title, date, time, note } = this.data;
    if (!(title || '').trim()) {
      wx.showToast({ title: '请填写标题', icon: 'none' });
      return;
    }
    const payload = {
      title: title.trim(),
      target_at: toIso(date, time),
      note: note || null,
      sort_order: 0,
    };
    try {
      if (id) {
        await request(`/api/countdowns/${id}`, { method: 'PUT', data: payload });
      } else {
        await request('/api/countdowns', { method: 'POST', data: payload });
      }
      wx.navigateBack();
    } catch (err) {
      wx.showToast({ title: err.message, icon: 'none' });
    }
  },

  remove() {
    if (!this.data.id) {
      wx.navigateBack();
      return;
    }
    wx.showModal({
      title: '删除这个倒计时？',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await request(`/api/countdowns/${this.data.id}`, { method: 'DELETE' });
          wx.navigateBack();
        } catch (err) {
          wx.showToast({ title: err.message, icon: 'none' });
        }
      },
    });
  },
});
