const { request } = require('../../utils/request');
const { todayStr, weekday, timeOf, fmtMinutes, countdownParts } = require('../../utils/date');

const MEAL_LABEL = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' };

Page({
  data: {
    date: '',
    weekdayText: '',
    wakeTime: '',
    workText: '0分钟',
    funText: '0分钟',
    summary: '',
    meals: [],
    doneMeals: 0,
    starItems: [],
    doneCount: 0,
    nearest: null,
    nearestParts: null,
    loading: true,
  },

  onShow() {
    this.load();
  },

  async load() {
    const date = todayStr(getApp().globalData.dayStartHour);
    try {
      const [review, countdowns] = await Promise.all([
        request(`/api/reviews/${date}`),
        request('/api/countdowns'),
      ]);
      const meals = ['breakfast', 'lunch', 'dinner'].map((type) => {
        const found = (review.meals || []).find((m) => m.meal_type === type);
        return {
          type,
          label: MEAL_LABEL[type],
          time: found && found.eaten_at ? timeOf(found.eaten_at) : '',
          kcal: found ? found.kcal : 0,
          filled: !!found,
        };
      });
      const starItems = review.star_items || [];
      const doneCount = [
        !!review.wake_at,
        meals.every((m) => m.filled),
        review.work_minutes > 0,
        starItems.length > 0,
      ].filter(Boolean).length;

      const nearest = countdowns.length ? countdowns[0] : null;
      this.setData({
        date,
        weekdayText: weekday(date),
        wakeTime: timeOf(review.wake_at),
        workText: fmtMinutes(review.work_minutes),
        funText: fmtMinutes(review.entertainment_minutes),
        summary: review.summary || '',
        meals,
        doneMeals: meals.filter((m) => m.filled).length,
        starItems,
        doneCount,
        nearest,
        nearestParts: nearest ? countdownParts(nearest.target_at) : null,
        loading: false,
      });
    } catch (err) {
      wx.showToast({ title: err.message, icon: 'none' });
      this.setData({ loading: false });
    }
  },

  goReview() {
    wx.navigateTo({ url: `/pages/review/index?date=${this.data.date}` });
  },

  goCountdown() {
    wx.switchTab({ url: '/pages/countdown/index' });
  },
});
