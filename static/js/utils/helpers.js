/**
 * 聆心 — 通用工具函数
 */
window.Helpers = {
  // 情绪颜色映射
  emoColor: function(e) {
    var m = { 正常:'#10b981',高兴:'#3b82f6',低落:'#94a3b8',焦虑:'#f59e0b',烦躁:'#ef4444',压抑:'#8b5cf6',愤怒:'#e74c3c',恐惧:'#8e44ad',惊讶:'#f39c12',厌恶:'#7f8c8d',悲伤:'#1e293b',紧张:'#e67e22',平静:'#3b82f6' };
    return m[e] || '#94a3b8';
  },
  // 风险背景色
  riskBg: function(l) { return { high:'#ef4444', medium:'#f59e0b', low:'#10b981', none:'#94a3b8' }[l] || '#94a3b8'; },
  // 风险标签
  riskLbl: function(l) { return { high:'高风险', medium:'中风险', low:'低风险', none:'正常' }[l] || l; },
  // Markdown渲染
  renderMd: function(text) {
    if (!text) return '';
    if (typeof marked !== 'undefined' && marked && marked.parse) {
      try { return marked.parse(text); } catch(e) {}
    }
    return text.replace(/\n/g, '<br>');
  },
  // 时间格式化
  formatTime: function(ts) {
    if (!ts) return '';
    var d = new Date(ts);
    return ('0'+d.getHours()).slice(-2) + ':' + ('0'+d.getMinutes()).slice(-2);
  },
  // 防抖
  debounce: function(fn, delay) {
    var timer;
    return function() {
      var ctx = this, args = arguments;
      clearTimeout(timer);
      timer = setTimeout(function() { fn.apply(ctx, args); }, delay);
    };
  },
  // 当前日期
  todayStr: function() {
    var d = new Date();
    var w = ['日','一','二','三','四','五','六'];
    return d.getFullYear()+'年'+(d.getMonth()+1)+'月'+d.getDate()+'日 星期'+w[d.getDay()];
  }
};
