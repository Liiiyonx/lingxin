/**
 * 聆心 — 通用工具函数
 */
window.Helpers = {
  // 情绪颜色映射（单一数据源：优先取 EmotionFusionEngine，前端统一颜色）
  emoColor: function(e) {
    if (window.EmotionFusionEngine && window.EmotionFusionEngine.emotionColor) {
      return window.EmotionFusionEngine.emotionColor(e);
    }
    var m = { 高兴:'#10b981',正常:'#94a3b8',平静:'#3b82f6',焦虑:'#f59e0b',恐惧:'#ef4444',愤怒:'#ef4444',悲伤:'#6366f1',压抑:'#8b5cf6',紧张:'#e67e22',惊讶:'#f39c12',烦躁:'#f97316',低落:'#94a3b8',厌恶:'#7f8c8d' };
    return m[e] || '#94a3b8';
  },
  // 风险背景色
  riskBg: function(l) { return { high:'#ef4444', medium:'#f59e0b', low:'#10b981', none:'#94a3b8' }[l] || '#94a3b8'; },
  // 风险标签
  riskLbl: function(l) {
    return { high:'高风险', medium:'中风险', low:'低风险', none:'正常', critical:'危急风险' }[l] || l;
  },
  escapeHtml: function(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  },
  // Markdown渲染
  renderMd: function(text) {
    if (!text) return '';
    if (typeof marked !== 'undefined' && marked && marked.parse && typeof DOMPurify !== 'undefined' && DOMPurify) {
      try {
        var html = marked.parse(text);
        return DOMPurify.sanitize(html);
      } catch(e) {}
    }
    return this.escapeHtml(text).replace(/\n/g, '<br>');
  },
  // 时间格式化
  formatTime: function(ts) {
    if (!ts) return '';
    var d = new Date(ts);
    return ('0'+d.getHours()).slice(-2) + ':' + ('0'+d.getMinutes()).slice(-2);
  },
  formatDateTime: function(ts) {
    if (!ts) return '';
    var d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    var pad = function(n) { return String(n).padStart(2, '0'); };
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  },
  sourceLbl: function(source) {
    return {
      assessment: '心理测评',
      talk_report: '谈心记录',
      video_call_summary: '视频通话',
      digital_human: '数字人对话',
      alert_resolution: '预警处置',
      manual: '人工调整',
      reminder_done: '提醒完成',
      todo_done: '待办完成',
      legacy_update: '旧接口回写',
      unknown: '系统',
    }[source] || source || '系统';
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
