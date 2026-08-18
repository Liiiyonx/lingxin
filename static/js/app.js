/**
 * 聆心 v3.1 — 主应用入口
 * 依赖: Vue 3 CDN, ECharts, Socket.IO, marked, face-api.js
 * 工具模块: API, Toast, Icons, Helpers (全局)
 * 实时模块: FaceEmotionDetector, VoiceProsodyAnalyzer, EmotionFusionEngine (全局)
 */
(function() {
  const { createApp, ref, reactive, computed, onMounted, nextTick, watch } = Vue;

  createApp({
    setup() {
      // ==================== 认证状态 ====================
      const isLoggedIn = ref(!!localStorage.getItem('token'));
      const loginForm = reactive({ username: '', password: '' });
      const loginLoading = ref(false);
      const currentUser = reactive({ username: '', display_name: '', role: '', name: '', student_id: '', college: '', class_name: '' });
      const roleLabel = computed(function() {
        return { super_admin: '超级管理员', student_affairs: '学工处', counselor: '老师', student: '学生' }[currentUser.role] || '';
      });
      const loginType = ref('staff');
      const showStudentRegister = ref(false);
      const studentLoginForm = reactive({ student_id: '', password: '' });
      const studentRegisterForm = reactive({ student_id: '', name: '', password: '', confirmPassword: '' });
      // 测试账号列表（登录页动态渲染，来自 /system/test-accounts，避免硬编码错位）
      const testAccounts = ref({ staff: [], counselors: [] });

      function fillStaffAccount(u) {
        loginForm.username = u.username;
        loginForm.password = u.role === 'super_admin' ? 'admin123' : 'staff123';
      }
      function fillCounselorAccount(u) {
        loginForm.username = u.username;
        loginForm.password = 'counsel123';
      }
      function fillStudentAccount(s) {
        studentLoginForm.student_id = s.student_id;
        studentLoginForm.password = '123456';
      }
      async function loadTestAccounts() {
        try {
          var d = await API.get('/system/test-accounts');
          if (d && d.success && d.data) testAccounts.value = d.data;
        } catch (e) { /* silent */ }
      }

      // ==================== 主题 ====================
      const isDarkMode = ref(localStorage.getItem('theme') === 'dark');
      function toggleTheme() {
        isDarkMode.value = !isDarkMode.value;
        document.documentElement.setAttribute('data-theme', isDarkMode.value ? 'dark' : '');
        localStorage.setItem('theme', isDarkMode.value ? 'dark' : 'light');
        if (networkGraphInst) networkGraphInst.setTheme(isDarkMode.value);
      }
      if (isDarkMode.value) document.documentElement.setAttribute('data-theme', 'dark');

      // ==================== 侧边栏 ====================
      const sidebarCollapsed = ref(false);
      const sidebarMobileOpen = ref(false);
      function toggleSidebar() {
        if (window.innerWidth <= 768) sidebarMobileOpen.value = !sidebarMobileOpen.value;
        else sidebarCollapsed.value = !sidebarCollapsed.value;
      }

      // ==================== 页面路由 ====================
      // 默认页：辅导员→工作台，管理员/学工处→情绪看板，学生→首页
      const defaultPage = function() {
        var r = currentUser.role;
        if (r === 'super_admin' || r === 'student_affairs') return 'emotionBoard';
        if (r === 'counselor') return 'dashboard';
        return 'studentHome';
      };
      const page = ref(defaultPage());
      const pageTitle = computed(function() {
        var m = {
          dashboard: '今日工作台', teacherChat: '师生对话', classMeeting: '班会策划',
          docWriting: '公文写作', alerts: '风险预警', knowledge: '知识库', system: '系统管理',
          students: '学生管理', emotionBoard: '情绪看板', emotionNetwork: '情绪网络图', reminders: '提醒中心',
          studentHome: '我的首页', studentChat: '联系老师', studentAssessment: '心理测评',
          studentAppointment: '预约咨询', studentProfile: '个人中心'
        };
        return m[page.value] || '聆心';
      });

      // ==================== Toast ====================
      const toasts = ref([]);
      function showToast(msg, type) {
        var t = { message: msg, type: type || 'success', id: Date.now() };
        toasts.value.push(t);
        setTimeout(function() {
          var i = toasts.value.indexOf(t);
          if (i > -1) toasts.value.splice(i, 1);
        }, 3500);
      }

      // ==================== 登录 ====================
      async function handleLogin() {
        loginLoading.value = true;
        try {
          var d = await API.post('/auth/login', loginForm);
          if (d.success && d.data && d.data.token) {
            setSession(d.data.token, d.data.user);
            localStorage.setItem('user_type', 'staff');
            isLoggedIn.value = true;
            // 管理员/学工处→情绪看板，辅导员→工作台
            page.value = (d.data.user.role === 'super_admin' || d.data.user.role === 'student_affairs')
              ? 'emotionBoard' : 'dashboard';
            if (page.value === 'dashboard') { loadDash(); loadWorkplan(); }
            if (page.value === 'emotionBoard') { loadEmotionDashboard(); }
            setRole();
            initSocket();
            if (currentUser.role === 'counselor') initTeacherVideo();
          } else if (d.token) {
            setSession(d.token, d.user || {});
            localStorage.setItem('user_type', 'staff');
            isLoggedIn.value = true;
            var urole = (d.user || {}).role;
            page.value = (urole === 'super_admin' || urole === 'student_affairs') ? 'emotionBoard' : 'dashboard';
            if (page.value === 'dashboard') { loadDash(); loadWorkplan(); }
            if (page.value === 'emotionBoard') { loadEmotionDashboard(); }
            setRole();
            initSocket();
            if (currentUser.role === 'counselor') initTeacherVideo();
          } else {
            Toast.error(d.message || '登录失败，请检查用户名和密码');
          }
        } catch (e) { if (e.message !== 'unauthorized') Toast.error('服务连接失败，请确认服务器已启动'); }
        loginLoading.value = false;
      }

      async function handleStudentLogin() {
        loginLoading.value = true;
        try {
          var d = await API.post('/student/login', studentLoginForm);
          if (d.success && d.data && d.data.token) {
            setSession(d.data.token, d.data.user);
            localStorage.setItem('user_type', 'student');
            currentUser.role = 'student';
            if (d.data.user && d.data.user.name) {
              currentUser.display_name = d.data.user.name;
              currentUser.username = d.data.user.name;
            }
            isLoggedIn.value = true;
            setRole();
            // 先切换页面→watch自动触发数据加载，避免重复调用
            page.value = 'studentHome';
            // Socket在后台初始化，不阻塞渲染
            setTimeout(function(){ initSocket(); initStudentVideo(); }, 100);
          } else { Toast.error(d.message || '登录失败，请检查学号和密码'); }
        } catch (e) { if (e.message !== 'unauthorized') Toast.error('服务连接失败，请确认服务器已启动'); }
        loginLoading.value = false;
      }

      async function handleStudentRegister() {
        if (studentRegisterForm.password !== studentRegisterForm.confirmPassword) {
          Toast.error('两次密码输入不一致'); return;
        }
        if (studentRegisterForm.password.length < 6) {
          Toast.error('密码长度至少6位'); return;
        }
        loginLoading.value = true;
        try {
          var d = await API.post('/student/register', {
            student_id: studentRegisterForm.student_id,
            name: studentRegisterForm.name,
            password: studentRegisterForm.password
          });
          if (d.success && d.data && d.data.token) {
            setSession(d.data.token, d.data.user);
            localStorage.setItem('user_type', 'student');
            currentUser.role = 'student';
            isLoggedIn.value = true;
            page.value = 'studentHome';
            setRole();
            setTimeout(function(){ initSocket(); initStudentVideo(); }, 100);
          } else { Toast.error(d.message || '注册失败'); }
        } catch (e) { Toast.error('网络连接失败'); }
        loginLoading.value = false;
      }

      function resetCurrentUser() {
        Object.assign(currentUser, {
          username: '', display_name: '', role: '', name: '',
          student_id: '', college: '', class_name: '', id: null
        });
      }

      function setSession(token, user) {
        var normalizedUser = Object.assign({}, user || {});
        if (normalizedUser.name && !normalizedUser.display_name) normalizedUser.display_name = normalizedUser.name;
        if (normalizedUser.name && !normalizedUser.username) normalizedUser.username = normalizedUser.name;
        localStorage.setItem('token', token);
        localStorage.setItem('current_user', JSON.stringify(normalizedUser));
        API.setToken(token);
        // Keep student profile fields from the login response.
        resetCurrentUser();
        Object.assign(currentUser, normalizedUser);
      }

      function restoreSessionUser() {
        try {
          var saved = JSON.parse(localStorage.getItem('current_user') || '{}');
          if (saved && Object.keys(saved).length) Object.assign(currentUser, saved);
        } catch (e) { localStorage.removeItem('current_user'); }
      }

      function handleLogout() {
        localStorage.removeItem('token');
        localStorage.removeItem('user_type');
        localStorage.removeItem('current_user');
        API.setToken('');
        resetCurrentUser();
        isLoggedIn.value = false;
        loginType.value = 'staff';
        stopAllRealtime();
      }

      function setRole() {
        var r = currentUser.role;
        document.documentElement.setAttribute('data-role',
          r === 'student' ? 'student' : r === 'super_admin' ? 'super_admin' : 'counselor');
      }

      // ==================== API 错误监听 ====================
      API.on('unauthorized', function() { handleLogout(); });
      API.on('error', function(msg) { Toast.error(msg); });

      // ==================== 工作台 ====================
      const wp = reactive({
        date: '', weekday: '', todo_list: [], todo_count: 0,
        calendar_events: [], student_summary: { total: 0, high_risk: 0, medium_risk: 0, low_risk: 0 },
        pending_reminders: 0
      });
      const wpCalYear = ref(new Date().getFullYear());
      const wpCalMonth = ref(new Date().getMonth() + 1);
      const calDayDetail = reactive({ show: false, date: '', items: [] });
      const showAddTodo = ref(false);
      const newTodo = reactive({ title: '', category: 'work_task', priority: 'medium', due_date: '', description: '' });

      const wpCalRows = computed(function() {
        var year = wpCalYear.value, month = wpCalMonth.value;
        var first = new Date(year, month - 1, 1);
        var last = new Date(year, month, 0);
        var days = [];
        for (var i = 0; i < first.getDay(); i++) days.push(null);
        for (var d = 1; d <= last.getDate(); d++) days.push(d);
        var today = new Date();
        var todayStr = today.getFullYear() + '-' + ('0' + (today.getMonth() + 1)).slice(-2) + '-' + ('0' + today.getDate()).slice(-2);
        var rows = [];
        for (var i = 0; i < days.length; i += 7) {
          var row = [];
          for (var j = 0; j < 7; j++) {
            var day = days[i + j];
            if (!day) { row.push(null); continue; }
            var ds = year + '-' + ('0' + month).slice(-2) + '-' + ('0' + day).slice(-2);
            var events = (wp.calendar_events || []).filter(function(e) { return e.date === ds; });
            row.push({ day: day, isToday: ds === todayStr, events: events });
          }
          rows.push(row);
        }
        return rows;
      });

      const wpTodoStudent = computed(function() {
        return (wp.todo_list || []).filter(function(t) { return t.category === 'student_care'; });
      });
      const wpTodoWork = computed(function() {
        return (wp.todo_list || []).filter(function(t) { return t.category === 'work_task' || t.category === 'other'; });
      });

      async function loadWorkplan() {
        try {
          var d = await API.get('/workplan/today');
          if (d && d.data) Object.assign(wp, d.data);
        } catch (e) { /* silent */ }
      }

      async function loadDash() {
        try {
          var d = await API.get('/system/dashboard');
          if (d) { Object.assign(dash, d); setTimeout(renderCharts, 400); }
        } catch (e) { /* silent */ }
        try {
          var a = await API.get('/alert/list', { limit: 5 });
          recentAlerts.value = a.data || a.items || [];
        } catch (e) { /* silent */ }
      }

      function wpCalPrev() {
        if (wpCalMonth.value === 1) { wpCalMonth.value = 12; wpCalYear.value--; }
        else wpCalMonth.value--;
        loadWorkplan();
      }
      function wpCalNext() {
        if (wpCalMonth.value === 12) { wpCalMonth.value = 1; wpCalYear.value++; }
        else wpCalMonth.value++;
        loadWorkplan();
      }
      async function wpSelectDay(day) {
        var ds = wpCalYear.value + '-' + ('0' + wpCalMonth.value).slice(-2) + '-' + ('0' + day).slice(-2);
        calDayDetail.date = ds; calDayDetail.show = true;
        try { var d = await API.get('/workplan/day/' + ds); calDayDetail.items = d.data || []; }
        catch (e) { calDayDetail.items = []; }
      }
      async function addCustomTodo() {
        if (!newTodo.title.trim()) { Toast.error('请输入待办标题'); return; }
        try {
          await API.post('/workplan/todo/add', newTodo);
          Toast.success('待办已添加');
          newTodo.title = ''; newTodo.description = '';
          showAddTodo.value = false; loadWorkplan();
        } catch (e) { Toast.error('添加失败'); }
      }
      async function completeCustomTodo(tid) {
        var id = String(tid).replace('todo_', '');
        try { await API.put('/workplan/todo/' + id + '/complete'); Toast.success('已完成'); loadWorkplan(); }
        catch (e) { Toast.error('操作失败'); }
      }
      async function wpCompleteTodo(rid) {
        try { await API.put('/workplan/complete/' + rid); Toast.success('已完成'); loadWorkplan(); }
        catch (e) { Toast.error('操作失败'); }
      }

      // ==================== 仪表盘 ====================
      const dash = reactive({ conversations: 0, emotions: 0, alerts_pending: 0, knowledge_docs: 0, emotion_distribution: {}, risk_distribution: {}, trend_data: [] });
      const recentAlerts = ref([]);
      const cPie = ref(null), cTrend = ref(null), cRisk = ref(null);
      let pieChart = null, trendChart = null, riskChart = null;

      function renderCharts() {
        if (typeof echarts === 'undefined') { window._loadECharts && window._loadECharts(function(){renderCharts();}); return; }
        try {
          if (cPie.value) {
            if (pieChart) pieChart.dispose();
            pieChart = echarts.init(cPie.value, isDarkMode.value ? 'dark' : undefined);
            var dist = dash.emotion_distribution || {};
            var data = Object.entries(dist).map(function(e) { return { name: e[0], value: e[1] }; });
            pieChart.setOption({
              tooltip: { trigger: 'item' },
              series: [{ type: 'pie', radius: ['40%', '70%'], label: { show: true, fontSize: 11 },
                data: data.length ? data : [{ name: '暂无数据', value: 1 }],
                color: ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#3b82f6']
              }]
            });
          }
        } catch (e) { /* silent */ }
      }

      // ==================== 学生管理 ====================
      const students = ref([]);
      const studentSearch = ref('');
      const showAddStudent = ref(false);
      const newStudent = reactive({ student_id: '', name: '', gender: '', college: '', class_name: '', phone: '', notes: '' });
      const selectedStudent = ref(null);
      const studentProfiles = ref([]);

      const searchStudentsDebounced = Helpers.debounce(async function() {
        try {
          var d = await API.get('/student/list', { search: studentSearch.value, per_page: 100 });
          students.value = d.data || [];
        } catch (e) { /* silent */ }
      }, 300);

      async function loadStudents() { searchStudentsDebounced(); }

      async function addStudent() {
        try {
          await API.post('/student/add', newStudent);
          Toast.success('学生添加成功');
          showAddStudent.value = false;
          Object.assign(newStudent, { student_id: '', name: '', gender: '', college: '', class_name: '', phone: '', notes: '' });
          loadStudents();
        } catch (e) { Toast.error('添加失败'); }
      }

      async function viewStudent(sid) {
        try {
          var d = await API.get('/student/' + sid);
          selectedStudent.value = d.data;
          var p = await API.get('/student/' + sid + '/profiles');
          studentProfiles.value = p.data || [];
        } catch (e) { Toast.error('获取详情失败'); }
      }

      async function updateStudentNotes(sid, notes) {
        try { await API.put('/student/' + sid, { notes: notes }); Toast.success('备注已更新'); }
        catch (e) { /* silent */ }
      }

      // ==================== 预警 ====================
      const alerts = ref([]);
      async function loadAlerts() {
        try { var d = await API.get('/alert/list'); alerts.value = d.data || d.items || []; }
        catch (e) { /* silent */ }
      }
      async function ackAlert(id) {
        await API.put('/alert/' + id + '/acknowledge');
        loadAlerts();
      }

      // ==================== 提醒 ====================
      const reminders = ref([]);
      const showCompleted = ref(false);
      async function loadReminders() {
        try { var d = await API.get('/student/reminder/list'); reminders.value = d.data || []; }
        catch (e) { /* silent */ }
      }
      async function completeReminder(rid) {
        try { await API.put('/student/reminder/' + rid + '/complete'); Toast.success('提醒已完成'); loadReminders(); }
        catch (e) { Toast.error('操作失败'); }
      }

      // ==================== 班会/公文 ====================
      const meetingTheme = ref(''), meetingResult = ref(''), meetingLoading = ref(false);
      async function generateMeeting() {
        if (!meetingTheme.value.trim()) return;
        meetingLoading.value = true;
        try {
          var d = await API.post('/conversation/organize', { scene: '班会策划', content: meetingTheme.value });
          meetingResult.value = d.content || d.result || '生成失败';
        } catch (e) { meetingResult.value = '请求失败'; }
        meetingLoading.value = false;
      }

      const docType = ref('通知'), docContent = ref(''), docResult = ref(''), docLoading = ref(false);
      async function generateDoc() {
        if (!docContent.value.trim()) return;
        docLoading.value = true;
        try {
          var d = await API.post('/conversation/organize', { scene: '公文写作', content: '文种：' + docType.value + '\n\n内容：' + docContent.value });
          docResult.value = d.content || d.result || '生成失败';
        } catch (e) { docResult.value = '请求失败'; }
        docLoading.value = false;
      }

      // ==================== 知识库 ====================
      const kbStats = ref(null);
      async function loadKbStats() {
        try { var d = await API.get('/knowledge/stats'); if (d && d.data) kbStats.value = d.data; }
        catch (e) { /* silent */ }
      }
      async function uploadDoc(e) {
        var f = e.target.files[0]; if (!f) return;
        var fd = new FormData(); fd.append('file', f);
        try { var d = await API.upload('/knowledge/upload', fd); Toast.success(d.message || '上传成功'); loadKbStats(); }
        catch (e) { Toast.error('上传失败'); }
      }

      // ==================== 情绪看板 ====================
      const emoDashStats = reactive({ total: 0, highRisk: 0, mediumRisk: 0, avgIntensity: 0 });
      const emoDashAlerts = ref([]);
      const realtimeEmotionLogs = ref([]);
      const emoPieChart = ref(null), emoRiskChart = ref(null), emoTrendChart = ref(null), emoHeatmapChart = ref(null);
      let emoPieInst = null, emoRiskInst = null, emoTrendInst = null, emoHeatInst = null;

      async function loadEmotionDashboard() {
        try {
          var s = await API.get('/emotion/statistics');
          if (s && s.data) {
            emoDashStats.total = s.data.total || 0;
            emoDashStats.highRisk = s.data.high_risk_count || 0;
            emoDashStats.mediumRisk = s.data.medium_risk_count || 0;
            emoDashStats.avgIntensity = s.data.avg_intensity || 0;
          }
        } catch (e) { /* silent */ }
        try { var a = await API.get('/alert/list', { per_page: 10 }); emoDashAlerts.value = a.data || a.items || []; }
        catch (e) { /* silent */ }
        try { var logs = await API.get('/emotion/logs', { per_page: 12 }); realtimeEmotionLogs.value = logs.data || []; }
        catch (e) { /* silent */ }
        await nextTick();
        renderEmoCharts();
      }


      async function seedRealtimeDemoData() {
        try {
          var d = await API.post('/emotion/seed-demo', {});
          Toast.success((d && d.message) || '\u6f14\u793a\u6570\u636e\u5df2\u8f7d\u5165');
          await loadEmotionDashboard();
        } catch (e) {
          Toast.error('\u6f14\u793a\u6570\u636e\u8f7d\u5165\u5931\u8d25');
        }
      }

      function renderEmoCharts() {
        if (typeof echarts === 'undefined') { window._loadECharts && window._loadECharts(function(){renderEmoCharts();}); return; }
        var isDark = isDarkMode.value;
        // Pie
        if (emoPieChart.value) {
          if (emoPieInst) emoPieInst.dispose();
          emoPieInst = echarts.init(emoPieChart.value, isDark ? 'dark' : undefined);
          API.get('/emotion/statistics').then(function(d) {
            var dist = d && d.data ? d.data.emotion_distribution : {};
            var data = Object.entries(dist || {}).map(function(e) { return { name: e[0], value: e[1].count || e[1] }; });
            emoPieInst.setOption({
              tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
              series: [{
                type: 'pie', radius: ['45%', '75%'], roseType: 'area',
                itemStyle: { borderRadius: 6, borderColor: isDark ? '#1e293b' : '#fff', borderWidth: 3 },
                label: { fontSize: 11 },
                data: data.length ? data : [{ name: '暂无', value: 1 }],
                color: ['#6366f1', '#8b5cf6', '#f59e0b', '#ef4444', '#10b981', '#3b82f6', '#e67e22', '#f97316', '#94a3b8']
              }]
            });
          }).catch(function() {});
        }
        // Risk ring
        if (emoRiskChart.value) {
          if (emoRiskInst) emoRiskInst.dispose();
          emoRiskInst = echarts.init(emoRiskChart.value, isDark ? 'dark' : undefined);
          emoRiskInst.setOption({
            tooltip: { trigger: 'item' },
            series: [{
              type: 'pie', radius: ['55%', '80%'], itemStyle: { borderRadius: 6 },
              label: { formatter: '{b}\n{c}人', fontSize: 12 },
              data: [
                { name: '高风险', value: emoDashStats.highRisk, itemStyle: { color: '#ef4444' } },
                { name: '中风险', value: emoDashStats.mediumRisk, itemStyle: { color: '#f59e0b' } },
                { name: '低风险', value: Math.max(0, (emoDashStats.total || 0) - emoDashStats.highRisk - emoDashStats.mediumRisk), itemStyle: { color: '#10b981' } }
              ]
            }]
          });
        }
        // Trend
        if (emoTrendChart.value) {
          if (emoTrendInst) emoTrendInst.dispose();
          emoTrendInst = echarts.init(emoTrendChart.value, isDark ? 'dark' : undefined);
          API.get('/emotion/trends', { days: 7 }).then(function(d) {
            var data = d && d.data ? d.data : [];
            var labels = [], vals = [];
            if (Array.isArray(data)) {
              data.forEach(function(item) { labels.push(item.date || item.day || ''); vals.push(item.count || item.avg_intensity || 0); });
            }
            emoTrendInst.setOption({
              tooltip: { trigger: 'axis' },
              grid: { top: 10, right: 10, bottom: 20, left: 35 },
              xAxis: { type: 'category', data: labels.length ? labels : ['暂无数据'], axisLabel: { fontSize: 10 } },
              yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
              series: [{
                type: 'line', data: vals.length ? vals : [0], smooth: true,
                areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(99,102,241,0.35)' }, { offset: 1, color: 'rgba(99,102,241,0.02)' }] } },
                lineStyle: { color: '#6366f1', width: 2 }, itemStyle: { color: '#6366f1' }, symbol: 'circle', symbolSize: 6
              }]
            });
          }).catch(function() {});
        }
        // Heatmap
        if (emoHeatmapChart.value) {
          if (emoHeatInst) emoHeatInst.dispose();
          emoHeatInst = echarts.init(emoHeatmapChart.value, isDark ? 'dark' : undefined);
          API.get('/emotion/heatmap').then(function(d) {
            var data = d && d.data ? d.data : [];
            var hData = [];
            if (data.matrix && data.emotion_labels && data.intensity_labels) {
              for (var i = 0; i < data.matrix.length; i++)
                for (var j = 0; j < data.matrix[i].length; j++)
                  hData.push([j, i, data.matrix[i][j] || 0]);
              emoHeatInst.setOption({
                tooltip: { formatter: function(p) { return data.emotion_labels[p.value[1]] + ' ' + data.intensity_labels[p.value[0]] + ': ' + p.value[2] + '次'; } },
                grid: { top: 5, right: 10, bottom: 15, left: 70 },
                xAxis: { type: 'category', data: data.intensity_labels || [], axisLabel: { fontSize: 9 }, position: 'top' },
                yAxis: { type: 'category', data: data.emotion_labels || [], axisLabel: { fontSize: 10 } },
                visualMap: { min: 0, max: Math.max.apply(null, hData.map(function(h) { return h[2]; })) || 10, calculable: true, orient: 'vertical', right: 0, bottom: '15%', inRange: { color: ['#eef2ff', '#c7d2fe', '#818cf8', '#6366f1', '#4338ca'] }, textStyle: { fontSize: 9 } },
                series: [{ type: 'heatmap', data: hData, label: { show: true, fontSize: 9 }, emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.25)' } } }]
              });
            }
          }).catch(function() {});
        }
      }

      // ==================== 情绪网络图 ====================
      const networkGraph = ref(null);
      const networkFilter = ref(['high', 'medium', 'low']);
      const networkCanvas = ref(null);
      let networkGraphInst = null;
      let networkGraphCanvasEl = null;
      let networkPoll = null;

      function jumpToStudentChat(student) {
        if (!student || !student.db_id) return;
        var contact = { id: student.db_id, name: student.name, student_id: student.student_no };
        page.value = 'teacherChat';
        selectTeacherContact(contact);
        Toast.success('已跳转到 ' + student.name + ' 的对话');
      }

      function ensureNetworkGraph() {
        // 页面 v-if 销毁后重新进入时，canvas 是新元素，需重建实例
        if (networkCanvas.value && networkCanvas.value !== networkGraphCanvasEl) {
          if (networkGraphInst) { networkGraphInst.destroy(); networkGraphInst = null; }
          networkGraphCanvasEl = networkCanvas.value;
        }
        if (window.EmotionNetworkGraph && networkCanvas.value && !networkGraphInst) {
          networkGraphInst = window.EmotionNetworkGraph.create(networkCanvas.value, {
            dark: isDarkMode.value,
            onStudentClick: jumpToStudentChat
          });
        }
        if (networkGraphInst && networkGraph.value) {
          networkGraphInst.setData(networkGraph.value);
        }
        return networkGraphInst;
      }

      async function loadEmotionNetwork() {
        try {
          var d = await API.get('/network/emotion-graph');
          if (d && d.success && d.data) {
            networkGraph.value = d.data;
            await nextTick();
            var g = ensureNetworkGraph();
            if (g) g.setSeverityFilter(networkFilter.value.slice());
          }
        } catch (e) { /* silent */ }
      }

      function toggleNetworkFilter(level) {
        var i = networkFilter.value.indexOf(level);
        if (i >= 0) {
          if (networkFilter.value.length > 1) networkFilter.value.splice(i, 1);
        } else {
          networkFilter.value.push(level);
        }
        var g = ensureNetworkGraph();
        if (g) g.setSeverityFilter(networkFilter.value.slice());
      }

      // ==================== Socket.IO ====================
      let socket = null;
      let socketInitTimer = null;
      let dashInterval = null;
      function initSocket() {
        if (socket) return;
        if (typeof io === 'undefined') {
          if (!socketInitTimer) {
            socketInitTimer = setTimeout(function() {
              socketInitTimer = null;
              initSocket();
              if (currentUser.role === 'student') initStudentVideo();
              if (currentUser.role === 'counselor') initTeacherVideo();
            }, 150);
          }
          return;
        }
        socket = io({ transports: ['polling', 'websocket'], timeout: 5000, reconnectionAttempts: 3 });
        socket.on('connect', function() { /* connected */ });
        socket.on('connect_error', function() { /* silent retry */ });
        // 视频通话情绪总结落库后，实时刷新情绪网络图
        socket.on('emotion_graph_update', function(data) {
          loadEmotionNetwork();
        });
        socket.on('new_message', function(msg) {
          if (page.value === 'teacherChat' && teacherSelected.value) {
            teacherChatMsgs.value.push(msg);
            nextTick(function() { if (teacherMsgRef.value) teacherMsgRef.value.scrollTop = teacherMsgRef.value.scrollHeight; });
          }
          if (page.value === 'studentChat' && selectedContact.value) {
            chatMessages.value.push(msg);
            nextTick(function() { if (studentMsgRef.value) studentMsgRef.value.scrollTop = studentMsgRef.value.scrollHeight; });
          }
          loadUnreadCount(); loadMessageContacts();
        });
        if (currentUser.role === 'student') initStudentVideo();
        if (currentUser.role === 'counselor') initTeacherVideo();
      }

      // ==================== 师生通讯 ====================
      const messageContacts = ref([]);
      const teacherSelected = ref(null);
      const teacherChatMsgs = ref([]);
      const teacherNewMsg = ref('');
      const teacherUnreadCount = ref(0);
      const teacherMsgRef = ref(null);
      const studentSearchQuery = ref('');
      const studentSearchResults = ref([]);
      const selectedContact = ref(null);
      const chatMessages = ref([]);
      const newMessage = ref('');
      const studentUnreadCount = ref(0);
      const studentMsgRef = ref(null);
      const teacherShowEmoji = ref(false);
      const showEmoji = ref(false);
      const guidanceResult = ref(null);
      const guidanceLoading = ref(false);

      const searchStudentsHandler = Helpers.debounce(async function() {
        if (!studentSearchQuery.value.trim()) { studentSearchResults.value = []; return; }
        try {
          var d = await API.get('/student/list', { search: studentSearchQuery.value, per_page: 10 });
          studentSearchResults.value = d.data || [];
        } catch (e) { /* silent */ }
      }, 300);

      async function inviteStudent(s) {
        studentSearchQuery.value = ''; studentSearchResults.value = [];
        try { await API.post('/messages/send', { contact_id: s.id, content: '老师向您发起了对话' }); } catch (e) { /* silent */ }
        teacherSelected.value = { id: s.id, name: s.name, student_id: s.student_id };
        teacherChatMsgs.value = [{ id: Date.now(), content: '老师向您发起了对话', sender_type: 'counselor', created_at: new Date().toISOString() }];
        loadMessageContacts(); Toast.success('已发起对话');
      }

      async function selectTeacherContact(contact) {
        teacherSelected.value = contact; guidanceResult.value = null;
        try {
          var d = await API.get('/messages/' + contact.id);
          teacherChatMsgs.value = (d.data || []).reverse();
          await nextTick();
          if (teacherMsgRef.value) teacherMsgRef.value.scrollTop = teacherMsgRef.value.scrollHeight;
          loadMessageContacts();
        } catch (e) { /* silent */ }
      }

      async function sendTeacherMsg() {
        if (!teacherNewMsg.value.trim() || !teacherSelected.value) return;
        try {
          await API.post('/messages/send', { contact_id: teacherSelected.value.id, content: teacherNewMsg.value });
          var msg = teacherNewMsg.value;
          teacherNewMsg.value = '';
          teacherChatMsgs.value.push({ id: Date.now(), content: msg, sender_type: 'counselor', created_at: new Date().toISOString() });
          await nextTick();
          if (teacherMsgRef.value) teacherMsgRef.value.scrollTop = teacherMsgRef.value.scrollHeight;
          loadMessageContacts();
        } catch (e) { Toast.error('发送失败'); }
      }

      async function analyzeCounselorGuidance() {
        if (!teacherSelected.value || !teacherChatMsgs.value.length) return;
        guidanceLoading.value = true;
        try {
          var d = await API.post('/messages/counselor-guidance', {
            messages: teacherChatMsgs.value.slice(-10),
            student_name: teacherSelected.value.name
          });
          if (d.success && d.data) { guidanceResult.value = d.data; Toast.success('AI分析完成'); }
        } catch (e) { Toast.error('分析失败'); }
        guidanceLoading.value = false;
      }

      const guidanceRiskTagStyle = computed(function() {
        var r = guidanceResult.value && guidanceResult.value.risk_alert;
        if (r === '建议预警') return 'background:#fee2e2;color:#dc2626';
        if (r === '建议关注') return 'background:#fef3c7;color:#d97706';
        return 'background:#dcfce7;color:#16a34a';
      });

      function fillTeacherMsg(script) {
        teacherNewMsg.value = script;
        Toast.success('话术已填入输入框，可直接发送');
        nextTick(function() {
          var el = document.querySelector('.chat-compose-input');
          if (el) el.focus();
        });
      }

      const talkReport = ref(null);
      const talkReportLoading = ref(false);
      async function generateTalkReport() {
        if (!teacherSelected.value || !teacherChatMsgs.value.length) { Toast.error('请先选择学生并有对话内容'); return; }
        talkReportLoading.value = true;
        try {
          var d = await API.post('/conversation/generate-report', {
            student_id: teacherSelected.value.id,
            student_name: teacherSelected.value.name,
            messages: teacherChatMsgs.value.slice(-30),
            topic: '日常谈心'
          });
          if (d && d.success && d.data) {
            talkReport.value = d.data.report || null;
            Toast.success('谈心记录已生成并归档到学生档案');
          } else {
            Toast.error(d.message || '生成失败');
          }
        } catch (e) { Toast.error('生成失败'); }
        talkReportLoading.value = false;
      }

      async function loadMessageContacts() {
        try { var d = await API.get('/messages/contacts'); messageContacts.value = d.data || []; }
        catch (e) { /* silent */ }
      }

      async function selectContactHandler(contact) {
        if (selectedContact.value && socket) { socket.emit('leave', { room: 'chat_' + selectedContact.value.id }); }
        selectedContact.value = contact;
        if (socket) { socket.emit('join', { room: 'chat_' + contact.id }); }
        try {
          var d = await API.get('/messages/' + contact.id);
          chatMessages.value = (d.data || []).reverse();
          await nextTick();
          if (studentMsgRef.value) studentMsgRef.value.scrollTop = studentMsgRef.value.scrollHeight;
          loadMessageContacts();
        } catch (e) { /* silent */ }
      }

      async function sendStudentMsg() {
        if (!newMessage.value.trim() || !selectedContact.value) return;
        try {
          var d = await API.post('/messages/send', { contact_id: selectedContact.value.id, content: newMessage.value });
          if (socket && d.success) {
            socket.emit('send_message', {
              room: 'chat_' + selectedContact.value.id,
              message: { id: d.data ? d.data.id : null, content: newMessage.value, sender_type: 'student', created_at: new Date().toISOString() }
            });
          }
          newMessage.value = '';
          selectContactHandler(selectedContact.value);
        } catch (e) { Toast.error('发送失败'); }
      }

      async function loadUnreadCount() {
        try { var d = await API.get('/messages/unread'); var c = d.data ? d.data.unread_count : 0; studentUnreadCount.value = c; }
        catch (e) { /* silent */ }
      }

      function insertEmoji(e) { newMessage.value += e; showEmoji.value = false; }
      function insertTeacherEmoji(e) { teacherNewMsg.value += e; teacherShowEmoji.value = false; }

      // ==================== WebRTC 视频通话 ====================
      const localVideo = ref(null), remoteVideo = ref(null);
      const isInCall = ref(false), isVideoEnabled = ref(true), isAudioEnabled = ref(true);
      const incomingStudentCall = ref(null);
      const teacherLocalVideo = ref(null), teacherRemoteVideo = ref(null);
      const teacherInCall = ref(false), teacherVideoEnabled = ref(true), teacherAudioEnabled = ref(true);
      const incomingCall = ref(null);
      let localStream = null, peerConnection = null;
      let teacherLocalStream = null, teacherPeerConn = null;
      let pendingStudentCandidates = [], pendingTeacherCandidates = [];
      const callRoom = ref('');
      const videoRoom = ref('teacher_room');
      var studentVideoListenersSet = false, teacherVideoListenersSet = false;
      const visionDiag = reactive({
        modelReady: false,
        faceDetected: false,
        poseDetected: false,
        detectionSource: '--',
        status: 'idle',
        lastUpdate: '--',
        lastError: '',
        failCount: 0,
        noFaceCount: 0,
        frameCount: 0,
        changedAt: '--',
        rawMicro: { browFurrow: 0, gazeAversion: 0, headDown: 0, postureStiffness: 0, shoulderSlope: 0, forwardHead: 0, slouch: 0, scratchHead: 0, touchNose: 0, handNearFace: 0, gazeInstability: 0 },
        poseFrameCount: 0,
        poseNoLandmarkCount: 0,
        faceMeshFrameCount: 0,
        faceMeshDetected: false,
        faceMeshCropUsed: false,
        videoSize: '--',
        faceCropUsed: false
      });

      function updateVisionDiag(diag) {
        diag = diag || {};
        Object.keys(visionDiag).forEach(function(key) {
          if (Object.prototype.hasOwnProperty.call(diag, key)) visionDiag[key] = diag[key];
        });
      }

      const audioDiag = reactive({
        localMic: false,
        localEnabled: false,
        remoteAudio: false,
        remoteEnabled: false,
        remoteMuted: false,
        remoteReady: '--',
        remoteTrackCount: 0,
        volume: 0,
        pitch: 0,
        speaking: false,
        analyzer: false,
        contextState: '--',
        playBlocked: false,
        updatedAt: '--'
      });

      function audioTracks(stream) {
        return stream && stream.getAudioTracks ? stream.getAudioTracks() : [];
      }

      function refreshAudioDiag(kind, stream) {
        var tracks = audioTracks(stream);
        var first = tracks[0] || null;
        if (kind === 'local') {
          audioDiag.localMic = tracks.length > 0;
          audioDiag.localEnabled = !!(first && first.enabled && first.readyState === 'live');
        } else if (kind === 'remote') {
          audioDiag.remoteTrackCount = tracks.length;
          audioDiag.remoteAudio = tracks.length > 0;
          audioDiag.remoteEnabled = !!(first && first.enabled && first.readyState === 'live');
          audioDiag.remoteMuted = !!(first && first.muted);
          audioDiag.remoteReady = first ? first.readyState : '--';
          if (first && !first.__lingxinDiagBound) {
            first.__lingxinDiagBound = true;
            first.addEventListener('mute', function() { refreshAudioDiag('remote', stream); });
            first.addEventListener('unmute', function() { refreshAudioDiag('remote', stream); });
            first.addEventListener('ended', function() { refreshAudioDiag('remote', stream); });
          }
        }
        audioDiag.updatedAt = new Date().toTimeString().slice(0, 8);
      }

      function resetAudioDiag() {
        audioDiag.localMic = false;
        audioDiag.localEnabled = false;
        audioDiag.remoteAudio = false;
        audioDiag.remoteEnabled = false;
        audioDiag.remoteMuted = false;
        audioDiag.remoteReady = '--';
        audioDiag.remoteTrackCount = 0;
        audioDiag.volume = 0;
        audioDiag.pitch = 0;
        audioDiag.speaking = false;
        audioDiag.analyzer = false;
        audioDiag.contextState = '--';
        audioDiag.playBlocked = false;
        audioDiag.updatedAt = '--';
      }

      function attachRemoteStream(videoEl, stream) {
        if (!videoEl || !stream) return;
        videoEl.srcObject = stream;
        videoEl.autoplay = true;
        videoEl.playsInline = true;
        refreshAudioDiag('remote', stream);
        var playPromise = videoEl.play ? videoEl.play() : null;
        if (playPromise && playPromise.catch) {
          playPromise.then(function() { audioDiag.playBlocked = false; }).catch(function() {
            audioDiag.playBlocked = true;
          });
        }
      }


      // ===== 学生端 WebRTC =====
      function initStudentVideo() {
        if (!socket || studentVideoListenersSet) return; studentVideoListenersSet = true;
        socket.on('video_call_accepted', function(data) {
          if (data.caller !== 'student') return;
          callRoom.value = data.room;
          socket.emit('join', { room: data.room });
          createPeerConn(); createOffer();
        });
        socket.on('incoming_video_call', function(data) {
          if (data.caller !== 'teacher' || String(data.student_id || '') !== String(currentUser.student_id || '')) return;
          incomingStudentCall.value = data;
          Toast.info((data.teacher_name || '\u8001\u5e08') + ' \u9080\u8bf7\u4f60\u89c6\u9891\u901a\u8bdd');
        });
        socket.on('video_offer', function(data) {
          if (data.sender !== 'teacher') return;
          if (!peerConnection) createPeerConn();
          if (peerConnection.signalingState === 'stable') {
            peerConnection.setRemoteDescription(new RTCSessionDescription(data)).then(function() { flushStudentCandidates(); createAnswer(); }).catch(function(e) { console.log(e); });
          }
        });
        socket.on('video_answer', function(data) {
          if (data.sender !== 'teacher') return;
          if (peerConnection && peerConnection.signalingState === 'have-local-offer') {
            peerConnection.setRemoteDescription(new RTCSessionDescription(data)).then(function() { flushStudentCandidates(); }).catch(function(e) { console.log(e); });
          }
        });
        socket.on('video_ice_candidate', function(data) {
          if (data.sender !== 'teacher' || !data.candidate || !data.candidate.candidate) return;
          if (peerConnection && peerConnection.remoteDescription) peerConnection.addIceCandidate(new RTCIceCandidate(data.candidate)).catch(function(e) {});
          else pendingStudentCandidates.push(data.candidate);
        });
        socket.on('video_call_ended', function(data) { if (!data || data.sender !== 'student') endVideoCall(true); });
      }

      function flushStudentCandidates() {
        if (!peerConnection || !peerConnection.remoteDescription) return;
        pendingStudentCandidates.splice(0).forEach(function(c) {
          peerConnection.addIceCandidate(new RTCIceCandidate(c)).catch(function(e) {});
        });
      }

      function createPeerConn() {
        if (peerConnection) { peerConnection.close(); peerConnection = null; }
        peerConnection = new RTCPeerConnection({ iceServers: [
          { urls: 'stun:stun.l.google.com:19302' },
          { urls: 'stun:stun1.l.google.com:19302' },
          { urls: 'stun:stun2.l.google.com:19302' }
        ], iceCandidatePoolSize: 2 });
        if (localStream) localStream.getTracks().forEach(function(t) { peerConnection.addTrack(t, localStream); });
        peerConnection.onicecandidate = function(e) {
          if (e.candidate && e.candidate.candidate) socket.emit('video_ice_candidate', { candidate: e.candidate, room: callRoom.value, sender: 'student' });
        };
        peerConnection.ontrack = function(e) {
          if (remoteVideo.value && e.streams[0]) {
            attachRemoteStream(remoteVideo.value, e.streams[0]);
          }
        };
      }

      async function createOffer() {
        if (!peerConnection || peerConnection.signalingState !== 'stable') return;
        var offer = await peerConnection.createOffer();
        await peerConnection.setLocalDescription(offer);
        socket.emit('video_offer', { type: offer.type, sdp: offer.sdp, room: callRoom.value, sender: 'student' });
      }

      async function createAnswer() {
        if (!peerConnection || peerConnection.signalingState !== 'have-remote-offer') return;
        var answer = await peerConnection.createAnswer();
        await peerConnection.setLocalDescription(answer);
        socket.emit('video_answer', { type: answer.type, sdp: answer.sdp, room: callRoom.value, sender: 'student' });
      }

      function getMediaUnsupportedMessage() {
        if (!window.isSecureContext) {
          return '当前访问地址不是安全环境，浏览器会禁用摄像头/麦克风。请用 http://localhost:5000、http://127.0.0.1:5000 或 HTTPS 打开平台，不要用局域网 IP 的 http 地址。';
        }
        return '当前浏览器不支持摄像头/麦克风，请使用最新版 Chrome 或 Edge。';
      }

      function isMediaSupported() {
        return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
      }

      async function startVideoCall(options) {
        options = options || {};
        if (!isMediaSupported()) {
          Toast.error(getMediaUnsupportedMessage()); return false;
        }
        try {
          var perms = await navigator.permissions.query({ name: 'camera' }).catch(function() { return null; });
          if (perms && perms.state === 'denied') { Toast.error('\u6444\u50cf\u5934\u6743\u9650\u5df2\u88ab\u62d2\u7edd\uff0c\u8bf7\u5728\u6d4f\u89c8\u5668\u8bbe\u7f6e\u4e2d\u5141\u8bb8'); return false; }
          localStream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 720 }, height: { ideal: 960 }, facingMode: 'user' }, audio: true });
          refreshAudioDiag('local', localStream);
          isInCall.value = true; isVideoEnabled.value = true; isAudioEnabled.value = true;
          await nextTick();
          if (localVideo.value) localVideo.value.srcObject = localStream;
          if (!socket) { Toast.error('\u8fde\u63a5\u672a\u5c31\u7eea\uff0c\u8bf7\u5237\u65b0\u9875\u9762'); endVideoCall(true); return false; }
          initStudentVideo();
          callRoom.value = options.reuseRoom || ('video_' + Date.now());
          socket.emit('join', { room: callRoom.value });
          if (!options.skipRequest) socket.emit('video_call_request', { caller: 'student', student_id: currentUser.student_id, student_name: currentUser.name, room: callRoom.value });
          return true;
        } catch (err) {
          if (err.name === 'NotAllowedError') Toast.error('\u6444\u50cf\u5934\u6216\u9ea6\u514b\u98ce\u6743\u9650\u88ab\u62d2\u7edd');
          else if (err.name === 'NotFoundError') Toast.error('\u672a\u68c0\u6d4b\u5230\u6444\u50cf\u5934\u6216\u9ea6\u514b\u98ce\u8bbe\u5907');
          else Toast.error('\u65e0\u6cd5\u8bbf\u95ee\u6444\u50cf\u5934\uff1a' + err.message);
          return false;
        }
      }

      function endVideoCall(silent) {
        stopAllRealtime();
        if (localStream) { localStream.getTracks().forEach(function(t) { t.stop(); }); localStream = null; }
        if (peerConnection) { peerConnection.close(); peerConnection = null; }
        pendingStudentCandidates = [];
        if (localVideo.value) localVideo.value.srcObject = null;
        if (remoteVideo.value) remoteVideo.value.srcObject = null;
        resetAudioDiag();
        isInCall.value = false;
        if (!silent && socket) socket.emit('video_call_end', { room: callRoom.value, sender: 'student' });
      }

      function toggleVideo() {
        if (localStream) { var t = localStream.getVideoTracks()[0]; if (t) { t.enabled = !t.enabled; isVideoEnabled.value = t.enabled; } }
      }
      function toggleAudio() {
        if (localStream) { var t = localStream.getAudioTracks()[0]; if (t) { t.enabled = !t.enabled; isAudioEnabled.value = t.enabled; refreshAudioDiag('local', localStream); } }
      }

      async function ensureStudentCallContact(callData) {
        page.value = 'studentChat';
        if (!messageContacts.value.length) await loadMessageContacts();
        var contactId = callData && callData.counselor_id ? Number(callData.counselor_id) : null;
        var match = messageContacts.value.find(function(c) { return contactId ? Number(c.id) === contactId : (callData && c.name === callData.teacher_name); });
        if (!match && callData && callData.teacher_name) { match = { id: contactId || (selectedContact.value && selectedContact.value.id), name: callData.teacher_name.replace(/老师$/, ''), role: 'counselor' }; }
        if (match && match.id) await selectContactHandler(match);
        await nextTick();
      }

      async function ensureTeacherCallContact(callData) {
        page.value = 'teacherChat';
        if (!messageContacts.value.length) await loadMessageContacts();
        var sid = callData && callData.student_id ? String(callData.student_id) : '';
        var match = messageContacts.value.find(function(c) { return sid && String(c.student_id || '') === sid; });
        if (!match && callData) { match = { id: callData.student_db_id || null, name: callData.student_name, student_id: callData.student_id, role: 'student' }; }
        if (match && match.id) await selectTeacherContact(match);
        await nextTick();
      }

      async function acceptStudentCall() {
        if (!incomingStudentCall.value) return;
        await ensureStudentCallContact(incomingStudentCall.value);
        callRoom.value = incomingStudentCall.value.room || ('video_' + Date.now());
        var started = await startVideoCall({ reuseRoom: callRoom.value, skipRequest: true });
        if (!started) return;
        socket.emit('join', { room: callRoom.value });
        socket.emit('video_call_accept', { room: callRoom.value, caller: 'teacher' });
        incomingStudentCall.value = null;
      }
      function rejectStudentCall() { incomingStudentCall.value = null; Toast.info('\u5df2\u62d2\u7edd'); }

      // ===== 教师端 WebRTC =====
      function initTeacherVideo() {
        if (!socket || teacherVideoListenersSet) return; teacherVideoListenersSet = true;
        socket.on('incoming_video_call', function(data) {
          if (data.caller !== 'student') return;
          incomingCall.value = data;
          Toast.info('\u6536\u5230 ' + data.student_name + ' \u7684\u89c6\u9891\u547c\u53eb');
        });
        socket.on('video_call_accepted', function(data) {
          if (data.caller !== 'teacher') return;
          videoRoom.value = data.room;
          socket.emit('join', { room: videoRoom.value });
          createTeacherPeerConn(); createTeacherOffer();
        });
        socket.on('video_offer', function(data) {
          if (data.sender !== 'student') return;
          if (!teacherPeerConn) createTeacherPeerConn();
          if (teacherPeerConn.signalingState === 'stable') {
            teacherPeerConn.setRemoteDescription(new RTCSessionDescription(data)).then(function() { flushTeacherCandidates(); createTeacherAnswer(); }).catch(function(e) { console.log(e); });
          }
        });
        socket.on('video_answer', function(data) {
          if (data.sender !== 'student') return;
          if (teacherPeerConn && teacherPeerConn.signalingState === 'have-local-offer') {
            teacherPeerConn.setRemoteDescription(new RTCSessionDescription(data)).then(function() { flushTeacherCandidates(); }).catch(function(e) { console.log(e); });
          }
        });
        socket.on('video_ice_candidate', function(data) {
          if (data.sender !== 'student' || !data.candidate || !data.candidate.candidate) return;
          if (teacherPeerConn && teacherPeerConn.remoteDescription) teacherPeerConn.addIceCandidate(new RTCIceCandidate(data.candidate)).catch(function(e) {});
          else pendingTeacherCandidates.push(data.candidate);
        });
        socket.on('video_call_ended', function(data) { if (!data || data.sender !== 'teacher') endTeacherVideo(true); });
      }

      function flushTeacherCandidates() {
        if (!teacherPeerConn || !teacherPeerConn.remoteDescription) return;
        pendingTeacherCandidates.splice(0).forEach(function(c) {
          teacherPeerConn.addIceCandidate(new RTCIceCandidate(c)).catch(function(e) {});
        });
      }

      async function startTeacherVideo(options) {
        options = options || {};
        if (!isMediaSupported()) {
          Toast.error(getMediaUnsupportedMessage()); return false;
        }
        try {
          teacherLocalStream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }, audio: true });
          refreshAudioDiag('local', teacherLocalStream);
          teacherInCall.value = true; teacherVideoEnabled.value = true; teacherAudioEnabled.value = true;
          videoRoom.value = options.reuseRoom || ('video_' + Date.now());
          await nextTick();
          if (teacherLocalVideo.value) teacherLocalVideo.value.srcObject = teacherLocalStream;
          if (socket) { socket.emit('join', { room: videoRoom.value }); }
          return true;
        } catch (err) {
          if (err.name === 'NotAllowedError') Toast.error('\u6444\u50cf\u5934\u6216\u9ea6\u514b\u98ce\u6743\u9650\u88ab\u62d2\u7edd');
          else if (err.name === 'NotFoundError') Toast.error('\u672a\u68c0\u6d4b\u5230\u6444\u50cf\u5934\u6216\u9ea6\u514b\u98ce\u8bbe\u5907');
          else Toast.error('\u65e0\u6cd5\u8bbf\u95ee\u6444\u50cf\u5934\uff1a' + err.message);
          return false;
        }
      }

      function createTeacherPeerConn() {
        if (teacherPeerConn) { teacherPeerConn.close(); teacherPeerConn = null; }
        teacherPeerConn = new RTCPeerConnection({ iceServers: [
          { urls: 'stun:stun.l.google.com:19302' },
          { urls: 'stun:stun1.l.google.com:19302' },
          { urls: 'stun:stun2.l.google.com:19302' }
        ], iceCandidatePoolSize: 2 });
        if (teacherLocalStream) teacherLocalStream.getTracks().forEach(function(t) { teacherPeerConn.addTrack(t, teacherLocalStream); });
        teacherPeerConn.onicecandidate = function(e) {
          if (e.candidate && e.candidate.candidate) socket.emit('video_ice_candidate', { candidate: e.candidate, room: videoRoom.value, sender: 'teacher' });
        };
        teacherPeerConn.ontrack = function(e) {
          if (teacherRemoteVideo.value && e.streams[0]) {
            attachRemoteStream(teacherRemoteVideo.value, e.streams[0]);
            autoStartRealtimeEmotion(e.streams[0], teacherRemoteVideo.value);
          }
        };
      }

      async function createTeacherOffer() {
        if (!teacherPeerConn || teacherPeerConn.signalingState !== 'stable') return;
        var offer = await teacherPeerConn.createOffer();
        await teacherPeerConn.setLocalDescription(offer);
        socket.emit('video_offer', { type: offer.type, sdp: offer.sdp, room: videoRoom.value, sender: 'teacher' });
      }

      async function createTeacherAnswer() {
        if (!teacherPeerConn || teacherPeerConn.signalingState !== 'have-remote-offer') return;
        var answer = await teacherPeerConn.createAnswer();
        await teacherPeerConn.setLocalDescription(answer);
        socket.emit('video_answer', { type: answer.type, sdp: answer.sdp, room: videoRoom.value, sender: 'teacher' });
      }

      async function acceptVideoCall() {
        if (incomingCall.value) await ensureTeacherCallContact(incomingCall.value);
        if (incomingCall.value) videoRoom.value = incomingCall.value.room || ('video_' + Date.now());
        if (!teacherInCall.value) {
          var started = await startTeacherVideo({ reuseRoom: videoRoom.value });
          if (!started) return;
        }
        if (incomingCall.value) {
          socket.emit('join', { room: videoRoom.value });
          socket.emit('video_call_accept', { room: videoRoom.value, caller: 'student' });
          incomingCall.value = null;
        }
      }

      function rejectVideoCall() { incomingCall.value = null; Toast.info('\u5df2\u62d2\u7edd'); }

      async function endTeacherVideo(silent) {
        await submitRealtimeCallSummary();
        stopAllRealtime();
        if (teacherLocalStream) { teacherLocalStream.getTracks().forEach(function(t) { t.stop(); }); teacherLocalStream = null; }
        if (teacherPeerConn) { teacherPeerConn.close(); teacherPeerConn = null; }
        pendingTeacherCandidates = [];
        if (teacherLocalVideo.value) teacherLocalVideo.value.srcObject = null;
        if (teacherRemoteVideo.value) teacherRemoteVideo.value.srcObject = null;
        resetAudioDiag();
        teacherInCall.value = false;
        if (!silent && socket) socket.emit('video_call_end', { room: videoRoom.value, sender: 'teacher' });
      }

      function toggleTeacherVideo() {
        if (teacherLocalStream) { var t = teacherLocalStream.getVideoTracks()[0]; if (t) { t.enabled = !t.enabled; teacherVideoEnabled.value = t.enabled; } }
      }
      function toggleTeacherAudio() {
        if (teacherLocalStream) { var t = teacherLocalStream.getAudioTracks()[0]; if (t) { t.enabled = !t.enabled; teacherAudioEnabled.value = t.enabled; refreshAudioDiag('local', teacherLocalStream); } }
      }

      async function openTeacherVideo() {
        if (!teacherSelected.value) return;
        initTeacherVideo();
        var started = await startTeacherVideo();
        if (!started) return;
        if (socket) {
          socket.emit('video_call_request', {
            caller: 'teacher',
            student_id: teacherSelected.value.student_id,
            student_name: teacherSelected.value.name,
            teacher_name: currentUser.display_name || currentUser.username || '\u8001\u5e08',
            counselor_id: currentUser.user_id || currentUser.id,
            room: videoRoom.value
          });
        }
      }

      const yoloActive = ref(false);
      const currentYoloEmotion = ref(null);
      const yoloAlerts = ref([]);
      const yoloCanvas = ref(null);
      let faceTimer = null, voiceTimer = null;
      let realtimeVideoEl = null;
      let realtimeAudioStream = null;
      let voiceAnalyzer = null;
      let lastRealtimeLogAt = 0;
      let lastRealtimeLogKey = '';
      let realtimeCallStartedAt = null;
      let realtimeSummarySubmitting = false;
      const realtimeEmotionSamples = [];
      const fusionHistory = [];
      const realtimeCallSummary = ref(null);
      // 后端真模型结果（准确情绪），由实时上传回填
      const realtimeVoiceModelEmotion = ref(null);  // emotion2vec 语音情绪
      const realtimeFaceModelEmotion = ref(null);   // FER 人脸情绪
      let lastVoiceUploadAt = 0;
      let lastFaceUploadAt = 0;

      const yoloEmotionShow = computed(function() { return yoloActive.value; });
      const yoloEmotionDisplay = computed(function() {
        if (!yoloActive.value || !currentYoloEmotion.value) {
          return {
            icon: '🤔', text: '等待检测', confidence: '--', intensity: 0, color: '#94a3b8',
            faceTension: '#10b981', faceLabel: '正常', gazeAvert: '#10b981', gazeLabel: '正常',
            posture: '#10b981', postureLabel: '正常', browFurrow: 0, gazeAversion: 0, headDownPercent: 0,
            postureStiffness: 0, postureStiffnessLabel: '\u6b63\u5e38', postureStiffnessColor: '#10b981',
            poseDetected: false, detectionSource: '--', shoulderSlope: 0, forwardHead: 0, slouch: 0, scratchHead: 0, touchNose: 0, handNearFace: 0, gazeInstability: 0,
            speechRate: 0, speechRateLabel: '--', pauseRatio: 0, isSpeaking: false,
            audioVolume: 0, pitch: 0
          };
        }
        return currentYoloEmotion.value;
      });

      function buildRealtimeEmotion(faceResult, voiceState) {
        faceResult = faceResult || { emotion: '\u6b63\u5e38', confidence: 45, expressions: { neutral: 1 }, micro: {}, facesDetected: 0 };
        voiceState = voiceState || { speechRate: 0, pauseRatio: 0, isSpeaking: false, emotionHint: '\u6b63\u5e38', volume: 0, pitch: 0 };
        if (window.EmotionFusionEngine) {
          return _applyModelEmotions(EmotionFusionEngine.fuse(faceResult, voiceState, fusionHistory), voiceState);
        }
        var micro = faceResult.micro || {};
        var text = faceResult.emotion || voiceState.emotionHint || '\u6b63\u5e38';
        var confidence = faceResult.confidence || (voiceState.isSpeaking ? 60 : 45);
        var weightedActionSignal = Math.max(
          (micro.browFurrow || 0) * 1.35,
          (micro.gazeInstability || 0) * 1.10,
          (micro.gazeAversion || 0) * 1.05,
          (micro.headDown || 0) * 0.95,
          (micro.slouch || 0) * 0.95,
          (micro.postureStiffness || 0) * 0.90,
          (micro.touchNose || 0) * 0.72,
          (micro.scratchHead || 0) * 0.72,
          (micro.handNearFace || 0) * 0.60
        );
        var actionConfidence = Math.round(Math.max(0, Math.min(1, weightedActionSignal)) * 100);
        return {
          icon: '\ud83d\ude10', text: text, confidence: confidence,
          intensity: Math.min(10, Math.max(1, Math.round(confidence / 10) + (weightedActionSignal > 0.28 ? 1 : 0) + (weightedActionSignal > 0.55 ? 1 : 0) + ((micro.browFurrow || 0) > 0.50 && (micro.gazeInstability || 0) > 0.25 ? 1 : 0))), color: '#6366f1',
          actionConfidence: actionConfidence,
          faceTension: micro.browFurrow > 0.22 ? '#ef4444' : '#10b981',
          faceLabel: micro.browFurrow > 0.22 ? '\u504f\u9ad8' : '\u6b63\u5e38',
          gazeAvert: Math.max(micro.gazeAversion || 0, micro.gazeInstability || 0) > 0.22 ? '#f59e0b' : '#10b981',
          gazeLabel: Math.max(micro.gazeAversion || 0, micro.gazeInstability || 0) > 0.22 ? '\u6ce8\u610f' : '\u6b63\u5e38',
          posture: (micro.headDown > 0.32 || micro.postureStiffness > 0.35 || micro.slouch > 0.35) ? '#ef4444' : '#10b981',
          postureLabel: (micro.headDown > 0.32 || micro.postureStiffness > 0.35 || micro.slouch > 0.35) ? '\u504f\u9ad8' : '\u6b63\u5e38',
          browFurrow: Math.round((micro.browFurrow || 0) * 100),
          gazeAversion: Math.round((micro.gazeAversion || 0) * 100),
          headDownPercent: Math.round((micro.headDown || 0) * 100),
          postureStiffness: Math.round((micro.postureStiffness || 0) * 100),
          postureStiffnessLabel: micro.postureStiffness > 0.35 ? '\u7591\u4f3c\u9a7c\u80cc/\u50f5\u786c' : '\u6b63\u5e38',
          postureStiffnessColor: micro.postureStiffness > 0.35 ? '#f59e0b' : '#10b981',
          poseDetected: !!micro.poseDetected,
          detectionSource: micro.detectionSource || 'face-keypoints',
          shoulderSlope: Math.round((micro.shoulderSlope || 0) * 100),
          forwardHead: Math.round((micro.forwardHead || 0) * 100),
          slouch: Math.round((micro.slouch || 0) * 100),
          scratchHead: Math.round((micro.scratchHead || 0) * 100),
          touchNose: Math.round((micro.touchNose || 0) * 100),
          handNearFace: Math.round((micro.handNearFace || 0) * 100),
          gazeInstability: Math.round((micro.gazeInstability || 0) * 100),
          speechRate: Math.round((voiceState.speechRate || 0) * 100),
          speechRateLabel: voiceState.speechRate > 0.45 ? '\u504f\u5feb' : '\u6b63\u5e38',
          pauseRatio: Math.round((voiceState.pauseRatio || 0) * 100),
          isSpeaking: !!voiceState.isSpeaking,
          audioVolume: Math.round((voiceState.volume || 0) * 100),
          pitch: Math.round(voiceState.pitch || 0)
        };
      }

      // 多信号加权投票融合：语音真模型(emotion2vec) + 人脸真模型(FER) + 本地微表情/韵律
      function _applyModelEmotions(fused, voiceState) {
        var voiceModel = realtimeVoiceModelEmotion.value;
        var faceModel = realtimeFaceModelEmotion.value;
        var isSpeaking = voiceState && voiceState.isSpeaking;

        var votes = {};      // {情绪: 加权得分}
        var totalWeight = 0; // 总权重

        function vote(emotion, confidence, weight) {
          if (!emotion || emotion === '未知' || emotion === '--') return;
          var conf = Number(confidence) || 0;
          if (conf > 1) conf = conf / 100; // 归一化到 0~1
          votes[emotion] = (votes[emotion] || 0) + conf * weight;
          totalWeight += weight;
        }

        // 语音真模型：说话时权重高（3），未说话权重低（1）
        if (voiceModel && voiceModel.emotion && voiceModel._source === 'emotion2vec') {
          vote(voiceModel.emotion, voiceModel.confidence, isSpeaking ? 3 : 1);
        }
        // 人脸真模型：权重 2
        if (faceModel && faceModel.primary_emotion && faceModel.primary_emotion !== '未知') {
          vote(faceModel.primary_emotion, faceModel.confidence, 2);
        }
        // 本地融合（face-api 表情 + 韵律 + 微表情：皱眉→焦虑、嘴角向下→悲伤）：权重 1
        vote(fused.text, fused.confidence, 1);

        if (totalWeight > 0) {
          var best = null, bestScore = -1;
          Object.keys(votes).forEach(function(k) {
            if (votes[k] > bestScore) { best = k; bestScore = votes[k]; }
          });
          if (best) {
            fused.text = best;
            fused.icon = window.EmotionFusionEngine ? EmotionFusionEngine.emotionIcon(best) : fused.icon;
            fused.color = window.EmotionFusionEngine ? EmotionFusionEngine.emotionColor(best) : fused.color;
            fused.confidence = Math.round((bestScore / totalWeight) * 100);
            fused.modelSource = '多模型投票';
          }
        }

        // 保留人脸模型的原始结果供面板显示
        if (faceModel && faceModel.primary_emotion) {
          fused.faceModelEmotion = faceModel.primary_emotion;
          fused.faceModelConfidence = Math.round((faceModel.confidence || 0) * 100);
        }

        fused.riskLevel = normalizeRealtimeRisk(fused);
        return fused;
      }

      function normalizeRealtimeRisk(emotion) {
        if (!emotion) return 'low';
        if (emotion.riskLevel && emotion.riskLevel !== 'none') return emotion.riskLevel;
        var intensity = Number(emotion.intensity || 0);
        return intensity >= 7 ? 'high' : intensity >= 5 ? 'medium' : 'low';
      }

      function captureRealtimeSample(emotion) {
        if (currentUser.role !== 'counselor' || !teacherInCall.value || !teacherSelected.value || !emotion) return;
        var now = Date.now();
        var last = realtimeEmotionSamples.length ? realtimeEmotionSamples[realtimeEmotionSamples.length - 1] : null;
        var riskLevel = normalizeRealtimeRisk(emotion);
        if (last && now - last.ts < 1200 && last.emotion === emotion.text && last.intensity === emotion.intensity && last.risk_level === riskLevel) return;
        realtimeEmotionSamples.push({
          ts: now,
          time: new Date(now).toISOString(),
          emotion: emotion.text || '\u6b63\u5e38',
          confidence: emotion.confidence === '--' ? null : emotion.confidence,
          intensity: emotion.intensity || 1,
          risk_level: riskLevel,
          speechRate: emotion.speechRate || 0,
          pauseRatio: emotion.pauseRatio || 0,
          audioVolume: emotion.audioVolume || 0,
          pitch: emotion.pitch || 0,
          actionConfidence: emotion.actionConfidence || 0,
          browFurrow: emotion.browFurrow || 0,
          gazeAversion: emotion.gazeAversion || 0,
          headDownPercent: emotion.headDownPercent || 0,
          postureStiffness: emotion.postureStiffness || 0,
          forwardHead: emotion.forwardHead || 0,
          shoulderSlope: emotion.shoulderSlope || 0,
          slouch: emotion.slouch || 0,
          scratchHead: emotion.scratchHead || 0,
          touchNose: emotion.touchNose || 0,
          handNearFace: emotion.handNearFace || 0,
          gazeInstability: emotion.gazeInstability || 0
        });
        if (realtimeEmotionSamples.length > 240) realtimeEmotionSamples.shift();
      }

      function queueRealtimeLog() {
        if (currentUser.role !== 'counselor' || !teacherInCall.value || !teacherSelected.value || !currentYoloEmotion.value) return;
        var emotion = currentYoloEmotion.value;
        captureRealtimeSample(emotion);
        var riskLevel = normalizeRealtimeRisk(emotion);
        var key = [teacherSelected.value.id || teacherSelected.value.student_id || '', emotion.text, riskLevel].join('|');
        var now = Date.now();
        if (now - lastRealtimeLogAt < 9000 && key === lastRealtimeLogKey) return;
        lastRealtimeLogAt = now;
        lastRealtimeLogKey = key;
        API.post('/emotion/realtime-log', {
          student_name: teacherSelected.value.name || '\u672a\u77e5\u5b66\u751f',
          student_class: teacherSelected.value.class_name || teacherSelected.value.student_class || teacherSelected.value.college || '\u89c6\u9891\u901a\u8bdd',
          emotion: emotion.text || '\u6b63\u5e38',
          confidence: emotion.confidence === '--' ? null : emotion.confidence,
          intensity: emotion.intensity || 1,
          risk_level: riskLevel
        }).catch(function() {});
      }

      function refreshRealtimeEmotion(faceResult) {
        var voiceState = voiceAnalyzer ? voiceAnalyzer.getState() : null;
        currentYoloEmotion.value = buildRealtimeEmotion(faceResult, voiceState);
        queueRealtimeLog();
      }

      // Float32Array → base64（小端序，供后端 np.frombuffer 解析）
      function _float32ToBase64(f32) {
        var buf = new ArrayBuffer(f32.length * 4);
        var view = new DataView(buf);
        for (var i = 0; i < f32.length; i++) view.setFloat32(i * 4, f32[i], true);
        var bytes = new Uint8Array(buf);
        var bin = '';
        var step = 0x8000;
        for (var j = 0; j < bytes.length; j += step) {
          bin += String.fromCharCode.apply(null, bytes.subarray(j, j + step));
        }
        return btoa(bin);
      }

      // 上传音频分片到后端 emotion2vec，回填准确语音情绪
      async function uploadVoiceChunk() {
        if (!voiceAnalyzer || !voiceAnalyzer.getAudioChunk) return;
        var chunk = voiceAnalyzer.getAudioChunk();
        if (!chunk || !chunk.pcm || chunk.pcm.length < (chunk.sampleRate || 44100) * 1.5) return;
        try {
          var b64 = _float32ToBase64(chunk.pcm);
          var d = await API.postSilent('/emotion/audio-chunk', {
            audio: b64,
            session_id: 'video_' + (teacherSelected.value ? (teacherSelected.value.id || teacherSelected.value.student_id || '') : ''),
            sample_rate: chunk.sampleRate
          });
          if (d && d.success && d.data && d.data.emotion) {
            realtimeVoiceModelEmotion.value = d.data;
            if (voiceAnalyzer.getState) voiceAnalyzer.getState().modelEmotion = d.data;
          }
        } catch (e) { /* 静默，网络异常不打断检测循环 */ }
      }

      // 上传视频帧到后端 FER，回填准确人脸情绪
      async function uploadFaceFrame(videoEl) {
        if (!videoEl || !videoEl.videoWidth) return;
        try {
          var canvas = document.createElement('canvas');
          canvas.width = videoEl.videoWidth; canvas.height = videoEl.videoHeight;
          var ctx = canvas.getContext('2d');
          ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
          var b64 = canvas.toDataURL('image/jpeg', 0.7);
          var d = await API.postSilent('/emotion/yolo-detect', { image: b64 });
          if (d && d.success && d.emotions && d.emotions.length > 0) {
            realtimeFaceModelEmotion.value = d.emotions[0];
          }
        } catch (e) { /* 静默 */ }
      }

      async function submitRealtimeCallSummary() {
        if (currentUser.role !== 'counselor' || realtimeSummarySubmitting || !teacherSelected.value) return null;
        // 确保至少有一个样本：即使检测未产生样本，也用当前/默认情绪生成一个，保证总结可靠弹出
        if (!realtimeEmotionSamples.length) {
          captureRealtimeSample(currentYoloEmotion.value || {
            text: '正常', confidence: 0, intensity: 1, riskLevel: 'low',
            speechRate: 0, pauseRatio: 0, audioVolume: 0, pitch: 0,
            browFurrow: 0, gazeAversion: 0, headDownPercent: 0, postureStiffness: 0,
            forwardHead: 0, shoulderSlope: 0, slouch: 0, scratchHead: 0,
            touchNose: 0, handNearFace: 0, gazeInstability: 0, actionConfidence: 0
          });
        }
        if (!realtimeEmotionSamples.length) return null;
        realtimeSummarySubmitting = true;
        try {
          var endedAt = new Date();
          var startedAt = realtimeCallStartedAt || endedAt;
          var d = await API.post('/emotion/realtime-call-summary', {
            student_pk: teacherSelected.value.id || null,
            student_id_str: teacherSelected.value.student_id || '',
            student_name: teacherSelected.value.name || '\u672a\u77e5\u5b66\u751f',
            student_class: teacherSelected.value.class_name || teacherSelected.value.student_class || teacherSelected.value.college || '\u89c6\u9891\u901a\u8bdd',
            call_started_at: startedAt.toISOString ? startedAt.toISOString() : startedAt,
            call_ended_at: endedAt.toISOString(),
            duration_seconds: Math.max(0, Math.round((endedAt.getTime() - new Date(startedAt).getTime()) / 1000)),
            samples: realtimeEmotionSamples.slice()
          });
          realtimeCallSummary.value = d && d.data ? d.data : null;
          if (realtimeCallSummary.value) {
            Toast.success('\u901a\u8bdd\u60c5\u7eea\u603b\u7ed3\u5df2\u751f\u6210\uff0c\u5efa\u8bae' + realtimeCallSummary.value.follow_up_days + '\u65e5\u540e\u590d\u67e5');
            loadYoloLogs();
            loadWorkplan();
            loadEmotionNetwork(); // \u901a\u8bdd\u7ed3\u675f\u540e\u5b9e\u65f6\u66f4\u65b0\u60c5\u7eea\u7f51\u7edc\u56fe
          }
          return realtimeCallSummary.value;
        } catch (e) {
          Toast.error('\u901a\u8bdd\u60c5\u7eea\u603b\u7ed3\u751f\u6210\u5931\u8d25');
          return null;
        } finally {
          realtimeSummarySubmitting = false;
        }
      }

      function queueFaceApiLoad() {
        if (window._loadFaceAPI) {
          window._loadFaceAPI(function() {
            if (window.FaceEmotionDetector) FaceEmotionDetector.loadModels().catch(function() {});
          });
        } else if (window.FaceEmotionDetector) {
          FaceEmotionDetector.loadModels().catch(function() {});
        }
      }

      function autoStartRealtimeEmotion(stream, videoEl) {
        yoloActive.value = true;
        if (!realtimeCallStartedAt) realtimeCallStartedAt = new Date();
        realtimeVideoEl = videoEl || null;
        refreshRealtimeEmotion(null);
        queueFaceApiLoad();
        startRealtimeEmotion(stream);
      }

      async function startRealtimeEmotion(remoteStream) {
        if (!yoloActive.value) return;
        if (faceTimer) clearTimeout(faceTimer);
        if (voiceTimer) clearTimeout(voiceTimer);
        if (voiceAnalyzer) { voiceAnalyzer.stop(); voiceAnalyzer = null; }
        realtimeAudioStream = remoteStream || null;
        refreshAudioDiag('remote', remoteStream);
        audioDiag.analyzer = false;
        audioDiag.contextState = '--';

        if (remoteStream && remoteStream.getAudioTracks && remoteStream.getAudioTracks().length > 0 && window.VoiceProsodyAnalyzer) {
          try {
            voiceAnalyzer = VoiceProsodyAnalyzer.create(remoteStream);
            voiceAnalyzer.start();
            audioDiag.analyzer = true;
          } catch (e) { console.warn('voice analyzer start failed:', e); audioDiag.analyzer = false; }
        }

        refreshRealtimeEmotion(null);
        runFaceDetectionLoop();
        runVoiceAnalysisLoop();
      }

      async function runFaceDetectionLoop() {
        if (!yoloActive.value) return;
        var videoEl = realtimeVideoEl || teacherRemoteVideo.value || remoteVideo.value;
        if (!videoEl || !videoEl.srcObject || videoEl.readyState < 2) {
          refreshRealtimeEmotion(null);
          faceTimer = setTimeout(runFaceDetectionLoop, 600);
          return;
        }

        // 每 ~1s 上传一帧到后端 FER（真模型人脸情绪）
        var _fnow = Date.now();
        if (_fnow - lastFaceUploadAt >= 1000) {
          lastFaceUploadAt = _fnow;
          uploadFaceFrame(videoEl);
        }

        if (window.FaceEmotionDetector) {
          try {
            var faceResult = await FaceEmotionDetector.detect(videoEl);
            if (faceResult && yoloCanvas.value) {
              try { FaceEmotionDetector.drawOverlay(yoloCanvas.value, videoEl, faceResult); }
              catch (e) { /* silent */ }
            }
            if (window.FaceEmotionDetector && FaceEmotionDetector.getDiagnostics) updateVisionDiag(FaceEmotionDetector.getDiagnostics());
            refreshRealtimeEmotion(faceResult || null);
            if (currentYoloEmotion.value && currentYoloEmotion.value.riskLevel === 'high') {
              yoloAlerts.value.unshift({
                emotion: currentYoloEmotion.value.text,
                severity: currentYoloEmotion.value.intensity,
                time: new Date().toTimeString().slice(0, 8)
              });
              if (yoloAlerts.value.length > 50) yoloAlerts.value = yoloAlerts.value.slice(0, 50);
            }
          } catch (e) { refreshRealtimeEmotion(null); }
        } else {
          refreshRealtimeEmotion(null);
          queueFaceApiLoad();
          await fallbackServerDetection(videoEl);
        }

        faceTimer = setTimeout(runFaceDetectionLoop, 600);
      }

      function runVoiceAnalysisLoop() {
        if (!yoloActive.value) return;
        if (voiceAnalyzer) {
          try {
            var vs = voiceAnalyzer.analyze();
            // 每 ~2.5s 上传一段音频到后端 emotion2vec（真模型语音情绪）
            var _now = Date.now();
            if (_now - lastVoiceUploadAt >= 2500) {
              lastVoiceUploadAt = _now;
              uploadVoiceChunk();
            }
            if (!currentYoloEmotion.value) refreshRealtimeEmotion(null);
            if (currentYoloEmotion.value) {
              currentYoloEmotion.value.speechRate = Math.round(vs.speechRate * 100);
              currentYoloEmotion.value.speechRateLabel = vs.speechRate > 0.45 ? '\u504f\u5feb' : '\u6b63\u5e38';
              currentYoloEmotion.value.pauseRatio = Math.round(vs.pauseRatio * 100);
              currentYoloEmotion.value.isSpeaking = vs.isSpeaking;
              currentYoloEmotion.value.audioVolume = Math.round((vs.volume || 0) * 100);
              currentYoloEmotion.value.pitch = Math.round(vs.pitch || 0);
              audioDiag.volume = currentYoloEmotion.value.audioVolume;
              audioDiag.pitch = currentYoloEmotion.value.pitch;
              audioDiag.speaking = !!vs.isSpeaking;
              audioDiag.analyzer = !!vs.analyzerReady;
              audioDiag.contextState = vs.contextState || '--';
              audioDiag.updatedAt = new Date().toTimeString().slice(0, 8);
              if (realtimeAudioStream) refreshAudioDiag('remote', realtimeAudioStream);
            }
          } catch (e) { refreshRealtimeEmotion(null); }
        } else if (!currentYoloEmotion.value) {
          refreshRealtimeEmotion(null);
        }
        voiceTimer = setTimeout(runVoiceAnalysisLoop, 1000);
      }

      async function fallbackServerDetection(videoEl) {
        try {
          var canvas = document.createElement('canvas');
          canvas.width = videoEl.videoWidth || 320; canvas.height = videoEl.videoHeight || 240;
          var ctx = canvas.getContext('2d'); ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
          var b64 = canvas.toDataURL('image/jpeg', 0.7);
          var d = await API.post('/emotion/yolo-detect', { image: b64 });
          if (d.success && d.emotions && d.emotions.length > 0) {
            var e = d.emotions[0];
            currentYoloEmotion.value = {
              icon: EmotionFusionEngine ? EmotionFusionEngine.emotionIcon(e.primary_emotion) : '😐',
              text: e.primary_emotion,
              confidence: Math.round(e.confidence * 100),
              intensity: Math.round(e.confidence * 10),
              color: EmotionFusionEngine ? EmotionFusionEngine.emotionColor(e.primary_emotion) : '#94a3b8',
              faceTension: '#10b981', faceLabel: '正常', gazeAvert: '#10b981', gazeLabel: '正常',
              posture: '#10b981', postureLabel: '正常', browFurrow: 0, gazeAversion: 0, headDownPercent: 0,
              postureStiffness: 0, postureStiffnessLabel: '\u6b63\u5e38', postureStiffnessColor: '#10b981',
              poseDetected: false, detectionSource: '--', shoulderSlope: 0, forwardHead: 0, slouch: 0, scratchHead: 0, touchNose: 0, handNearFace: 0, gazeInstability: 0,
              speechRate: 0, speechRateLabel: '--', pauseRatio: 0, isSpeaking: false
            };
            queueRealtimeLog();
            if (d.high_risk_alerts && d.high_risk_alerts.length) {
              d.high_risk_alerts.forEach(function(a) { yoloAlerts.value.unshift(a); });
              if (yoloAlerts.value.length > 50) yoloAlerts.value = yoloAlerts.value.slice(0, 50);
            }
          }
        } catch (e) { /* silent */ }
      }

      function toggleYolo() { if (yoloActive.value) stopYolo(); else startYolo(); }

      function startYolo() {
        var videoEl = teacherRemoteVideo.value;
        if (!videoEl || !videoEl.srcObject) { Toast.error('\u8bf7\u5148\u8fde\u63a5\u89c6\u9891\u901a\u8bdd'); return; }
        currentYoloEmotion.value = null;
        autoStartRealtimeEmotion(videoEl.srcObject, videoEl);
        Toast.success('\u5b9e\u65f6\u60c5\u7eea\u76d1\u6d4b\u5df2\u5f00\u542f');
      }

      function stopYolo() {
        yoloActive.value = false;
        realtimeVideoEl = null;
        realtimeAudioStream = null;
        audioDiag.analyzer = false;
        audioDiag.contextState = '--';
        audioDiag.volume = 0;
        audioDiag.pitch = 0;
        audioDiag.speaking = false;
        updateVisionDiag({ modelReady: false, faceDetected: false, poseDetected: false, detectionSource: '--', status: 'idle', lastUpdate: '--', lastError: '', failCount: 0, noFaceCount: 0, frameCount: 0, changedAt: '--', rawMicro: { browFurrow: 0, gazeAversion: 0, headDown: 0, postureStiffness: 0, shoulderSlope: 0, forwardHead: 0, slouch: 0, scratchHead: 0, touchNose: 0, handNearFace: 0, gazeInstability: 0 }, poseFrameCount: 0, poseNoLandmarkCount: 0, faceMeshFrameCount: 0, faceMeshDetected: false, faceMeshCropUsed: false, videoSize: '--', faceCropUsed: false });
        if (faceTimer) clearTimeout(faceTimer);
        if (voiceTimer) clearTimeout(voiceTimer);
        if (voiceAnalyzer) { voiceAnalyzer.stop(); voiceAnalyzer = null; }
        faceTimer = null; voiceTimer = null;
        lastRealtimeLogAt = 0;
        lastRealtimeLogKey = '';
        realtimeCallStartedAt = null;
        realtimeEmotionSamples.splice(0, realtimeEmotionSamples.length);
      }

      function stopAllRealtime() {
        stopYolo();
        if (voiceAnalyzer) { voiceAnalyzer.stop(); voiceAnalyzer = null; }
      }

      async function loadYoloLogs() {
        try { var d = await API.get('/emotion/yolo-logs', { limit: 20 }); if (d.data) yoloAlerts.value = d.data; }
        catch (e) { /* silent */ }
      }

      // ==================== 预约 ====================
      const appointments = ref([]);
      const counselors = ref([]);
      const newAppointment = reactive({ counselor_id: '', appointment_time: '', reason: '' });
      async function loadAppointments() {
        try { var d = await API.get('/appointments'); appointments.value = d.data || []; }
        catch (e) { /* silent */ }
      }
      async function createAppointment() {
        if (!newAppointment.counselor_id || !newAppointment.appointment_time) { Toast.error('请选择辅导员和预约时间'); return; }
        try {
          await API.post('/appointments/create', newAppointment);
          Toast.success('预约创建成功');
          newAppointment.counselor_id = ''; newAppointment.appointment_time = ''; newAppointment.reason = '';
          loadAppointments();
        } catch (e) { Toast.error('预约失败'); }
      }
      async function loadCounselors() {
        try { var d = await API.get('/counselors/list'); counselors.value = d.data || []; }
        catch (e) { /* silent */ }
      }

      // ==================== 心理测评 ====================
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
        if (!canProceedToNext()) { Toast.warning('请完成当前部分的所有题目'); return; }
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
          var d = await API.post('/assessment/submit', { answers: answers, duration_seconds: duration });
          if (d.success) { assessmentResult.value = d.data; loadAssessmentHistory(); Toast.success('测评完成'); }
          else { Toast.error(d.message || '提交失败'); }
        } catch (e) { Toast.error('提交失败'); }
        assessmentSubmitting.value = false;
      }

      function resetAssessment() { assessmentResult.value = null; initAssessment(); }

      async function crisisReport() {
        if (!confirm('确认要上报心理危机吗？辅导员与心理中心将尽快联系你。\n\n如有紧急危险，请立即拨打 120 / 110 或心理援助热线 400-161-9995。')) return;
        try {
          var d = await API.post('/crisis/report', { reason: '学生主动求助' });
          if (d && d.success) {
            Toast.success(d.message || '危机已上报');
            if (d.data && d.data.hotline) Toast.info('📞 ' + d.data.hotline);
            if (currentUser.role === 'student') { page.value = 'studentChat'; loadMessageContacts(); }
          } else {
            Toast.error(d.message || '上报失败');
          }
        } catch (e) { Toast.error('上报失败，请稍后重试'); }
      }

      async function loadAssessmentHistory() {
        try { var d = await API.get('/assessment/history'); assessmentHistory.value = d.data || []; }
        catch (e) { /* silent */ }
      }

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

      // ==================== 生命周期 ====================
      onMounted(function() {
        loadTestAccounts();
        if (isLoggedIn.value) {
          restoreSessionUser();
          var ut = localStorage.getItem('user_type') || 'staff';
          if (ut === 'student') {
            currentUser.role = 'student';
            page.value = 'studentHome';
            setRole();
            setTimeout(loadUnreadCount, 0);
            setTimeout(function(){ initSocket(); initStudentVideo(); }, 0);
          } else {
            // 管理员/学工处→情绪看板，辅导员→工作台
            var r = currentUser.role;
            if (r === 'super_admin' || r === 'student_affairs') {
              page.value = 'emotionBoard';
              loadEmotionDashboard();
            } else {
              page.value = 'dashboard';
              loadDash();
              loadWorkplan();
              dashInterval = setInterval(loadDash, 30000);
              setTimeout(function(){ initSocket(); initTeacherVideo(); }, 0);
            }
          }
        }
        loadWater(); loadMood();
        if (currentUser.role) setRole();
      });

      watch(page, function(p) {
        if (dashInterval) { clearInterval(dashInterval); dashInterval = null; }
        if (networkPoll) { clearInterval(networkPoll); networkPoll = null; }
        if (p === 'dashboard') { loadWorkplan(); dashInterval = setInterval(loadDash, 30000); }
        if (p === 'studentHome') { /* 首页纯本地渲染，无需API */ }
        if (p === 'students') loadStudents();
        if (p === 'reminders') loadReminders();
        if (p === 'emotionBoard') { loadEmotionDashboard(); dashInterval = setInterval(loadEmotionDashboard, 60000); }
        if (p === 'emotionNetwork') { loadEmotionNetwork(); networkPoll = setInterval(loadEmotionNetwork, 15000); }
        if (p === 'alerts') loadAlerts();
        if (p === 'teacherChat') { initSocket(); loadMessageContacts(); initTeacherVideo(); loadYoloLogs(); }
        if (p === 'studentChat') { initSocket(); initStudentVideo(); loadMessageContacts(); }
        if (p === 'studentAppointment') { loadCounselors(); loadAppointments(); }
      });

      async function loadStudentData() {
        // 并行加载，减少等待时间
        loadMessageContacts();
        loadUnreadCount();
        if (!counselors.value.length) {
          try { var d = await API.get('/counselors/list'); counselors.value = d.data || []; }
          catch (e) { console.warn("API silent error:", e); }
        }
      }

      // ==================== 数据导出 ====================
      async function exportData(type) {
        try {
          var d = await API.post('/data/export', { type: type, format: 'csv' });
          if (d && d.message) {
            Toast.success(d.message || '导出成功');
          } else {
            // 如果是文件下载，创建Blob下载
            var res = await fetch(API.BASE + '/data/export', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + API.getToken() },
              body: JSON.stringify({ type: type, format: 'csv' })
            });
            if (res.ok) {
              var blob = await res.blob();
              var url = URL.createObjectURL(blob);
              var a = document.createElement('a');
              a.href = url; a.download = type + '_' + new Date().toISOString().split('T')[0] + '.csv';
              a.click(); URL.revokeObjectURL(url);
              Toast.success('导出成功');
            }
          }
        } catch (e) { Toast.error('导出失败'); }
      }

      // 重新生成测试数据
      async function reSeedData() {
        if (confirm('确认重新生成所有测试数据？这将清除现有数据！')) {
          try {
            var res = await fetch(API.BASE + '/system/reseed', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + API.getToken() }
            });
            var d = await res.json();
            Toast.success(d.message || '数据已重新生成');
            setTimeout(function() { location.reload(); }, 1000);
          } catch (e) { Toast.error('重新生成失败，请手动运行 python seed_v31.py'); }
        }
      }

      return {
        // 认证
        isLoggedIn, loginForm, loginLoading, currentUser, roleLabel, handleLogin, handleLogout,
        loginType, showStudentRegister, studentLoginForm, studentRegisterForm,
        handleStudentLogin, handleStudentRegister,
        testAccounts, fillStaffAccount, fillCounselorAccount, fillStudentAccount,
        // 主题
        isDarkMode, toggleTheme,
        // 侧边栏
        sidebarCollapsed, sidebarMobileOpen, toggleSidebar,
        // 路由
        page, pageTitle,
        // Toast
        toasts, showToast,
        // 工作台
        wp, wpCalYear, wpCalMonth, wpCalRows, wpCalPrev, wpCalNext, wpSelectDay,
        loadWorkplan, wpCompleteTodo, wpTodoStudent, wpTodoWork,
        showAddTodo, newTodo, addCustomTodo, completeCustomTodo, calDayDetail,
        // 仪表盘
        dash, recentAlerts, loadDash, cPie, cTrend, cRisk, renderCharts,
        // 学生管理
        students, studentSearch, showAddStudent, newStudent, selectedStudent, studentProfiles,
        loadStudents, addStudent, viewStudent, updateStudentNotes, searchStudentsHandler,
        // 预警
        alerts, loadAlerts, ackAlert,
        // 提醒
        reminders, showCompleted, loadReminders, completeReminder,
        // 班会/公文
        meetingTheme, meetingResult, meetingLoading, generateMeeting,
        docType, docContent, docResult, docLoading, generateDoc,
        // 知识库
        kbStats, loadKbStats, uploadDoc,
        // 情绪看板
        emoDashStats, emoDashAlerts, realtimeEmotionLogs, emoPieChart, emoRiskChart, emoTrendChart, emoHeatmapChart,
        loadEmotionDashboard, seedRealtimeDemoData,
        // 情绪网络图
        networkGraph, networkFilter, networkCanvas, loadEmotionNetwork, toggleNetworkFilter,
        // 通讯
        messageContacts, teacherSelected, teacherChatMsgs, teacherNewMsg, teacherUnreadCount, teacherMsgRef,
        studentSearchQuery, studentSearchResults, searchStudentsHandler, inviteStudent,
        selectTeacherContact, sendTeacherMsg, guidanceResult, guidanceLoading, analyzeCounselorGuidance,
        fillTeacherMsg, guidanceRiskTagStyle, talkReport, talkReportLoading, generateTalkReport,
        selectedContact, chatMessages, newMessage, studentUnreadCount, studentMsgRef,
        loadMessageContacts, selectContactHandler, sendStudentMsg, loadUnreadCount,
        insertEmoji, insertTeacherEmoji, teacherShowEmoji, showEmoji, emojiList,
        openTeacherVideo, autoResize,
        // WebRTC 学生端
        audioDiag, visionDiag,
        localVideo, remoteVideo, isInCall, isVideoEnabled, isAudioEnabled,
        startVideoCall, endVideoCall, toggleVideo, toggleAudio,
        incomingStudentCall, acceptStudentCall, rejectStudentCall,
        // WebRTC 教师端
        teacherLocalVideo, teacherRemoteVideo, teacherInCall, teacherVideoEnabled, teacherAudioEnabled,
        incomingCall, initTeacherVideo, startTeacherVideo, endTeacherVideo,
        toggleTeacherVideo, toggleTeacherAudio, acceptVideoCall, rejectVideoCall,
        // 实时情绪
        yoloActive, currentYoloEmotion, yoloAlerts, yoloCanvas,
        toggleYolo, startYolo, stopYolo, loadYoloLogs,
        yoloEmotionShow, yoloEmotionDisplay, realtimeCallSummary,
        // 预约
        appointments, counselors, newAppointment, loadAppointments, createAppointment,
        // 测评
        assessmentStep, assessmentOptions, assessmentProgress, assessmentStepLabel,
        phq9Questions, gad7Questions, isiQuestions, currentStepQuestions, currentStepStart,
        assessmentAnswers, assessmentSubmitting, assessmentResult, assessmentHistory,
        initAssessment, submitAssessment, resetAssessment, loadAssessmentHistory, crisisReport,
        canProceedToNext, goToNextStep, goToPrevStep,
        // 学生Widget
        waterCount, waterProgress, addWater, resetWater,
        dailyQuote, dailyWord, todayMood, todayMoodText,
        loadMood, recordMood, todayStr, greetingText,
        // 工具
        Icons, Helpers,
        exportData, reSeedData
      };
    }
  }).mount('#app');
})();
