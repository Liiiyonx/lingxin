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
        } catch (e) { console.warn('测试账号加载失败', e); }
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
          docWriting: '公文写作', digitalHuman: 'AI 数字人', alerts: '风险预警', knowledge: '知识库', system: '系统管理',
          students: '学生管理', emotionBoard: '情绪看板', emotionNetwork: '情绪网络图', reminders: '提醒中心',
          studentHome: '我的首页', studentChat: '联系老师', studentAssessment: '心理测评',
          studentAppointment: '预约咨询', teacherAppointments: '预约管理', studentProfile: '个人中心'
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
            if (currentUser.role === 'counselor') { initTeacherVideo(); startPresencePing(); }
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
            if (currentUser.role === 'counselor') { initTeacherVideo(); startPresencePing(); }
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
        stopPresencePing();
      }

      function setRole() {
        var r = currentUser.role;
        document.documentElement.setAttribute('data-role',
          r === 'student' ? 'student' : r === 'super_admin' ? 'super_admin' : 'counselor');
        if (typeof networkClusterMode !== 'undefined' && typeof networkClusterBy !== 'undefined') {
          var schoolView = r === 'super_admin' || r === 'student_affairs';
          networkClusterMode.value = schoolView ? 'force' : 'auto';
          networkClusterBy.value = schoolView ? 'college' : 'class';
        }
      }

      // ==================== API 错误监听 ====================
      API.on('unauthorized', function() { handleLogout(); });
      API.on('critical-error', function(payload) {
        Toast.error(payload.message || '操作失败，请稍后重试', '重试', payload.retry);
      });

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
        } catch (e) { console.warn('工作台数据加载失败', e); }
      }

      async function loadDash() {
        try {
          var d = await API.get('/system/dashboard');
          if (d) { Object.assign(dash, d); setTimeout(renderCharts, 400); }
        } catch (e) { console.warn('仪表盘数据加载失败', e); }
        try {
          var a = await API.get('/alert/list', { limit: 5 });
          recentAlerts.value = a.data || a.items || [];
        } catch (e) { console.warn('预警列表加载失败', e); }
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

      function ensureChart(inst, el, dark) {
        var disposed = inst && inst.isDisposed ? inst.isDisposed() : false;
        if (inst && !disposed && inst.__themeDark === dark) {
          inst.clear();
          return inst;
        }
        if (inst && !disposed) inst.dispose();
        var next = echarts.init(el, dark ? 'dark' : undefined);
        next.__themeDark = dark;
        return next;
      }

      function renderCharts() {
        if (typeof echarts === 'undefined') { window._loadECharts && window._loadECharts(function(){renderCharts();}); return; }
        try {
          if (cPie.value) {
            pieChart = ensureChart(pieChart, cPie.value, isDarkMode.value);
            var dist = dash.emotion_distribution || {};
            var data = Object.entries(dist).map(function(e) { return { name: e[0], value: e[1] }; });
            pieChart.setOption({
              tooltip: { trigger: 'item' },
              series: [{ type: 'pie', radius: ['40%', '70%'], label: { show: true, fontSize: 11 },
                data: data.length ? data : [{ name: '暂无数据', value: 1 }],
                color: ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#3b82f6']
              }]
            }, { notMerge: true });
          }
        } catch (e) { console.warn('图表渲染失败', e); }
      }

      // ==================== 学生管理 ====================
      const students = ref([]);
      const studentsLoading = ref(false);
      const studentSearch = ref('');
      const showAddStudent = ref(false);
      const newStudent = reactive({ student_id: '', name: '', gender: '', college: '', class_name: '', phone: '', notes: '' });
      const selectedStudent = ref(null);
      const studentProfiles = ref([]);
      const studentRiskTimeline = ref([]);
      const studentRiskTimelineLoading = ref(false);
      const showStudentRiskTimeline = ref(false);
      const manualRiskLevel = ref('low');
      const manualRiskReason = ref('');

      const searchStudentsDebounced = Helpers.debounce(async function() {
        studentsLoading.value = true;
        try {
          var d = await API.get('/student/list', { search: studentSearch.value, per_page: 100 });
          students.value = d.data || [];
        } catch (e) { console.warn('学生列表加载失败', e); }
        finally { studentsLoading.value = false; }
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
          if (window._loadMarkdown) await window._loadMarkdown();
          studentProfiles.value = p.data || [];
          showStudentRiskTimeline.value = false;
          studentRiskTimeline.value = [];
          manualRiskLevel.value = selectedStudent.value.risk_level || 'low';
          manualRiskReason.value = '';
          loadStudentRiskTimeline(sid);
        } catch (e) { Toast.error('获取详情失败'); }
      }

      async function updateStudentNotes(sid, notes) {
        try { await API.put('/student/' + sid, { notes: notes }); Toast.success('备注已更新'); }
        catch (e) { console.warn('学生备注保存失败', e); }
      }

      async function loadStudentRiskTimeline(sid) {
        if (!sid) return;
        studentRiskTimelineLoading.value = true;
        try {
          var d = await API.get('/student/' + sid + '/risk-timeline');
          studentRiskTimeline.value = d.data || [];
        } catch (e) {
          console.warn('学生风险时间线加载失败', e);
          studentRiskTimeline.value = [];
        } finally {
          studentRiskTimelineLoading.value = false;
        }
      }

      function toggleStudentRiskTimeline() {
        showStudentRiskTimeline.value = !showStudentRiskTimeline.value;
        if (showStudentRiskTimeline.value && selectedStudent.value && !studentRiskTimeline.value.length) {
          loadStudentRiskTimeline(selectedStudent.value.id);
        }
      }

      async function adjustStudentRisk() {
        if (!selectedStudent.value) return;
        var sid = selectedStudent.value.id;
        try {
          var d = await API.put('/student/' + sid + '/risk', {
            risk_level: manualRiskLevel.value,
            reason: manualRiskReason.value.trim() || '辅导员人工调整风险等级'
          });
          if (d.success) {
            Toast.success('风险等级已调整');
            var fresh = await API.get('/student/' + sid);
            selectedStudent.value = fresh.data || selectedStudent.value;
            manualRiskLevel.value = selectedStudent.value.risk_level || 'low';
            manualRiskReason.value = '';
            await loadStudentRiskTimeline(sid);
          } else {
            Toast.error(d.message || '调整失败');
          }
        } catch (e) {
          Toast.error(e.message || '调整失败，请稍后重试');
        }
      }

      // ==================== 预警 ====================
      const alerts = ref([]);
      const alertsLoading = ref(false);
      const alertStatusFilter = ref('pending');
      const crisisOnly = ref(false);
      const resolvingAlert = ref(null);
      const resolveNote = ref('');
      const resolveSubmitting = ref(false);
      const crisisCounselors = ref([]);
      const assigningCrisisAlert = ref(null);
      const crisisAssignTo = ref('');
      const crisisAssignSubmitting = ref(false);
      const filteredAlerts = computed(function() {
        var status = alertStatusFilter.value;
        if (status === 'all') return alerts.value;
        return alerts.value.filter(function(a) { return a.status === status; });
      });
      const alertStatusCounts = computed(function() {
        var counts = { all: alerts.value.length, pending: 0, acknowledged: 0, resolved: 0 };
        alerts.value.forEach(function(a) {
          if (counts[a.status] !== undefined) counts[a.status] += 1;
        });
        return counts;
      });
      async function loadAlerts() {
        alertsLoading.value = true;
        try {
          var endpoint = crisisOnly.value && ['super_admin', 'student_affairs'].indexOf(currentUser.role) !== -1
            ? '/alert/crisis-center'
            : '/alert/list';
          var d = await API.get(endpoint, { per_page: 100, status: alertStatusFilter.value === 'all' ? '' : alertStatusFilter.value });
          alerts.value = d.data || d.items || [];
        }
        catch (e) { Toast.error('预警列表加载失败'); }
        finally { alertsLoading.value = false; }
      }
      function toggleCrisisOnly() {
        crisisOnly.value = !crisisOnly.value;
        loadAlerts();
      }
      async function loadCrisisCounselors() {
        try {
          var d = await API.get('/counselors/list');
          crisisCounselors.value = d.data || [];
        } catch (e) {
          console.warn('辅导员列表加载失败', e);
        }
      }
      function openAssignCrisisAlert(a) {
        assigningCrisisAlert.value = a;
        crisisAssignTo.value = a.assigned_to || '';
        loadCrisisCounselors();
      }
      function closeAssignCrisisAlert() {
        assigningCrisisAlert.value = null;
        crisisAssignTo.value = '';
      }
      async function submitAssignCrisisAlert() {
        var alert = assigningCrisisAlert.value;
        if (!alert) return;
        var assignedTo = parseInt(crisisAssignTo.value, 10);
        if (!assignedTo) {
          Toast.warning('请选择指派辅导员');
          return;
        }
        crisisAssignSubmitting.value = true;
        try {
          await API.put('/alert/crisis-center/' + alert.id + '/assign', { assigned_to: assignedTo });
          Toast.success('危机工单已指派');
          closeAssignCrisisAlert();
          await loadAlerts();
        } catch (e) {
          Toast.error(e.message || '指派失败，请稍后重试');
        } finally {
          crisisAssignSubmitting.value = false;
        }
      }
      async function closeCrisisAlert(a) {
        if (!a) return;
        var resolution = window.prompt('关闭备注（可选）：', '已完成危机处置并确认学生安全');
        if (resolution === null) return;
        try {
          await API.put('/alert/crisis-center/' + a.id + '/close', { resolution: resolution.trim() });
          Toast.success('危机工单已关闭，学生风险已重算');
          await loadAlerts();
        } catch (e) {
          Toast.error(e.message || '关闭失败，请稍后重试');
        }
      }
      async function ackAlert(id) {
        try {
          await API.put('/alert/' + id + '/acknowledge');
          Toast.success('预警已确认，可进入处置流程');
          if (resolvingAlert.value && resolvingAlert.value.id === id) {
            resolvingAlert.value = Object.assign({}, resolvingAlert.value, { status: 'acknowledged' });
          }
          await loadAlerts();
        } catch (e) {
          Toast.error(e.message || '确认失败，请稍后重试');
        }
      }
      function openResolveAlert(a) {
        resolvingAlert.value = a;
        resolveNote.value = a.resolution || '';
      }
      function closeResolveAlert() {
        resolvingAlert.value = null;
        resolveNote.value = '';
      }
      async function submitResolveAlert() {
        var alert = resolvingAlert.value;
        if (!alert) return;
        if (!resolveNote.value.trim()) {
          Toast.warning('请填写处理备注，便于后续回访与归档');
          return;
        }
        resolveSubmitting.value = true;
        try {
          await API.put('/alert/' + alert.id + '/resolve', { resolution: resolveNote.value.trim() });
          Toast.success('预警已解决并归档');
          closeResolveAlert();
          await loadAlerts();
        } catch (e) {
          Toast.error(e.message || '解决失败，请稍后重试');
        } finally {
          resolveSubmitting.value = false;
        }
      }
      async function escalateAlert(id) {
        var note = window.prompt('升级说明（可选）：', '建议心理中心/学工处协同处置');
        if (note === null) return;
        try {
          await API.put('/alert/' + id + '/escalate', { note: note });
          Toast.success('已升级至心理中心/学工处');
          await loadAlerts();
        } catch (e) {
          Toast.error(e.message || '升级失败，请稍后重试');
        }
      }

      // ==================== 提醒 ====================
      const reminders = ref([]);
      const showCompleted = ref(false);
      async function loadReminders() {
        try { var d = await API.get('/student/reminder/list'); reminders.value = d.data || []; }
        catch (e) { console.warn('提醒列表加载失败', e); }
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
          if (window._loadMarkdown) await window._loadMarkdown();
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
          if (window._loadMarkdown) await window._loadMarkdown();
          docResult.value = d.content || d.result || '生成失败';
        } catch (e) { docResult.value = '请求失败'; }
        docLoading.value = false;
      }

      // ==================== 知识库 ====================
      const kbStats = ref(null);
      const kbDocs = ref([]);
      const kbLoading = ref(false);
      const kbDeleting = ref(null);
      async function loadKbStats() {
        try { var d = await API.get('/knowledge/stats'); if (d && d.data) kbStats.value = d.data; }
        catch (e) { console.warn('知识库统计加载失败', e); }
      }
      async function loadKbDocs() {
        try {
          var d = await API.get('/knowledge/documents');
          kbDocs.value = (d && (d.data || d.items)) || [];
        } catch (e) { console.warn('知识库文档列表加载失败', e); }
      }
      async function loadKnowledge() {
        kbLoading.value = true;
        try { await Promise.all([loadKbStats(), loadKbDocs()]); }
        finally { kbLoading.value = false; }
      }
      async function uploadDoc(e) {
        var f = e.target.files[0]; if (!f) return;
        var fd = new FormData(); fd.append('file', f);
        try { var d = await API.upload('/knowledge/upload', fd); Toast.success(d.message || '上传成功'); loadKnowledge(); }
        catch (e) { Toast.error('上传失败'); }
        finally { e.target.value = ''; }
      }
      async function deleteKbDoc(docId) {
        if (!confirm('确认删除该知识库文档？删除后不可恢复。')) return;
        kbDeleting.value = docId;
        try {
          var d = await API.del('/knowledge/documents/' + encodeURIComponent(docId));
          Toast.success(d.message || '文档已删除');
          loadKnowledge();
        } catch (e) { Toast.error('删除失败'); }
        finally { kbDeleting.value = null; }
      }

      // ==================== 情绪看板 ====================
      const emoDashStats = reactive({ total: 0, highRisk: 0, mediumRisk: 0, avgIntensity: 0 });
      const emoDashAlerts = ref([]);
      const realtimeEmotionLogs = ref([]);
      const emoBoardLoading = ref(false);
      const emoPieChart = ref(null), emoRiskChart = ref(null), emoTrendChart = ref(null), emoHeatmapChart = ref(null);
      let emoPieInst = null, emoRiskInst = null, emoTrendInst = null, emoHeatInst = null;

      async function loadEmotionDashboard() {
        emoBoardLoading.value = true;
        try {
          var s = await API.get('/emotion/statistics');
          if (s && s.data) {
            emoDashStats.total = s.data.total || 0;
            emoDashStats.highRisk = s.data.high_risk_count || 0;
            emoDashStats.mediumRisk = s.data.medium_risk_count || 0;
            emoDashStats.avgIntensity = s.data.avg_intensity || 0;
          }
        } catch (e) { console.warn('情绪统计加载失败', e); }
        try { var a = await API.get('/alert/list', { per_page: 10 }); emoDashAlerts.value = a.data || a.items || []; }
        catch (e) { console.warn('情绪预警加载失败', e); }
        try { var logs = await API.get('/emotion/logs', { per_page: 12 }); realtimeEmotionLogs.value = logs.data || []; }
        catch (e) { console.warn('情绪日志加载失败', e); }
        emoBoardLoading.value = false;
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
          emoPieInst = ensureChart(emoPieInst, emoPieChart.value, isDark);
          var pieChart = emoPieInst;
          API.get('/emotion/statistics').then(function(d) {
            var dist = d && d.data ? d.data.emotion_distribution : {};
            var data = Object.entries(dist || {}).map(function(e) { return { name: e[0], value: e[1].count || e[1] }; });
            if (pieChart.isDisposed && pieChart.isDisposed()) return;
            pieChart.setOption({
              tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
              series: [{
                type: 'pie', radius: ['45%', '75%'], roseType: 'area',
                itemStyle: { borderRadius: 6, borderColor: isDark ? '#1e293b' : '#fff', borderWidth: 3 },
                label: { fontSize: 11 },
                data: data.length ? data : [{ name: '暂无', value: 1 }],
                color: ['#6366f1', '#8b5cf6', '#f59e0b', '#ef4444', '#10b981', '#3b82f6', '#e67e22', '#f97316', '#94a3b8']
              }]
            }, { notMerge: true });
          }).catch(function() {});
        }
        // Risk ring
        if (emoRiskChart.value) {
          emoRiskInst = ensureChart(emoRiskInst, emoRiskChart.value, isDark);
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
          }, { notMerge: true });
        }
        // Trend
        if (emoTrendChart.value) {
          emoTrendInst = ensureChart(emoTrendInst, emoTrendChart.value, isDark);
          var trendChart = emoTrendInst;
          API.get('/emotion/trends', { days: 7 }).then(function(d) {
            var data = d && d.data ? d.data : [];
            var labels = [], vals = [];
            if (Array.isArray(data)) {
              data.forEach(function(item) { labels.push(item.date || item.day || ''); vals.push(item.count || item.avg_intensity || 0); });
            }
            if (trendChart.isDisposed && trendChart.isDisposed()) return;
            trendChart.setOption({
              tooltip: { trigger: 'axis' },
              grid: { top: 10, right: 10, bottom: 20, left: 35 },
              xAxis: { type: 'category', data: labels.length ? labels : ['暂无数据'], axisLabel: { fontSize: 10 } },
              yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
              series: [{
                type: 'line', data: vals.length ? vals : [0], smooth: true,
                areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(99,102,241,0.35)' }, { offset: 1, color: 'rgba(99,102,241,0.02)' }] } },
                lineStyle: { color: '#6366f1', width: 2 }, itemStyle: { color: '#6366f1' }, symbol: 'circle', symbolSize: 6
              }]
            }, { notMerge: true });
          }).catch(function() {});
        }
        // Heatmap
        if (emoHeatmapChart.value) {
          emoHeatInst = ensureChart(emoHeatInst, emoHeatmapChart.value, isDark);
          var heatChart = emoHeatInst;
          API.get('/emotion/heatmap').then(function(d) {
            var data = d && d.data ? d.data : [];
            var hData = [];
            if (data.matrix && data.emotion_labels && data.intensity_labels) {
              for (var i = 0; i < data.matrix.length; i++)
                for (var j = 0; j < data.matrix[i].length; j++)
                  hData.push([j, i, data.matrix[i][j] || 0]);
              if (heatChart.isDisposed && heatChart.isDisposed()) return;
              heatChart.setOption({
                tooltip: { formatter: function(p) { return data.emotion_labels[p.value[1]] + ' ' + data.intensity_labels[p.value[0]] + ': ' + p.value[2] + '次'; } },
                grid: { top: 5, right: 10, bottom: 15, left: 70 },
                xAxis: { type: 'category', data: data.intensity_labels || [], axisLabel: { fontSize: 9 }, position: 'top' },
                yAxis: { type: 'category', data: data.emotion_labels || [], axisLabel: { fontSize: 10 } },
                visualMap: { min: 0, max: Math.max.apply(null, hData.map(function(h) { return h[2]; })) || 10, calculable: true, orient: 'vertical', right: 0, bottom: '15%', inRange: { color: ['#eef2ff', '#c7d2fe', '#818cf8', '#6366f1', '#4338ca'] }, textStyle: { fontSize: 9 } },
                series: [{ type: 'heatmap', data: hData, label: { show: true, fontSize: 9 }, emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.25)' } } }]
              }, { notMerge: true });
            }
          }).catch(function() {});
        }
      }

      // ==================== 情绪网络图 ====================
      const networkGraph = ref(null);
      const networkFilter = ref(['high', 'medium', 'low']);
      const networkCanvas = ref(null);
      const networkFollowUp = ref(false);
      const networkVisibleCount = ref(0);
      const networkSearch = ref('');
      const networkHover = ref(null);
      const networkLoading = ref(false);
      const networkClusterMode = ref('auto');
      const networkClusterBy = ref('class');
      let networkGraphInst = null;
      let networkGraphCanvasEl = null;
      let networkPoll = null;

      const RISK_LABELS = { high: '高风险', medium: '中风险', low: '低风险' };
      const RISK_COLORS = { high: '#ef4444', medium: '#f59e0b', low: '#10b981' };
      const networkTipStyle = computed(function() {
        if (!networkHover.value) return {};
        var x = networkHover.value.x + 16, y = networkHover.value.y - 12;
        // 防止卡片溢出画布右/下边缘
        if (networkCanvas.value) {
          var wrap = networkCanvas.value.parentElement;
          if (wrap) {
            var w = wrap.getBoundingClientRect();
            if (x + 250 > w.width) x = networkHover.value.x - 258;
            if (y + 110 > w.height) y = w.height - 118;
          }
        }
        return { left: x + 'px', top: Math.max(6, y) + 'px' };
      });

      function jumpToStudentChat(student) {
        if (!student || !student.db_id) return;
        var contact = { id: student.db_id, name: student.name, student_id: student.student_no };
        page.value = 'teacherChat';
        selectTeacherContact(contact);
        Toast.success('已跳转到 ' + student.name + ' 的对话');
      }

      function onNetworkHover(info) {
        if (!info) { networkHover.value = null; return; }
        networkHover.value = {
          node: info.node,
          x: info.x, y: info.y,
          riskLabel: info.node.kind === 'student' ? RISK_LABELS[info.node.risk] : '',
          riskColor: info.node.kind === 'student' ? RISK_COLORS[info.node.risk] : ''
        };
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
            clusterMode: networkClusterMode.value,
            clusterBy: networkClusterBy.value,
            onStudentClick: jumpToStudentChat,
            onHover: onNetworkHover,
            onVisibleChange: function(n) { networkVisibleCount.value = n; }
          });
        }
        if (networkGraphInst && networkGraph.value) {
          networkGraphInst.setData(networkGraph.value);
        }
        return networkGraphInst;
      }

      async function loadEmotionNetwork() {
        networkLoading.value = true;
        try {
          var d = await API.get('/network/emotion-graph');
          if (d && d.success && d.data) {
            networkGraph.value = d.data;
            await nextTick();
            var g = ensureNetworkGraph();
            if (g) {
              g.setSeverityFilter(networkFilter.value.slice());
              g.setFollowUpMode(networkFollowUp.value);
              g.setClusterMode(networkClusterMode.value);
              g.setClusterBy(networkClusterBy.value);
              if (networkSearch.value) g.setSearchQuery(networkSearch.value);
            }
          }
        } catch (e) { console.warn('情绪网络图加载失败', e); }
        finally { networkLoading.value = false; }
      }

      function toggleNetworkFilter(level) {
        if (networkFollowUp.value && level === 'low') return;
        var i = networkFilter.value.indexOf(level);
        if (i >= 0) {
          if (networkFilter.value.length > 1) networkFilter.value.splice(i, 1);
        } else {
          networkFilter.value.push(level);
        }
        var g = ensureNetworkGraph();
        if (g) g.setSeverityFilter(networkFilter.value.slice());
      }

      function setNetworkFollowUp(on) {
        networkFollowUp.value = !!on;
        var g = ensureNetworkGraph();
        if (g) g.setFollowUpMode(networkFollowUp.value);
      }

      function setNetworkClusterMode(mode) {
        networkClusterMode.value = mode;
        var g = ensureNetworkGraph();
        if (g) g.setClusterMode(mode);
      }

      function setNetworkClusterBy(by) {
        networkClusterBy.value = by;
        var g = ensureNetworkGraph();
        if (g) g.setClusterBy(by);
      }

      function onNetworkSearchInput() {
        var g = ensureNetworkGraph();
        if (g) g.setSearchQuery(networkSearch.value);
      }

      function locateNetworkStudent() {
        if (!networkSearch.value.trim()) return;
        var g = ensureNetworkGraph();
        if (g && g.locateFirstMatch()) {
          Toast.success('已定位到 ' + networkSearch.value.trim());
        } else {
          Toast.error('未找到匹配的学生');
        }
      }

      function networkZoom(action) {
        var g = ensureNetworkGraph();
        if (!g) return;
        if (action === 'in') g.zoomIn();
        else if (action === 'out') g.zoomOut();
        else g.resetView();
      }

      // ==================== Socket.IO ====================
      let socket = null;
      let socketInitTimer = null;
      let socketLoading = false;
      let dashInterval = null;
      function initSocket() {
        if (socket) return;
        if (typeof io === 'undefined') {
          if (socketLoading) return;
          if (window._loadSocketIO) {
            socketLoading = true;
            window._loadSocketIO(function() {
              socketLoading = false;
              if (typeof io !== 'undefined') {
                initSocket();
                if (currentUser.role === 'student') initStudentVideo();
                if (currentUser.role === 'counselor') initTeacherVideo();
              } else if (!socketInitTimer) {
                socketInitTimer = setTimeout(function() {
                  socketInitTimer = null;
                  initSocket();
                }, 3000);
              }
            });
            return;
          }
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
        socket.on('connect_error', function() { console.warn('Socket连接失败，准备自动重试'); });
        // 视频通话情绪总结落库后，实时刷新情绪网络图
        socket.on('emotion_graph_update', function(data) {
          loadEmotionNetwork();
        });
        socket.on('alert_created', function(alert) {
          if (!alert || currentUser.role === 'student') return;
          loadAlerts();
          if (alert.risk_level === 'high' || alert.risk_level === 'critical') {
            Toast.warning('🚨 数字人识别到危机信号：' + (alert.student_name || '未知学生') + '，请立即处理');
          } else {
            Toast.info('收到新的风险预警：' + (alert.student_name || '未知学生'));
          }
        });
        socket.on('new_message', function(msg) {
          function existsIn(arr) {
            return !!(msg && msg.id) && arr.some(function(m) { return m.id === msg.id; });
          }
          if (page.value === 'teacherChat' && teacherSelected.value) {
            var counselorId = Number(currentUser.user_id || currentUser.id);
            var studentId = Number(teacherSelected.value.id);
            var teacherRelevant = true;
            if (msg.counselor_id !== undefined && msg.counselor_id !== null) teacherRelevant = Number(msg.counselor_id) === counselorId;
            if (teacherRelevant && msg.student_id !== undefined && msg.student_id !== null) teacherRelevant = Number(msg.student_id) === studentId;
            if (teacherRelevant && !existsIn(teacherChatMsgs.value)) teacherChatMsgs.value.push(msg);
            if (teacherRelevant) nextTick(function() { if (teacherMsgRef.value) teacherMsgRef.value.scrollTop = teacherMsgRef.value.scrollHeight; });
          }
          if (page.value === 'studentChat' && selectedContact.value) {
            var studentDbId = Number(currentUser.id);
            var contactCounselorId = Number(selectedContact.value.id);
            var studentRelevant = true;
            if (msg.student_id !== undefined && msg.student_id !== null) studentRelevant = Number(msg.student_id) === studentDbId;
            if (studentRelevant && msg.counselor_id !== undefined && msg.counselor_id !== null) studentRelevant = Number(msg.counselor_id) === contactCounselorId;
            if (studentRelevant && !existsIn(chatMessages.value)) chatMessages.value.push(msg);
            if (studentRelevant && msg.sender_type === 'assistant') assistantTyping.value = false;
            if (studentRelevant) nextTick(function() { if (studentMsgRef.value) studentMsgRef.value.scrollTop = studentMsgRef.value.scrollHeight; });
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
      const assistantTyping = ref(false);
      const teacherShowEmoji = ref(false);
      const showEmoji = ref(false);
      const guidanceResult = ref(null);
      const guidanceLoading = ref(false);

      const searchStudentsHandler = Helpers.debounce(async function() {
        if (!studentSearchQuery.value.trim()) { studentSearchResults.value = []; return; }
        try {
          var d = await API.get('/student/list', { search: studentSearchQuery.value, per_page: 10 });
          studentSearchResults.value = d.data || [];
        } catch (e) { console.warn('学生搜索失败', e); }
      }, 300);

      async function inviteStudent(s) {
        studentSearchQuery.value = ''; studentSearchResults.value = [];
        var sentId = Date.now();
        try {
          var d = await API.post('/messages/send', { contact_id: s.id, content: '老师向您发起了对话' });
          if (d && d.data && d.data.id) sentId = d.data.id;
        } catch (e) {
          console.error('发起对话失败', e);
          return;
        }
        teacherSelected.value = { id: s.id, name: s.name, student_id: s.student_id };
        teacherChatMsgs.value = [{
          id: sentId,
          student_id: s.id,
          counselor_id: currentUser.user_id || currentUser.id,
          content: '老师向您发起了对话',
          sender_type: 'counselor',
          created_at: new Date().toISOString()
        }];
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
        } catch (e) {
          console.error('加载聊天记录失败', e);
          teacherChatMsgs.value = [];
          Toast.error('加载聊天记录失败，请稍后重试');
        }
      }

      async function sendTeacherMsg() {
        if (!teacherNewMsg.value.trim() || !teacherSelected.value) return;
        try {
          var d = await API.post('/messages/send', { contact_id: teacherSelected.value.id, content: teacherNewMsg.value });
          var msg = teacherNewMsg.value;
          teacherNewMsg.value = '';
          var msgId = d && d.data && d.data.id ? d.data.id : Date.now();
          teacherChatMsgs.value.push({
            id: msgId,
            student_id: teacherSelected.value.id,
            counselor_id: currentUser.user_id || currentUser.id,
            content: msg,
            sender_type: 'counselor',
            created_at: new Date().toISOString()
          });
          await nextTick();
          if (teacherMsgRef.value) teacherMsgRef.value.scrollTop = teacherMsgRef.value.scrollHeight;
          loadMessageContacts();
        } catch (e) { console.error('发送消息失败', e); }
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
            if (window._loadMarkdown) await window._loadMarkdown();
            talkReport.value = d.data.report || null;
            Toast.success('谈心记录已生成并归档到学生档案');
          } else {
            Toast.error(d.message || '生成失败');
          }
        } catch (e) { console.error('生成谈心记录失败', e); }
        talkReportLoading.value = false;
      }

      function printTalkReport() {
        if (!talkReport.value) return;
        var openPrint = function() {
          var html = Helpers.renderMd(talkReport.value.summary || '');
          var printWindow = window.open('', '_blank', 'width=860,height=1000');
          if (!printWindow) {
            Toast.error('浏览器拦截了打印窗口，请允许本站弹出窗口后重试');
            return;
          }
          printWindow.document.write(
            '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">' +
            '<title>谈心记录报告</title><style>' +
            'body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#1e293b;background:#fff;margin:0;padding:32px;line-height:1.75}' +
            '.report{max-width:820px;margin:0 auto}h1,h2,h3{color:#4f46e5;line-height:1.35}' +
            'p,li{font-size:14px}@media print{body{padding:0}}' +
            '</style></head><body><div class="report">' + html + '</div>' +
            '<script>window.onload=function(){window.print();};</' + 'script></body></html>'
          );
          printWindow.document.close();
        };
        if (window._loadMarkdown) {
          window._loadMarkdown(openPrint);
        } else {
          openPrint();
        }
      }

      async function loadMessageContacts() {
        try { var d = await API.get('/messages/contacts'); messageContacts.value = d.data || []; }
        catch (e) { console.warn('联系人列表加载失败', e); }
        if (currentUser.role === 'student' && selectedContact.value) {
          loadContactPresence(selectedContact.value.id);
        }
      }

      async function selectContactHandler(contact, keepTyping) {
        if (!keepTyping) assistantTyping.value = false;
        if (selectedContact.value && socket) {
          socket.emit('leave', { room: 'student_chat_' + currentUser.id + '_' + selectedContact.value.id });
        }
        selectedContact.value = contact;
        if (socket) { socket.emit('join', { room: 'student_chat_' + currentUser.id + '_' + contact.id }); }
        if (currentUser.role === 'student') loadContactPresence(contact.id);
        try {
          var d = await API.get('/messages/' + contact.id);
          chatMessages.value = (d.data || []).reverse();
          if (keepTyping) {
            var ordered = chatMessages.value;
            var latest = ordered[ordered.length - 1];
            if (latest && latest.sender_type === 'assistant') assistantTyping.value = false;
          }
          await nextTick();
          if (studentMsgRef.value) studentMsgRef.value.scrollTop = studentMsgRef.value.scrollHeight;
          loadMessageContacts();
        } catch (e) {
          console.error('加载聊天记录失败', e);
          chatMessages.value = [];
          Toast.error('加载聊天记录失败，请稍后重试');
        }
      }

      async function sendStudentMsg() {
        if (!newMessage.value.trim() || !selectedContact.value) return;
        try {
          var d = await API.post('/messages/send', { contact_id: selectedContact.value.id, content: newMessage.value });
          var pending = !!(d && d.data && d.data.ai_reply_pending);
          if (pending) assistantTyping.value = true;
          newMessage.value = '';
          await selectContactHandler(selectedContact.value, pending);
        } catch (e) { console.error('发送消息失败', e); }
      }

      async function loadUnreadCount() {
        try { var d = await API.get('/messages/unread'); var c = d.data ? d.data.unread_count : 0; studentUnreadCount.value = c; }
        catch (e) { console.warn('未读消息数加载失败', e); }
      }

      function insertEmoji(e) { newMessage.value += e; showEmoji.value = false; }
      function insertTeacherEmoji(e) { teacherNewMsg.value += e; teacherShowEmoji.value = false; }

      // ==================== AI 数字人 ====================
      const dh = window.DigitalHumanModule.setup({ API, Toast, currentUser });

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
        if (currentUser.role === 'counselor' && (currentUser.user_id || currentUser.id)) {
          socket.emit('join', { room: 'teacher_chat_' + (currentUser.user_id || currentUser.id) });
        }
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
              catch (e) { console.warn('人脸情绪覆盖层绘制失败', e); }
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
        } catch (e) { console.warn('服务端人脸情绪检测失败', e); }
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
        catch (e) { console.warn('实时情绪日志加载失败', e); }
      }

      // ==================== 预约 ====================
      const appointmentMod = window.AppointmentsModule.setup({ API, Toast, loadReminders });

      // ==================== 心理测评 ====================
      const assessmentMod = window.AssessmentModule.setup({ API, Toast, currentUser, page, loadMessageContacts });

      const {
        dhSettings, dhLogs, dhPreviewMsgs, dhPreviewInput, dhPreviewLoading,
        dhQuickQs, dhVoiceEnabled, contactPresence,
        loadDigitalHuman, saveDigitalHuman, loadDigitalHumanLogs, markDigitalHumanLogHandled,
        askDigitalHuman, speakDigitalHuman, stopDigitalHumanSpeech,
        loadContactPresence, startPresencePing, stopPresencePing
      } = dh;

      const {
        appointments, counselors, newAppointment, appointmentFilter,
        appointmentNotes, updatingAppointmentId,
        loadAppointments, setAppointmentFilter, createAppointment,
        updateAppointmentStatus, loadCounselors
      } = appointmentMod;

      const {
        assessmentStep, assessmentOptions, assessmentProgress, assessmentStepLabel,
        phq9Questions, gad7Questions, isiQuestions, currentStepQuestions, currentStepStart,
        assessmentAnswers, assessmentSubmitting, assessmentResult, assessmentHistory,
        initAssessment, submitAssessment, resetAssessment, loadAssessmentHistory,
        crisisReport, canProceedToNext, goToNextStep, goToPrevStep
      } = assessmentMod;

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
              loadAppointments();
              dashInterval = setInterval(loadDash, 30000);
              setTimeout(function(){ initSocket(); initTeacherVideo(); }, 0);
              if (currentUser.role === 'counselor') startPresencePing();
            }
          }
        }
        loadWater(); loadMood();
        if (currentUser.role) setRole();
      });

      watch(page, function(p) {
        stopDigitalHumanSpeech();
        if (dashInterval) { clearInterval(dashInterval); dashInterval = null; }
        if (networkPoll) { clearInterval(networkPoll); networkPoll = null; }
        if (p === 'dashboard') { loadWorkplan(); dashInterval = setInterval(loadDash, 30000); }
        if (p === 'studentHome') { loadStudentTrend(); }
        if (p === 'students') loadStudents();
        if (p === 'reminders') loadReminders();
        if (p === 'emotionBoard') { loadEmotionDashboard(); dashInterval = setInterval(loadEmotionDashboard, 60000); }
        if (p === 'emotionNetwork') { loadEmotionNetwork(); networkPoll = setInterval(loadEmotionNetwork, 15000); }
        if (p === 'alerts') loadAlerts();
        if (p === 'knowledge') loadKnowledge();
        if (p === 'teacherChat') { initSocket(); loadMessageContacts(); initTeacherVideo(); loadYoloLogs(); }
        if (p === 'studentChat') { initSocket(); initStudentVideo(); loadMessageContacts(); }
        if (p === 'studentAppointment') { loadCounselors(); loadAppointments(); }
        if (p === 'teacherAppointments') loadAppointments();
      });

      async function loadStudentData() {
        // 并行加载，减少等待时间
        loadMessageContacts();
        loadUnreadCount();
        if (!counselors.value.length) {
          try { var d = await API.get('/counselors/list'); counselors.value = d.data || []; }
          catch (e) { console.warn("辅导员列表加载失败:", e); }
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
        students, studentsLoading, studentSearch, showAddStudent, newStudent, selectedStudent, studentProfiles,
        studentRiskTimeline, studentRiskTimelineLoading, showStudentRiskTimeline, manualRiskLevel, manualRiskReason,
        loadStudents, addStudent, viewStudent, updateStudentNotes, searchStudentsHandler,
        loadStudentRiskTimeline, toggleStudentRiskTimeline, adjustStudentRisk,
        // 预警
        alerts, alertsLoading, alertStatusFilter, crisisOnly, alertStatusCounts, filteredAlerts,
        loadAlerts, toggleCrisisOnly, ackAlert, escalateAlert, resolvingAlert, resolveNote, resolveSubmitting,
        openResolveAlert, closeResolveAlert, submitResolveAlert,
        crisisCounselors, assigningCrisisAlert, crisisAssignTo, crisisAssignSubmitting,
        openAssignCrisisAlert, closeAssignCrisisAlert, submitAssignCrisisAlert, closeCrisisAlert,
        // 提醒
        reminders, showCompleted, loadReminders, completeReminder,
        // 班会/公文
        meetingTheme, meetingResult, meetingLoading, generateMeeting,
        docType, docContent, docResult, docLoading, generateDoc,
        // 知识库
        kbStats, kbDocs, kbLoading, kbDeleting, loadKbStats, loadKnowledge, uploadDoc, deleteKbDoc,
        // 情绪看板
        emoDashStats, emoDashAlerts, realtimeEmotionLogs, emoBoardLoading,
        emoPieChart, emoRiskChart, emoTrendChart, emoHeatmapChart,
        loadEmotionDashboard, seedRealtimeDemoData,
        // 情绪网络图
        networkGraph, networkFilter, networkCanvas, networkLoading, loadEmotionNetwork, toggleNetworkFilter,
        networkFollowUp, networkVisibleCount, networkSearch, networkHover, networkTipStyle,
        networkClusterMode, networkClusterBy,
        setNetworkFollowUp, setNetworkClusterMode, setNetworkClusterBy,
        onNetworkSearchInput, locateNetworkStudent, networkZoom,
        // AI 数字人
        dhSettings, dhLogs, dhPreviewMsgs, dhPreviewInput, dhPreviewLoading, dhQuickQs, dhVoiceEnabled,
        loadDigitalHuman, saveDigitalHuman, loadDigitalHumanLogs, markDigitalHumanLogHandled,
        askDigitalHuman, contactPresence, speakDigitalHuman, stopDigitalHumanSpeech,
        // 通讯
        messageContacts, teacherSelected, teacherChatMsgs, teacherNewMsg, teacherUnreadCount, teacherMsgRef,
        studentSearchQuery, studentSearchResults, searchStudentsHandler, inviteStudent,
        selectTeacherContact, sendTeacherMsg, guidanceResult, guidanceLoading, analyzeCounselorGuidance,
        fillTeacherMsg, guidanceRiskTagStyle, talkReport, talkReportLoading, generateTalkReport, printTalkReport,
        selectedContact, chatMessages, newMessage, studentUnreadCount, studentMsgRef,
        assistantTyping, loadMessageContacts, selectContactHandler, sendStudentMsg, loadUnreadCount,
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
        appointments, counselors, newAppointment, appointmentFilter, appointmentNotes, updatingAppointmentId,
        loadAppointments, setAppointmentFilter, createAppointment, updateAppointmentStatus,
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
        studentTrendChart, studentTrendLoading, studentTrendSummary, loadStudentTrend,
        // 工具
        Icons, Helpers,
        exportData, reSeedData
      };
    }
  }).mount('#app');
})();
