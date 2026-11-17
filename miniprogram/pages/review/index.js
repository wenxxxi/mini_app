const { request } = require('../../utils/request');
const { todayStr, shiftDate, timeOf, toIso, weekday, fmtMinutes } = require('../../utils/date');

const MEALS = [
  { type: 'breakfast', label: '早餐' },
  { type: 'lunch', label: '午餐' },
  { type: 'dinner', label: '晚餐' },
  { type: 'snack', label: '加餐' },
];

const emptyFood = () => ({
  name: '',
  amount: '',
  unit: 'g',
  kcal: '',
  protein: '',
  fat: '',
  carb: '',
});

Page({
  data: {
    date: '',
    weekdayText: '',
    wakeTime: '',
    workMinutes: 0,
    funMinutes: 0,
    workText: '0分钟',
    funText: '0分钟',
    mood: 0,
    summary: '',
    mealRows: [],
    starItems: [],
    starMinutesText: '0分钟',
    mealSheet: { visible: false, id: null, meal_type: 'breakfast', time: '', note: '', foods: [] },
    mealTypes: MEALS,
    starSheet: {
      visible: false,
      id: null,
      title: '',
      situation: '',
      task: '',
      action: '',
      result: '',
      progress: 0,
      minutes: 0,
    },
  },

  onLoad(query) {
    this.setData({ date: query.date || todayStr(getApp().globalData.dayStartHour) });
    this.load();
  },

  async load() {
    const { date } = this.data;
    try {
      const review = await request(`/api/reviews/${date}`);
      const meals = review.meals || [];
      const mealRows = MEALS.map((item) => {
        const found = meals.find((m) => m.meal_type === item.type);
        return {
          ...item,
          id: found ? found.id : null,
          time: found && found.eaten_at ? timeOf(found.eaten_at) : '',
          kcal: found ? found.kcal : 0,
          filled: !!found,
        };
      });
      const starItems = review.star_items || [];
      this.setData({
        wakeTime: timeOf(review.wake_at),
        workMinutes: review.work_minutes || 0,
        funMinutes: review.entertainment_minutes || 0,
        workText: fmtMinutes(review.work_minutes || 0),
        funText: fmtMinutes(review.entertainment_minutes || 0),
        mood: review.mood || 0,
        summary: review.summary || '',
        mealRows,
        starItems,
        starMinutesText: fmtMinutes(starItems.reduce((sum, item) => sum + (item.minutes || 0), 0)),
        weekdayText: weekday(date),
      });
    } catch (err) {
      wx.showToast({ title: err.message, icon: 'none' });
    }
  },

  changeDate(e) {
    const delta = Number(e.currentTarget.dataset.delta);
    const date = shiftDate(this.data.date, delta);
    this.setData({ date });
    this.load();
  },

  // ---------- 基础字段 ----------
  async saveReview(patch) {
    try {
      await request(`/api/reviews/${this.data.date}`, { method: 'PUT', data: patch });
      await this.load();
    } catch (err) {
      wx.showToast({ title: err.message, icon: 'none' });
    }
  },

  onWakeChange(e) {
    const time = e.detail.value;
    this.setData({ wakeTime: time });
    this.saveReview({ wake_at: toIso(this.data.date, time) });
  },

  adjustWork(e) {
    const delta = Number(e.currentTarget.dataset.delta);
    const value = Math.max(0, this.data.workMinutes + delta);
    if (value === this.data.workMinutes) return;
    this.setData({ workMinutes: value, workText: fmtMinutes(value) });
    this.saveReview({ work_minutes: value });
  },

  adjustFun(e) {
    const delta = Number(e.currentTarget.dataset.delta);
    const value = Math.max(0, this.data.funMinutes + delta);
    if (value === this.data.funMinutes) return;
    this.setData({ funMinutes: value, funText: fmtMinutes(value) });
    this.saveReview({ entertainment_minutes: value });
  },

  setMood(e) {
    const mood = Number(e.currentTarget.dataset.mood);
    this.setData({ mood });
    this.saveReview({ mood });
  },

  onSummaryInput(e) {
    this.setData({ summary: e.detail.value });
  },

  onSummaryBlur(e) {
    this.saveReview({ summary: e.detail.value });
  },

  sumStarMinutes() {
    const total = this.data.starItems.reduce((sum, item) => sum + (item.minutes || 0), 0);
    this.setData({ workMinutes: total, workText: fmtMinutes(total) });
    this.saveReview({ work_minutes: total });
  },

  // ---------- 餐食 ----------
  openMeal(e) {
    const type = e.currentTarget.dataset.type;
    const existing = this.data.mealRows.find((item) => item.type === type && item.filled);
    if (existing) {
      request(`/api/reviews/${this.data.date}`).then((review) => {
        const meal = (review.meals || []).find((m) => m.meal_type === type);
        this.setData({
          mealSheet: {
            visible: true,
            id: meal.id,
            meal_type: type,
            time: meal.eaten_at ? timeOf(meal.eaten_at) : '',
            note: meal.note || '',
            foods: (meal.foods || []).map((f) => ({
              name: f.name || '',
              amount: String(f.amount || ''),
              unit: f.unit || 'g',
              kcal: String(f.kcal || ''),
              protein: String(f.protein || ''),
              fat: String(f.fat || ''),
              carb: String(f.carb || ''),
            })),
          },
        });
      });
      return;
    }
    this.setData({
      mealSheet: { visible: true, id: null, meal_type: type, time: '', note: '', foods: [emptyFood()] },
    });
  },

  closeMeal() {
    this.setData({ 'mealSheet.visible': false });
  },

  onMealTime(e) {
    this.setData({ 'mealSheet.time': e.detail.value });
  },

  onMealNote(e) {
    this.setData({ 'mealSheet.note': e.detail.value });
  },

  onFoodField(e) {
    const index = Number(e.currentTarget.dataset.index);
    const field = e.currentTarget.dataset.field;
    this.setData({ [`mealSheet.foods[${index}].${field}`]: e.detail.value });
  },

  addFood() {
    this.setData({ 'mealSheet.foods': [...this.data.mealSheet.foods, emptyFood()] });
  },

  removeFood(e) {
    const index = Number(e.currentTarget.dataset.index);
    const foods = this.data.mealSheet.foods.filter((_, i) => i !== index);
    this.setData({ 'mealSheet.foods': foods.length ? foods : [emptyFood()] });
  },

  async saveMeal() {
    const sheet = this.data.mealSheet;
    const foods = sheet.foods
      .filter((f) => (f.name || '').trim())
      .map((f) => ({
        name: f.name.trim(),
        amount: Number(f.amount) || 0,
        unit: f.unit || 'g',
        kcal: Number(f.kcal) || 0,
        protein: Number(f.protein) || 0,
        fat: Number(f.fat) || 0,
        carb: Number(f.carb) || 0,
      }));
    if (!foods.length) {
      wx.showToast({ title: '至少填写一种食物', icon: 'none' });
      return;
    }
    const payload = {
      meal_type: sheet.meal_type,
      eaten_at: sheet.time ? toIso(this.data.date, sheet.time) : null,
      note: sheet.note || null,
      foods,
    };
    try {
      if (sheet.id) {
        await request(`/api/meals/${sheet.id}`, { method: 'PUT', data: payload });
      } else {
        await request(`/api/reviews/${this.data.date}/meals`, { method: 'POST', data: payload });
      }
      this.setData({ 'mealSheet.visible': false });
      await this.load();
      wx.showToast({ title: '已保存', icon: 'success' });
    } catch (err) {
      wx.showToast({ title: err.message, icon: 'none' });
    }
  },

  deleteMeal() {
    const sheet = this.data.mealSheet;
    if (!sheet.id) {
      this.closeMeal();
      return;
    }
    wx.showModal({
      title: '删除这餐记录？',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await request(`/api/meals/${sheet.id}`, { method: 'DELETE' });
          this.setData({ 'mealSheet.visible': false });
          await this.load();
        } catch (err) {
          wx.showToast({ title: err.message, icon: 'none' });
        }
      },
    });
  },

  // ---------- STAR ----------
  openStar(e) {
    const id = e.currentTarget.dataset.id;
    if (id) {
      const item = this.data.starItems.find((s) => s.id === id);
      this.setData({
        starSheet: {
          visible: true,
          id: item.id,
          title: item.title,
          situation: item.situation || '',
          task: item.task || '',
          action: item.action || '',
          result: item.result || '',
          progress: item.progress || 0,
          minutes: item.minutes || 0,
        },
      });
      return;
    }
    this.setData({
      starSheet: {
        visible: true,
        id: null,
        title: '',
        situation: '',
        task: '',
        action: '',
        result: '',
        progress: 0,
        minutes: 0,
      },
    });
  },

  closeStar() {
    this.setData({ 'starSheet.visible': false });
  },

  onStarField(e) {
    const field = e.currentTarget.dataset.field;
    this.setData({ [`starSheet.${field}`]: e.detail.value });
  },

  onStarProgress(e) {
    this.setData({ 'starSheet.progress': e.detail.value });
  },

  onStarMinutes(e) {
    this.setData({ 'starSheet.minutes': Number(e.detail.value) || 0 });
  },

  async saveStar() {
    const sheet = this.data.starSheet;
    if (!(sheet.title || '').trim()) {
      wx.showToast({ title: '请填写标题', icon: 'none' });
      return;
    }
    if (!(sheet.situation || '').trim() && !(sheet.result || '').trim()) {
      wx.showToast({ title: '情境与结果至少填一项', icon: 'none' });
      return;
    }
    const payload = {
      title: sheet.title.trim(),
      situation: sheet.situation || null,
      task: sheet.task || null,
      action: sheet.action || null,
      result: sheet.result || null,
      progress: Number(sheet.progress) || 0,
      minutes: Number(sheet.minutes) || 0,
      sort_order: sheet.id ? undefined : this.data.starItems.length,
    };
    if (!payload.sort_order) delete payload.sort_order;
    try {
      if (sheet.id) {
        await request(`/api/star/${sheet.id}`, { method: 'PUT', data: payload });
      } else {
        await request(`/api/reviews/${this.data.date}/star`, { method: 'POST', data: payload });
      }
      this.setData({ 'starSheet.visible': false });
      await this.load();
    } catch (err) {
      wx.showToast({ title: err.message, icon: 'none' });
    }
  },

  deleteStar() {
    const sheet = this.data.starSheet;
    if (!sheet.id) {
      this.closeStar();
      return;
    }
    wx.showModal({
      title: '删除这条工作记录？',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await request(`/api/star/${sheet.id}`, { method: 'DELETE' });
          this.setData({ 'starSheet.visible': false });
          await this.load();
        } catch (err) {
          wx.showToast({ title: err.message, icon: 'none' });
        }
      },
    });
  },

  noop() {},
});
