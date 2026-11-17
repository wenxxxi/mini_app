const { baseUrl } = require('./config');

function getToken() {
  return wx.getStorageSync('token') || '';
}

function setToken(token) {
  wx.setStorageSync('token', token);
}

// 直接调用 wx.request，用于登录，避免 401 重试递归
function rawRequest(path, options) {
  const { method = 'GET', data, token } = options || {};
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${baseUrl}${path}`,
      method,
      data,
      timeout: 15000,
      header: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
          return;
        }
        const detail = res.data && res.data.detail;
        reject(new Error(typeof detail === 'string' ? detail : `请求失败(${res.statusCode})`));
      },
      fail(err) {
        reject(new Error((err && err.errMsg) || '网络异常'));
      },
    });
  });
}

function login() {
  return new Promise((resolve, reject) => {
    wx.login({
      success: async (res) => {
        if (!res.code) {
          reject(new Error('微信登录失败'));
          return;
        }
        try {
          const data = await rawRequest('/api/auth/login', {
            method: 'POST',
            data: { code: res.code },
          });
          setToken(data.token);
          wx.setStorageSync('user', data.user);
          resolve(data);
        } catch (err) {
          reject(err);
        }
      },
      fail: () => reject(new Error('微信登录失败')),
    });
  });
}

async function ensureLogin() {
  if (getToken()) return;
  await login();
}

async function request(path, options) {
  await ensureLogin();
  try {
    return await rawRequest(path, { ...options, token: getToken() });
  } catch (err) {
    if (err.message.indexOf('登录') === -1) throw err;
    setToken('');
    await login();
    return rawRequest(path, { ...options, token: getToken() });
  }
}

module.exports = {
  request,
  login,
  ensureLogin,
  getToken,
  setToken,
  rawRequest,
};
