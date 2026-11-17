const { request } = require('../../utils/request');
const { todayStr, shiftDate, fmtMinutes } = require('../../utils/date');

Page({
  data: {
    range: 7,
    days: 0,
    workText: '0分钟',
    funText: '0分钟',
    avgWake: '--:--',
    avgKcal: '0',
    rows: [],
    maxMinutes: 1,
    loading: true,
  },

  onShow() {
    this.load();
  },

  switchRange(e) {
    const range = Number(e.currentTarget.dataset.range);
    if (range === this.data.range) return;
    this.setData({ range });
    this.load();
  },

  async load() {
    const to = todayStr(0);
    const from = shiftDate(to, -(this.data.range - 1));
    try {
      const data = await request(`/api/stats/summary?from=${from}&to=${to}`);
      const maxMinutes = Math.max(
        60,
        ...data.series.map((row) => Math.max(row.work_minutes, row.entertainment_minutes))
      );
      const rows = data.series.map((row) => ({
        ...row,
        label: row.date.slice(5),
        workPct: Math.round((row.work_minutes / maxMinutes) * 100),
        funPct: Math.round((row.entertainment_minutes / maxMinutes) * 100),
        workText: fmtMinutes(row.work_minutes),
      }));
      this.setData({
        days: data.days,
        workText: fmtMinutes(data.work_minutes),
        funText: fmtMinutes(data.entertainment_minutes),
        avgWake: data.avg_wake_text || '--:--',
        avgKcal: String(data.avg_kcal || 0),
        rows,
        maxMinutes,
        loading: false,
      });
    } catch (err) {
      wx.showToast({ title: err.message, icon: 'none' });
      this.setData({ loading: false });
    }
  },
});
