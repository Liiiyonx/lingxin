/**
 * 聆心 v3.1 — 主应用入口
 * 依赖: Vue 3 CDN, ECharts, Socket.IO, marked, face-api.js
 * 工具模块: API, Toast, Icons, Helpers (全局)
 * 实时模块: FaceEmotionDetector, VoiceProsodyAnalyzer, EmotionFusionEngine (全局)
 */
(function() {
  const { createApp, ref, reactive, computed, onMounted, nextTick, watch } = Vue;

  const app = createApp({
    components: {
      'dh-face': {
        props: {
          mood: { type: String, default: 'neutral' },
          size: { type: String, default: 'sm' }
        },
        template: `
          <div class="dh-face" :class="'dh-face--' + size + ' dh-mood--' + mood">
            <svg viewBox="0 0 100 100" class="dh-face-svg" aria-hidden="true">
              <rect x="2" y="2" width="96" height="96" rx="28" class="dh-face-base"></rect>
              <circle cx="50" cy="43" r="27" class="dh-face-skin"></circle>
              <g class="dh-brows">
                <path v-if="mood === 'concerned' || mood === 'sad'" d="M28 30 Q36 24 44 30 M56 30 Q64 24 72 30" class="dh-feature-line"></path>
                <path v-else d="M29 28 Q37 31 44 28 M56 28 Q63 31 71 28" class="dh-feature-line"></path>
              </g>
              <g class="dh-eyes">
                <ellipse cx="37" cy="45" rx="5" ry="7" class="dh-eye"></ellipse>
                <ellipse cx="63" cy="45" rx="5" ry="7" class="dh-eye"></ellipse>
                <circle cx="39" cy="44" r="1.6" class="dh-eye-light"></circle>
                <circle cx="65" cy="44" r="1.6" class="dh-eye-light"></circle>
              </g>
              <g class="dh-mouth">
                <path v-if="mood === 'happy'" d="M34 56 Q50 70 66 56" class="dh-mouth-shape"></path>
                <path v-else-if="mood === 'concerned' || mood === 'sad'" d="M36 62 Q50 52 64 62" class="dh-mouth-shape"></path>
                <ellipse v-else-if="mood === 'speaking'" cx="50" cy="59" rx="10" ry="7" class="dh-mouth-shape dh-mouth-speaking"></ellipse>
                <line v-else x1="42" y1="59" x2="58" y2="59" class="dh-mouth-line"></line>
              </g>
              <g class="dh-blush">
                <ellipse v-if="mood === 'happy' || mood === 'speaking'" cx="29" cy="54" rx="5" ry="3" class="dh-blush-shape"></ellipse>
                <ellipse v-if="mood === 'happy' || mood === 'speaking'" cx="71" cy="54" rx="5" ry="3" class="dh-blush-shape"></ellipse>
              </g>
            </svg>
            <span v-if="mood === 'thinking'" class="dh-face-thinking"><i></i><i></i><i></i></span>
          </div>
        `
      }
    },
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
        } catch (e) { if (e.message !== 'unauthorized') Toast.error(e.message || '登录失败，请稍后重试'); }
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
        } catch (e) { if (e.message !== 'unauthorized') Toast.error(e.message || '登录失败，请稍后重试'); }
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
        try { API.logout(); } catch (e) {}
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
      const studentPage = ref(1);
      const studentPageSize = ref(20);
      const studentTotal = ref(0);
      const showAddStudent = ref(false);
      const newStudent = reactive({ student_id: '', name: '', gender: '', college: '', class_name: '', phone: '', notes: '' });
      const selectedStudent = ref(null);
      const studentProfiles = ref([]);
      const studentRiskTimeline = ref([]);
      const studentRiskTimelineLoading = ref(false);
      const showStudentRiskTimeline = ref(false);
      const manualRiskLevel = ref('low');
      const manualRiskReason = ref('');

      const studentTotalPages = computed(function() {
        return Math.max(1, Math.ceil((studentTotal.value || 0) / (studentPageSize.value || 20)));
      });

      async function fetchStudents(pageNum) {
        pageNum = Math.max(1, Number(pageNum) || 1);
        studentsLoading.value = true;
        try {
          var d = await API.get('/student/list', {
            search: studentSearch.value,
            page: pageNum,
            per_page: studentPageSize.value
          });
          students.value = d.data || [];
          studentTotal.value = Number(d.total || (d.data || []).length || 0);
          studentPage.value = pageNum;
        } catch (e) {
          console.warn('学生列表加载失败', e);
          Toast.error('学生列表加载失败');
        } finally {
          studentsLoading.value = false;
        }
      }

      const studentListSearch = Helpers.debounce(async function() {
        studentPage.value = 1;
        await fetchStudents(1);
      }, 250);

      async function loadStudents(resetPage) {
        await fetchStudents(resetPage ? 1 : studentPage.value);
      }

      function prevStudentsPage() {
        if (studentPage.value <= 1) return;
        fetchStudents(studentPage.value - 1);
      }

      function nextStudentsPage() {
        if (studentPage.value >= studentTotalPages.value) return;
        fetchStudents(studentPage.value + 1);
      }

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
      const alertsModule = window.AlertsModule.setup({ API, Toast, currentUser });
      const {
        alerts, alertsLoading, alertStatusFilter, crisisOnly, alertStatusCounts, filteredAlerts,
        loadAlerts, toggleCrisisOnly, ackAlert, escalateAlert, resolvingAlert, resolveNote, resolveSubmitting,
        openResolveAlert, closeResolveAlert, submitResolveAlert,
        crisisCounselors, assigningCrisisAlert, crisisAssignTo, crisisAssignSubmitting,
        openAssignCrisisAlert, closeAssignCrisisAlert, submitAssignCrisisAlert, closeCrisisAlert
      } = alertsModule;

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
      const emoDashStats = reactive({ total: 0, studentCount: 0, highRisk: 0, mediumRisk: 0, avgIntensity: 0 });
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
            emoDashStats.studentCount = s.data.student_count || 0;
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
        videoModule.setSocket(socket);
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
        loadUnreadCount();
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
        try {
          var d = await API.get('/messages/unread');
          var c = d.data ? d.data.unread_count : 0;
          if (currentUser.role === 'student') studentUnreadCount.value = c;
          else teacherUnreadCount.value = c;
        }
        catch (e) { console.warn('未读消息数加载失败', e); }
      }

      function insertEmoji(e) { newMessage.value += e; showEmoji.value = false; }
      function insertTeacherEmoji(e) { teacherNewMsg.value += e; teacherShowEmoji.value = false; }

      // ==================== AI 数字人 ====================
      const dh = window.DigitalHumanModule.setup({ API, Toast, currentUser });

      // ==================== WebRTC 视频通话 ====================
      const videoModule = window.VideoCallModule.setup({
        API, Toast, currentUser, page, messageContacts, selectedContact, teacherSelected,
        loadMessageContacts, selectContactHandler, selectTeacherContact, loadWorkplan, loadEmotionNetwork
      });
      const {
        audioDiag, visionDiag,
        localVideo, remoteVideo, isInCall, isVideoEnabled, isAudioEnabled,
        startVideoCall, endVideoCall, toggleVideo, toggleAudio,
        incomingStudentCall, acceptStudentCall, rejectStudentCall,
        teacherLocalVideo, teacherRemoteVideo, teacherInCall, teacherVideoEnabled, teacherAudioEnabled,
        incomingCall, initTeacherVideo, startTeacherVideo, endTeacherVideo,
        toggleTeacherVideo, toggleTeacherAudio, acceptVideoCall, rejectVideoCall,
        openTeacherVideo,
        yoloActive, currentYoloEmotion, yoloAlerts, yoloCanvas,
        toggleYolo, startYolo, stopYolo, loadYoloLogs,
        yoloEmotionShow, yoloEmotionDisplay, realtimeCallSummary,
        initStudentVideo, stopAllRealtime
      } = videoModule;

      // ==================== 预约 ====================
      const appointmentMod = window.AppointmentsModule.setup({ API, Toast, loadReminders });

      // ==================== 心理测评 ====================
      const assessmentMod = window.AssessmentModule.setup({ API, Toast, currentUser, page, loadMessageContacts });

      const {
        dhSettings, dhLogs, dhPreviewMsgs, dhPreviewInput, dhPreviewLoading,
        dhQuickQs, dhVoiceEnabled, dhAvatarMood, dhSpeakingMessageId,
        dhPreviewSpeakingIndex, dhSummary, contactPresence,
        loadDigitalHuman, saveDigitalHuman, loadDigitalHumanLogs, markDigitalHumanLogHandled,
        askDigitalHuman, speakDigitalHuman, stopDigitalHumanSpeech,
        crisisLevelLabel, crisisLevelClass, logFaceMood,
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
      const studentHomeModule = window.StudentHomeModule.setup({
        API, Toast, Helpers, currentUser, isDarkMode, ensureChart
      });
      const {
        waterCount, waterProgress, addWater, resetWater, loadWater,
        dailyQuote, dailyWord, todayMood, todayMoodText,
        loadMood, recordMood, todayStr, greetingText,
        studentTrendChart, studentTrendLoading, studentTrendSummary, loadStudentTrend,
        emojiList, autoResize
      } = studentHomeModule;

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
        students, studentsLoading, studentSearch, studentPage, studentPageSize, studentTotal, studentTotalPages,
        showAddStudent, newStudent, selectedStudent, studentProfiles,
        studentRiskTimeline, studentRiskTimelineLoading, showStudentRiskTimeline, manualRiskLevel, manualRiskReason,
        loadStudents, studentListSearch, prevStudentsPage, nextStudentsPage,
        addStudent, viewStudent, updateStudentNotes, searchStudentsHandler,
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
        dhAvatarMood, dhSpeakingMessageId, dhPreviewSpeakingIndex, dhSummary,
        loadDigitalHuman, saveDigitalHuman, loadDigitalHumanLogs, markDigitalHumanLogHandled,
        askDigitalHuman, contactPresence, speakDigitalHuman, stopDigitalHumanSpeech,
        crisisLevelLabel, crisisLevelClass, logFaceMood,
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
  });
  app.mount('#app');
})();
