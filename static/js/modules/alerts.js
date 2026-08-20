(function() {
  window.AlertsModule = {
    setup: function(ctx) {
      const { ref, reactive, computed } = Vue;
      const API = ctx.API;
      const Toast = ctx.Toast;
      const currentUser = ctx.currentUser;

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


      return {
        alerts, alertsLoading, alertStatusFilter, crisisOnly, alertStatusCounts, filteredAlerts,
        loadAlerts, toggleCrisisOnly, ackAlert, escalateAlert, resolvingAlert, resolveNote, resolveSubmitting,
        openResolveAlert, closeResolveAlert, submitResolveAlert,
        crisisCounselors, assigningCrisisAlert, crisisAssignTo, crisisAssignSubmitting,
        openAssignCrisisAlert, closeAssignCrisisAlert, submitAssignCrisisAlert, closeCrisisAlert
      };
    }
  };
})();
