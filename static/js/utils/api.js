/**
 * 聆心 — API 请求封装 & 统一错误处理
 * 使用方式: API.get('/path') / API.post('/path', body)
 */
window.API = (function() {
  const BASE = location.origin + '/api';
  let token = localStorage.getItem('token') || '';

  const emitter = { _handlers: {} };
  emitter.on = function(ev, fn) { (this._handlers[ev] = this._handlers[ev] || []).push(fn); };
  emitter.emit = function(ev, data) { (this._handlers[ev] || []).forEach(function(fn) { fn(data); }); };

  async function request(path, opts) {
    opts = opts || {};
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = 'Bearer ' + token;
    if (opts.headers) Object.assign(headers, opts.headers);

    let res;
    try {
      res = await fetch(BASE + path, Object.assign({}, opts, { headers: headers }));
    } catch (e) {
      const msg = '网络连接失败，请检查网络';
      emitter.emit('error', msg);
      throw new Error(msg);
    }

    if (res.status === 401) {
      emitter.emit('unauthorized');
      throw new Error('unauthorized');
    }

    let data;
    try { data = await res.json(); } catch (e) { data = null; }

    if (!res.ok) {
      var msg = (data && data.message) ? data.message : ('请求失败 (HTTP ' + res.status + ')');
      emitter.emit('error', msg);
      throw new Error(msg);
    }

    return data;
  }

  return {
    BASE: BASE,
    get: function(path, params) {
      if (params) {
        var qs = Object.keys(params).map(function(k) {
          return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]);
        }).join('&');
        path = path + '?' + qs;
      }
      return request(path);
    },
    post: function(path, body) { return request(path, { method: 'POST', body: JSON.stringify(body) }); },
    // 静默 POST：失败时不触发全局 Toast（用于后台轮询/上传，避免刷屏）
    postSilent: async function(path, body) {
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = 'Bearer ' + token;
      try {
        var r = await fetch(BASE + path, { method: 'POST', headers: headers, body: JSON.stringify(body) });
        if (r.status === 401) { emitter.emit('unauthorized'); return null; }
        return await r.json();
      } catch (e) {
        return null;
      }
    },
    put: function(path, body) { return request(path, { method: 'PUT', body: JSON.stringify(body) }); },
    del: function(path) { return request(path, { method: 'DELETE' }); },
    upload: async function(path, formData) {
      const headers = {};
      if (token) headers['Authorization'] = 'Bearer ' + token;
      try {
        var r = await fetch(BASE + path, { method: 'POST', headers: headers, body: formData });
        if (r.status === 401) { emitter.emit('unauthorized'); throw new Error('unauthorized'); }
        return r.json();
      } catch (e) {
        emitter.emit('error', e.message);
        throw e;
      }
    },
    setToken: function(t) { token = t; },
    getToken: function() { return token; },
    on: emitter.on.bind(emitter),
    emit: emitter.emit.bind(emitter)
  };
})();
