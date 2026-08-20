(function() {
  window.StudentHomeModule = {
    setup: function(ctx) {
      const { ref, reactive, computed, nextTick } = Vue;
      const API = ctx.API;
      const Toast = ctx.Toast;
      const Helpers = ctx.Helpers;
      const currentUser = ctx.currentUser;
      const isDarkMode = ctx.isDarkMode;
      const ensureChart = ctx.ensureChart;

      // ==================== 学生端 Widget ====================
      const QUOTES = [
        { text: '教育不是灌满一桶水，而是点燃一把火。', author: '叶芝' },
        { text: '每一个不曾起舞的日子，都是对生命的辜负。', author: '尼采' },
        { text: '你生而不可限量，你生而心怀梦想。', author: '米歇尔·奥巴马' },
        { text: '最大的荣耀不在于从不跌倒，而在于每次跌倒后都能爬起来。', author: '曼德拉' },
        { text: '生活不止眼前的苟且，还有诗和远方。', author: '高晓松' },
        { text: '知人者智，自知者明。胜人者有力，自胜者强。', author: '老子' },
        { text: '千里之行，始于足下。', author: '老子' },
        { text: '学而不思则罔，思而不学则殆。', author: '孔子' },
        { text: '天行健，君子以自强不息。', author: '周易' },
        { text: '路漫漫其修远兮，吾将上下而求索。', author: '屈原' },
        { text: '世上无难事，只要肯登攀。', author: '毛泽东' },
        { text: 'Stay hungry, stay foolish.', author: '乔布斯' }
      ];
      const WORDS = [
        { word: 'Resilience', phonetic: '/rɪˈzɪliəns/', meaning: 'n. 韧性，恢复力；适应力', sentence: 'She showed great resilience in overcoming difficulties.' },
        { word: 'Ephemeral', phonetic: '/ɪˈfemərəl/', meaning: 'adj. 短暂的，转瞬即逝的', sentence: 'The beauty of cherry blossoms is ephemeral yet profound.' },
        { word: 'Serendipity', phonetic: '/ˌserənˈdɪpəti/', meaning: 'n. 意外发现珍奇事物的本领', sentence: 'Finding this book was pure serendipity.' },
        { word: 'Perseverance', phonetic: '/ˌpɜːrsəˈvɪrəns/', meaning: 'n. 坚持不懈，毅力', sentence: 'Perseverance is the key to success.' },
        { word: 'Empathy', phonetic: '/ˈempəθi/', meaning: 'n. 同理心，共鸣', sentence: 'A good counselor needs empathy and patience.' },
        { word: 'Paradigm', phonetic: '/ˈpærədaɪm/', meaning: 'n. 典范，范式', sentence: 'This discovery marks a paradigm shift in science.' },
        { word: 'Eloquent', phonetic: '/ˈeləkwənt/', meaning: 'adj. 雄辩的，有口才的', sentence: 'She gave an eloquent speech at the ceremony.' },
        { word: 'Tenacious', phonetic: '/təˈneɪʃəs/', meaning: 'adj. 坚韧不拔的，顽强的', sentence: 'His tenacious spirit helped him overcome the odds.' }
      ];
      const MOOD_LABELS = { happy: '今天心情不错！保持这份好心情 😊', calm: '内心平静，岁月安好 🌿', neutral: '平常的一天，也是珍贵的一天', down: '偶尔的低落也没关系，给自己一点温暖', anxious: '别担心，一切都会好起来的 💪' };

      const waterCount = ref(0);
      const waterProgress = computed(function() { return waterCount.value / 8; });
      const dailyQuote = ref(QUOTES[new Date().getDate() % QUOTES.length]);
      const dailyWord = ref(WORDS[new Date().getDate() % WORDS.length]);
      const todayMood = ref('');
      const todayMoodText = computed(function() { return MOOD_LABELS[todayMood.value] || '点击记录今天的心情吧 🌈'; });
      const todayStr = computed(function() { return Helpers.todayStr(); });
      const greetingText = computed(function() {
        var h = new Date().getHours();
        return h < 6 ? '夜深了，注意休息 🌙' : h < 9 ? '早上好 ☀️' : h < 12 ? '上午好 🌤️' : h < 14 ? '中午好 ☀️' : h < 18 ? '下午好 🌈' : '晚上好 🌙';
      });

      const studentTrendChart = ref(null);
      const studentTrendLoading = ref(false);
      const studentTrendData = ref([]);
      const studentTrendSummary = reactive({ total: 0, avgIntensity: 0, highCount: 0 });
      let studentTrendInst = null;

      function renderStudentTrend() {
        if (typeof echarts === 'undefined') {
          window._loadECharts && window._loadECharts(renderStudentTrend);
          return;
        }
        if (!studentTrendChart.value) return;
        studentTrendInst = ensureChart(studentTrendInst, studentTrendChart.value, isDarkMode.value);
        var data = studentTrendData.value || [];
        var labels = data.map(function(item) { return item.date || item.day || ''; });
        var values = data.map(function(item) { return Number(item.avg_intensity || 0); });
        studentTrendInst.setOption({
          tooltip: {
            trigger: 'axis',
            formatter: function(params) {
              var p = params && params[0];
              if (!p) return '';
              return p.axisValue + '<br/>平均情绪强度：' + (p.value || 0) + '/10';
            }
          },
          grid: { top: 20, right: 18, bottom: 28, left: 42 },
          xAxis: { type: 'category', data: labels, axisLabel: { fontSize: 10 } },
          yAxis: { type: 'value', min: 0, max: 10, interval: 2, axisLabel: { fontSize: 10 } },
          series: [{
            name: '平均情绪强度',
            type: 'line',
            smooth: true,
            data: values,
            symbol: 'circle',
            symbolSize: 7,
            lineStyle: { color: '#6366f1', width: 3 },
            itemStyle: { color: '#6366f1' },
            areaStyle: {
              color: {
                type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                colorStops: [
                  { offset: 0, color: 'rgba(99,102,241,0.32)' },
                  { offset: 1, color: 'rgba(99,102,241,0.02)' }
                ]
              }
            }
          }]
        }, { notMerge: true });
      }

      async function loadStudentTrend() {
        if (currentUser.role !== 'student') return;
        studentTrendLoading.value = true;
        try {
          var d = await API.get('/emotion/trends', { days: 14, student_id: currentUser.id });
          var rows = (d && d.data) ? d.data : [];
          studentTrendData.value = rows;
          var total = 0, avgSum = 0, avgCount = 0, highCount = 0;
          rows.forEach(function(item) {
            var count = Number(item.count || 0);
            var avg = Number(item.avg_intensity || 0);
            total += count;
            if (avg) { avgSum += avg; avgCount += 1; }
            if (avg >= 7) highCount += 1;
          });
          studentTrendSummary.total = total;
          studentTrendSummary.avgIntensity = avgCount ? Math.round((avgSum / avgCount) * 10) / 10 : 0;
          studentTrendSummary.highCount = highCount;
          nextTick(renderStudentTrend);
        } catch (e) {
          studentTrendData.value = [];
          studentTrendSummary.total = 0;
          studentTrendSummary.avgIntensity = 0;
          studentTrendSummary.highCount = 0;
        } finally {
          studentTrendLoading.value = false;
        }
      }

      function loadWater() { var today = new Date().toISOString().split('T')[0]; var saved = localStorage.getItem('water_' + today); waterCount.value = saved ? parseInt(saved) : 0; }
      function addWater() {
        if (waterCount.value < 8) { waterCount.value++; var today = new Date().toISOString().split('T')[0]; localStorage.setItem('water_' + today, waterCount.value); Toast.success('+1 杯水！继续加油 💧'); }
      }
      function resetWater() { waterCount.value = 0; var today = new Date().toISOString().split('T')[0]; localStorage.setItem('water_' + today, '0'); Toast.info('今日饮水已重置'); }
      function loadMood() { var today = new Date().toISOString().split('T')[0]; var saved = localStorage.getItem('mood_' + today); todayMood.value = saved || ''; }
      function recordMood(mood) { todayMood.value = mood; var today = new Date().toISOString().split('T')[0]; localStorage.setItem('mood_' + today, mood); Toast.success('心情已记录！'); }
      function autoResize(e) { var el = e.target; el.style.height = 'auto'; el.style.height = Math.min(100, el.scrollHeight) + 'px'; }

      // 表情列表
      const emojiList = ['😀','😂','🤣','😊','😍','🥰','😘','😜','🤔','😐','😢','😭','😡','😱','👍','👎','👏','💪','🙏','❤️','💔','🔥','⭐','🎉','🎊','🌸','🌺','☀️','🌈','💧','🍀','🐵','🐶','🐱','🦊','🐼','🐨','🐧','💻','📱','📚','✏️','💡','🏠','🎓','🏆','⚽','🍕','🍦','☕','🚀','✨','💯','✅','❌','❓','💤','👋','🤝'];


      return {
        waterCount, waterProgress, addWater, resetWater, loadWater,
        dailyQuote, dailyWord, todayMood, todayMoodText,
        loadMood, recordMood, todayStr, greetingText,
        studentTrendChart, studentTrendLoading, studentTrendSummary, loadStudentTrend,
        emojiList, autoResize
      };
    }
  };
})();
