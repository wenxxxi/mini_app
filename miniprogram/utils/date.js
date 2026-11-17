function pad(value) {
  return value < 10 ? `0${value}` : `${value}`;
}

function todayStr(dayStartHour) {
  const start = typeof dayStartHour === 'number' ? dayStartHour : 4;
  const now = new Date();
  now.setHours(now.getHours() - start);
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function shiftDate(dateStr, delta) {
  const [y, m, d] = dateStr.split('-').map(Number);
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() + delta);
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
}

function toIso(dateStr, timeStr) {
  if (!timeStr) return null;
  const time = timeStr.length === 5 ? `${timeStr}:00` : timeStr;
  return `${dateStr}T${time}+08:00`;
}

function timeOf(iso) {
  if (!iso) return '';
  const match = String(iso).match(/T(\d{2}:\d{2})/);
  return match ? match[1] : '';
}

function nowIso() {
  const now = new Date();
  const tz = now.getTimezoneOffset() === -480 ? '+08:00' : 'Z';
  const base = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  return tz === 'Z' ? `${base}Z` : `${base}+08:00`;
}

function fmtMinutes(minutes) {
  const total = Math.max(Number(minutes) || 0, 0);
  const hours = Math.floor(total / 60);
  const mins = total % 60;
  if (hours && mins) return `${hours}小时${mins}分`;
  if (hours) return `${hours}小时`;
  return `${mins}分钟`;
}

function weekday(dateStr) {
  const [y, m, d] = dateStr.split('-').map(Number);
  return ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][new Date(y, m - 1, d).getDay()];
}

function countdownParts(targetIso) {
  const target = new Date(targetIso.replace(/-/g, '/').replace('T', ' ')).getTime();
  const diff = target - Date.now();
  const past = diff < 0;
  let rest = Math.abs(diff);
  const days = Math.floor(rest / 86400000);
  rest -= days * 86400000;
  const hours = Math.floor(rest / 3600000);
  rest -= hours * 3600000;
  const minutes = Math.floor(rest / 60000);
  const seconds = Math.floor((rest - minutes * 60000) / 1000);
  return { past, days, hours, minutes, seconds };
}

function targetToPicker(iso) {
  const [date, time] = String(iso || '').split('T');
  return { date: date || todayStr(0), time: (time || '09:00').slice(0, 5) };
}

module.exports = {
  pad,
  todayStr,
  shiftDate,
  toIso,
  timeOf,
  nowIso,
  fmtMinutes,
  weekday,
  countdownParts,
  targetToPicker,
};
