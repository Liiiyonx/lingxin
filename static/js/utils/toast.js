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

  function show(message, type) {
    var el = document.createElement('div');
    el.className = 'toast ' + (type || 'info');
    el.textContent = message;
    ensureContainer().appendChild(el);
    setTimeout(function() {
      if (el.parentNode) { el.style.opacity = '0'; el.style.transition = 'opacity 0.3s'; }
      setTimeout(function() { if (el.parentNode) el.parentNode.removeChild(el); }, 300);
    }, 3000);
  }

  return {
    success: function(m) { show(m, 'success'); },
    error: function(m) { show(m, 'error'); },
    info: function(m) { show(m, 'info'); },
    warning: function(m) { show(m, 'warning'); }
  };
})();
