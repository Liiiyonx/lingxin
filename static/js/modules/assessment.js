(function() {
  window.AssessmentModule = {
    setup: function(ctx) {
      const { ref, computed } = Vue;
      const assessmentStep = ref(0);
      const assessmentOptions = ['完全不会', '几天', '一半以上', '几乎每天'];
      const phq9Questions = [
        { text: '做事时提不起劲或没有兴趣' }, { text: '感到心情低落、沮丧或绝望' },
        { text: '入睡困难、睡不安稳或睡眠过多' }, { text: '感觉疲倦或没有活力' },
        { text: '食欲不振或吃太多' }, { text: '觉得自己很糟，或觉得自己很失败' },
        { text: '对事物专注有困难，例如阅读或看电视' }, { text: '动作或说话速度缓慢到别人已经觉察，或正好相反' },
        { text: '有不如死掉或用某种方式伤害自己的念头' }
      ];
      const gad7Questions = [
        { text: '感觉紧张、焦虑或急切' }, { text: '不能够停止或控制担忧' },
        { text: '对各种各样的事情担忧过多' }, { text: '很难放松下来' },
        { text: '由于不安而无法静坐' }, { text: '变得容易烦恼或急躁' },
        { text: '感到似乎将有可怕的事情发生' }
      ];
      const isiQuestions = [
        { text: '入睡困难的程度' }, { text: '夜间易醒或早醒的程度' },
        { text: '比期望的时间早醒的程度' }, { text: '对自己的睡眠状况是否满意' },
        { text: '睡眠问题对日间功能的影响程度' }, { text: '他人是否注意到你的睡眠问题' },
        { text: '对睡眠问题的担忧程度' }
      ];
      const assessmentAnswers = ref(Array(23).fill(-1));
      const assessmentSubmitting = ref(false);
      const assessmentResult = ref(null);
      const assessmentHistory = ref([]);
      const assessStartTime = ref(0);

      const assessmentProgress = computed(function() {
        var answered = assessmentAnswers.value.filter(function(a) { return a >= 0; }).length;
        return Math.round(answered / 23 * 100);
      });

      const assessmentStepLabel = computed(function() {
        return ['一、抑郁状态 (PHQ-9)', '二、焦虑状态 (GAD-7)', '三、睡眠状态 (ISI)'][assessmentStep.value] || '';
      });

      const currentStepQuestions = computed(function() {
        if (assessmentStep.value === 0) return phq9Questions;
        if (assessmentStep.value === 1) return gad7Questions;
        return isiQuestions;
      });

      const currentStepStart = computed(function() {
        return assessmentStep.value === 0 ? 0 : assessmentStep.value === 1 ? 9 : 16;
      });

      function canProceedToNext() {
        var start = currentStepStart.value;
        var end = start + currentStepQuestions.value.length;
        for (var i = start; i < end; i++) {
          if (assessmentAnswers.value[i] < 0) return false;
        }
        return true;
      }

      function goToNextStep() {
        if (!canProceedToNext()) { ctx.Toast.warning('请完成当前部分的所有题目'); return; }
        if (assessmentStep.value < 2) assessmentStep.value++;
      }

      function goToPrevStep() {
        if (assessmentStep.value > 0) assessmentStep.value--;
      }

      function initAssessment() {
        assessmentAnswers.value = Array(23).fill(-1);
        assessmentResult.value = null;
        assessmentStep.value = 0;
        assessStartTime.value = Date.now();
        loadAssessmentHistory();
      }

      async function submitAssessment() {
        var duration = Math.floor((Date.now() - assessStartTime.value) / 1000);
        assessmentSubmitting.value = true;
        var answers = [];
        for (var i = 0; i < 23; i++) { answers.push({ q: i + 1, a: assessmentAnswers.value[i] }); }
        try {
          var d = await ctx.API.post('/assessment/submit', { answers: answers, duration_seconds: duration });
          if (d.success) { assessmentResult.value = d.data; loadAssessmentHistory(); ctx.Toast.success('测评完成'); }
          else { ctx.Toast.error(d.message || '提交失败'); }
        } catch (e) { console.error('提交测评失败', e); }
        assessmentSubmitting.value = false;
      }

      function resetAssessment() { assessmentResult.value = null; initAssessment(); }

      async function crisisReport() {
        if (!confirm('确认要上报心理危机吗？辅导员与心理中心将尽快联系你。\n\n如有紧急危险，请立即拨打 120 / 110 或心理援助热线 400-161-9995。')) return;
        try {
          var d = await ctx.API.post('/crisis/report', { reason: '学生主动求助' });
          if (d && d.success) {
            ctx.Toast.success(d.message || '危机已上报');
            if (d.data && d.data.hotline) ctx.Toast.info('📞 ' + d.data.hotline);
            if (ctx.currentUser.role === 'student') { ctx.page.value = 'studentChat'; ctx.loadMessageContacts(); }
          } else {
            ctx.Toast.error(d.message || '上报失败');
          }
        } catch (e) { console.error('危机上报失败', e); }
      }

      async function loadAssessmentHistory() {
        try { var d = await ctx.API.get('/assessment/history'); assessmentHistory.value = d.data || []; }
        catch (e) { console.warn('测评历史加载失败', e); }
      }

      return {
        assessmentStep, assessmentOptions, phq9Questions, gad7Questions, isiQuestions,
        assessmentAnswers, assessmentSubmitting, assessmentResult, assessmentHistory,
        assessStartTime, assessmentProgress, assessmentStepLabel, currentStepQuestions, currentStepStart,
        canProceedToNext, goToNextStep, goToPrevStep, initAssessment, submitAssessment,
        resetAssessment, crisisReport, loadAssessmentHistory
      };
    }
  };
})();
