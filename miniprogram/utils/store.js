const { rawRequest, getToken } = require('./request');

const KEY = 'pending_writes';

function load() {
  return wx.getStorageSync(KEY) || [];
}

function save(list) {
  wx.setStorageSync(KEY, list);
}

function enqueue(op) {
  const list = load();
  list.push(op);
  save(list);
}

async function flush() {
  const list = load();
  if (!list.length || !getToken()) return;
  const rest = [];
  for (let i = 0; i < list.length; i += 1) {
    try {
      await rawRequest(list[i].path, {
        method: list[i].method,
        data: list[i].data,
        token: getToken(),
      });
    } catch (err) {
      rest.push(list[i]);
    }
  }
  save(rest);
}

function pendingCount() {
  return load().length;
}

module.exports = { enqueue, flush, pendingCount };
