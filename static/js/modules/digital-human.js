(function() {
  window.DigitalHumanModule = {
    setup: function(ctx) {
      const { ref, reactive } = Vue;
      const dhSettings = ref({ enabled: false, name: '小聆', humor: 3, style: 'humor', delay: 2 });
      const dhLogs = ref([]);
      const dhPreviewMsgs = ref([]);
      const dhPreviewInput = ref('');
      const dhPreviewLoading = ref(false);
      const dhVoiceEnabled = ref(false);
      const dhQuickQs = ['最近考试压力好大，怎么办？', '晚上总是睡不着', '和室友闹矛盾了', '感觉对未来很迷茫'];
      const contactPresence = ref(null);
      let presencePingTimer = null;

      async function loadDigitalHuman() {
        try {
          var d = await ctx.API.get('/digital-human/settings');
          if (d && d.success && d.data) {
            dhSettings.value = Object.assign({ enabled: false, name: '小聆', humor: 3, style: 'humor', delay: 2 }, d.data);
          }
        } catch (e) { console.warn('数字人设置加载失败', e); }
        loadDigitalHumanLogs();
        if (!dhPreviewMsgs.value.length) {
          dhPreviewMsgs.value.push({ role: 'ai', text: '嗨～我是' + (dhSettings.value.name || '小聆') + '，' + (ctx.currentUser.display_name || ctx.currentUser.username || '老师') + '的 AI 分身 (｡･ω･｡)ﾉ 点下方快捷问题或者直接输入，试试我的回复吧！' });
        }
      }

      async function saveDigitalHuman() {
        try {
          var d = await ctx.API.put('/digital-human/settings', dhSettings.value);
          if (d && d.success) { ctx.Toast.success('数字人设置已保存'); }
        } catch (e) { ctx.Toast.error('保存失败'); }
      }

      async function loadDigitalHumanLogs() {
        try {
          var d = await ctx.API.get('/digital-human/logs');
          if (d && d.success) dhLogs.value = d.data || [];
        } catch (e) { console.warn('数字人日志加载失败', e); }
      }

      async function markDigitalHumanLogHandled(log) {
        if (!log || log.handled) return;
        var note = window.prompt('可填写处理备注（可选）：', log.crisis ? '已联系学生并确认安全' : '');
        if (note === null) return;
        try {
          var d = await ctx.API.put('/digital-human/logs/' + log.id + '/handle', { note: note });
          if (d && d.success) {
            ctx.Toast.success('已标记处理');
            await loadDigitalHumanLogs();
          }
        } catch (e) {
          ctx.Toast.error(e.message || '处理失败，请稍后重试');
        }
      }

      async function askDigitalHuman(q) {
        var text = (q || dhPreviewInput.value || '').trim();
        if (!text || dhPreviewLoading.value) return;
        dhPreviewMsgs.value.push({ role: 'student', text: text });
        dhPreviewInput.value = '';
        dhPreviewLoading.value = true;
        try {
          var d = await ctx.API.post('/digital-human/preview', { message: text });
          if (d && d.success && d.data) {
            dhPreviewMsgs.value.push({ role: 'ai', text: d.data.reply });
            if (dhVoiceEnabled.value) speakDigitalHuman(d.data.reply);
          } else {
            dhPreviewMsgs.value.push({ role: 'ai', text: '哎呀，脑子突然卡壳了 (˶‾᷄ ⁻̫ ‾᷅˵) 稍后再试试？' });
          }
        } catch (e) {
          dhPreviewMsgs.value.push({ role: 'ai', text: '网络打了个盹 (；一_一) 稍后再试试～' });
        }
        dhPreviewLoading.value = false;
      }

      function speakDigitalHuman(text) {
        if (!('speechSynthesis' in window)) return false;
        var clean = String(text || '')
          .replace(/```[\s\S]*?```/g, ' ')
          .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
          .replace(/[*_`#>\-]/g, '')
          .replace(/\s+/g, ' ')
          .trim();
        if (!clean) return false;
        window.speechSynthesis.cancel();
        var utterance = new SpeechSynthesisUtterance(clean);
        utterance.lang = 'zh-CN';
        utterance.rate = 1;
        utterance.pitch = 1.08;
        var zhVoice = (window.speechSynthesis.getVoices() || []).find(function(v) {
          return /^zh|cmn/i.test(v.lang || '');
        });
        if (zhVoice) utterance.voice = zhVoice;
        window.speechSynthesis.speak(utterance);
        return true;
      }

      function stopDigitalHumanSpeech() {
        if ('speechSynthesis' in window) window.speechSynthesis.cancel();
      }

      async function loadContactPresence(counselorId) {
        try {
          var d = await ctx.API.get('/digital-human/status/' + counselorId);
          if (d && d.success) contactPresence.value = d.data;
          else contactPresence.value = null;
        } catch (e) { contactPresence.value = null; }
      }

      function startPresencePing() {
        if (presencePingTimer || ctx.currentUser.role === 'student') return;
        var ping = function() { ctx.API.post('/presence/ping', {}).catch(function() {}); };
        ping();
        presencePingTimer = setInterval(ping, 30000);
      }

      function stopPresencePing() {
        if (presencePingTimer) {
          clearInterval(presencePingTimer);
          presencePingTimer = null;
        }
        contactPresence.value = null;
      }

      return {
        dhSettings, dhLogs, dhPreviewMsgs, dhPreviewInput, dhPreviewLoading,
        dhVoiceEnabled, dhQuickQs, contactPresence,
        loadDigitalHuman, saveDigitalHuman, loadDigitalHumanLogs, markDigitalHumanLogHandled,
        askDigitalHuman, speakDigitalHuman, stopDigitalHumanSpeech,
        loadContactPresence, startPresencePing, stopPresencePing
      };
    }
  };
})();
