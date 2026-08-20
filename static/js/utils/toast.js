/**
 * 聆心 — Toast 通知系统
 * 使用方式: Toast.success('操作成功') / Toast.error('操作失败') / Toast.info('提示')
 */
window.Toast = (function() {
  var container = null;

  function ensureContainer() {
    if (!container) {
      container = document.createElement('div');
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    return container;
  }

  function show(message, type, actionLabel, actionFn) {
    var el = document.createElement('div');
    el.className = 'toast ' + (type || 'info');
    el.textContent = message;
    if (actionLabel && typeof actionFn === 'function') {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = actionLabel;
      btn.style.cssText = 'display:block;margin-top:8px;margin-left:auto;padding:4px 10px;border:1px solid rgba(255,255,255,.65);border-radius:6px;background:rgba(255,255,255,.14);color:#fff;font-size:12px;font-weight:600;cursor:pointer';
      btn.addEventListener('click', function() {
        actionFn();
        if (el.parentNode) el.parentNode.removeChild(el);
      });
      el.appendChild(btn);
    }
    ensureContainer().appendChild(el);
    setTimeout(function() {
      if (el.parentNode) { el.style.opacity = '0'; el.style.transition = 'opacity 0.3s'; }
      setTimeout(function() { if (el.parentNode) el.parentNode.removeChild(el); }, 300);
    }, 3000);
  }

  return {
    success: function(m) { show(m, 'success'); },
    error: function(m, actionLabel, actionFn) { show(m, 'error', actionLabel, actionFn); },
    info: function(m) { show(m, 'info'); },
    warning: function(m) { show(m, 'warning'); }
  };
})();
