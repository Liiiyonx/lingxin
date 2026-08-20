(function() {
  window.AppointmentsModule = {
    setup: function(ctx) {
      const { ref, reactive } = Vue;
      const appointments = ref([]);
      const counselors = ref([]);
      const newAppointment = reactive({ counselor_id: '', appointment_time: '', reason: '' });
      const appointmentFilter = ref('all');
      const appointmentNotes = reactive({});
      const updatingAppointmentId = ref(null);

      async function loadAppointments() {
        var params = {};
        if (appointmentFilter.value !== 'all') params.status = appointmentFilter.value;
        try { var d = await ctx.API.get('/appointments', params); appointments.value = d.data || []; }
        catch (e) { console.warn('预约列表加载失败', e); }
      }

      function setAppointmentFilter(status) {
        appointmentFilter.value = status;
        loadAppointments();
      }

      async function createAppointment() {
        if (!newAppointment.counselor_id || !newAppointment.appointment_time) { ctx.Toast.error('请选择辅导员和预约时间'); return; }
        try {
          await ctx.API.post('/appointments/create', newAppointment);
          ctx.Toast.success('预约创建成功');
          newAppointment.counselor_id = ''; newAppointment.appointment_time = ''; newAppointment.reason = '';
          loadAppointments();
        } catch (e) { ctx.Toast.error('预约失败'); }
      }

      async function updateAppointmentStatus(id, status) {
        var note = (appointmentNotes[id] || '').trim();
        if (status === 'completed' && !note) { ctx.Toast.warning('请先填写处理备注'); return; }
        if (status === 'cancelled' && !confirm('确认取消这条预约吗？')) return;
        updatingAppointmentId.value = id;
        try {
          var d = await ctx.API.put('/appointments/' + id + '/status', { status: status, notes: note });
          ctx.Toast.success(d.message || '预约状态已更新');
          appointmentNotes[id] = '';
          await loadAppointments();
          if (status === 'confirmed' && ctx.loadReminders) ctx.loadReminders();
        } catch (e) {
          ctx.Toast.error('状态更新失败');
        } finally {
          updatingAppointmentId.value = null;
        }
      }

      async function loadCounselors() {
        try { var d = await ctx.API.get('/counselors/list'); counselors.value = d.data || []; }
        catch (e) { console.warn('辅导员列表加载失败', e); }
      }

      return {
        appointments, counselors, newAppointment, appointmentFilter,
        appointmentNotes, updatingAppointmentId,
        loadAppointments, setAppointmentFilter, createAppointment,
        updateAppointmentStatus, loadCounselors
      };
    }
  };
})();
