(function() {
  window.VideoCallModule = {
    setup: function(ctx) {
      const { ref, reactive, computed, nextTick } = Vue;
      const API = ctx.API;
      const Toast = ctx.Toast;
      const currentUser = ctx.currentUser;
      const page = ctx.page;
      const messageContacts = ctx.messageContacts;
      const selectedContact = ctx.selectedContact;
      const teacherSelected = ctx.teacherSelected;
      const loadMessageContacts = ctx.loadMessageContacts;
      const selectContactHandler = ctx.selectContactHandler;
      const selectTeacherContact = ctx.selectTeacherContact;
      const loadWorkplan = ctx.loadWorkplan;
      const loadEmotionNetwork = ctx.loadEmotionNetwork;
      let socket = null;
      function setSocket(value) { socket = value; }

      // ==================== WebRTC 视频通话 ====================
      const localVideo = ref(null), remoteVideo = ref(null);
      const isInCall = ref(false), isVideoEnabled = ref(true), isAudioEnabled = ref(true);
      const incomingStudentCall = ref(null);
      const teacherLocalVideo = ref(null), teacherRemoteVideo = ref(null);
      const teacherInCall = ref(false), teacherVideoEnabled = ref(true), teacherAudioEnabled = ref(true);
      const incomingCall = ref(null);
      let agoraClient = null, localVideoTrack = null, localAudioTrack = null;
      let agoraTeacherClient = null, teacherVideoTrack = null, teacherAudioTrack = null;
      let agoraConfig = null;
      let remoteMediaStream = null;
      const callRoom = ref('');
      const videoRoom = ref('teacher_room');
      // 控制台临时 Token 绑定固定频道，因此呼叫通道不能再用时间戳动态生成
      const AGORA_CHANNEL = 'video_check';
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

      function combineTrackStreams(trackList) {
        var tracks = [];
        (trackList || []).forEach(function(track) {
          if (!track) return;
          var stream = track.getMediaStream ? track.getMediaStream() : null;
          var mediaTracks = (stream && stream.getTracks) ? stream.getTracks() : [];
          if (!mediaTracks.length && track.getMediaStreamTrack) {
            var direct = track.getMediaStreamTrack();
            if (direct) mediaTracks.push(direct);
          }
          mediaTracks.forEach(function(t) {
            if (!tracks.some(function(e) { return e.id === t.id; })) tracks.push(t);
          });
        });
        return new MediaStream(tracks);
      }

      function getRemoteMediaStream(user) {
        if (!remoteMediaStream) remoteMediaStream = new MediaStream();
        [user.videoTrack, user.audioTrack].forEach(function(track) {
          if (!track || !track.getMediaStreamTrack) return;
          var t = track.getMediaStreamTrack();
          if (t && !remoteMediaStream.getTracks().some(function(e) { return e.id === t.id; })) {
            remoteMediaStream.addTrack(t);
          }
        });
        return remoteMediaStream;
      }

      function getLocalMediaStream() {
        return combineTrackStreams([localVideoTrack, localAudioTrack]);
      }

      function getAgoraUid(role) {
        if (role === 'teacher') {
          return 'teacher_' + (currentUser.user_id || currentUser.id || 'counselor');
        }
        return String(currentUser.student_id || currentUser.user_id || currentUser.id || 'student');
      }

      async function ensureAgoraReady() {
        if (!window.AgoraRTC && window._loadAgoraRTC) {
          await new Promise(function(resolve) { window._loadAgoraRTC(resolve); });
        }
        if (!window.AgoraRTC) {
          Toast.error('\u58f0\u7f51 SDK \u672a\u52a0\u8f7d');
          return null;
        }
        if (!agoraConfig) {
          try {
            var info = await fetch('/system/info');
            var data = await info.json();
            var cfg = (data && data.video && data.video.agora) || {};
            agoraConfig = { appId: cfg.app_id || cfg.appId || '' };
          } catch (e) {
            agoraConfig = null;
          }
        }
        if (!agoraConfig || !agoraConfig.appId) {
          Toast.error('\u58f0\u7f51 App ID \u672a\u914d\u7f6e');
          return null;
        }
        return agoraConfig;
      }

      async function fetchAgoraToken(channel, uid) {
        try {
          var resp = await fetch('/api/video/agora-token?channel=' + encodeURIComponent(channel) + '&uid=' + encodeURIComponent(uid));
          var data = await resp.json();
          return data && data.token ? data.token : null;
        } catch (e) {
          return null;
        }
      }

      // ===== 学生端 WebRTC =====
      function initStudentVideo() {
        if (!socket || studentVideoListenersSet) return; studentVideoListenersSet = true;
        socket.on('video_call_accepted', function(data) {
          if (data.caller !== 'student') return;
          callRoom.value = data.room;
          socket.emit('join', { room: data.room });
        });
        socket.on('incoming_video_call', function(data) {
          if (data.caller !== 'teacher' || String(data.student_id || '') !== String(currentUser.student_id || '')) return;
          incomingStudentCall.value = data;
          Toast.info((data.teacher_name || '\u8001\u5e08') + ' \u9080\u8bf7\u4f60\u89c6\u9891\u901a\u8bdd');
        });
        socket.on('video_call_ended', function(data) { if (!data || data.sender !== 'student') endVideoCall(true); });
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

      function agoraJoinErrorMessage(err) {
        var msg = String((err && (err.message || err)) || '');
        if (msg.indexOf('dynamic use static key') !== -1 || msg.indexOf('CAN_NOT_GET_GATEWAY_SERVER') !== -1) {
          return '\u58f0\u7f51\u9274\u6743\u672a\u914d\u7f6e\uff1a\u8bf7\u5230\u58f0\u7f51\u63a7\u5236\u53f0\u5173\u95ed\u8be5\u9879\u76ee\u7684 App \u8bc1\u4e66\u9274\u6743\uff1b\u6216\u628a App \u8bc1\u4e66/\u4e34\u65f6 Token \u586b\u5165 .env \u7684 AGORA_APP_CERT/AGORA_TOKEN \u540e\u91cd\u542f\u670d\u52a1';
        }
        return '\u65e0\u6cd5\u8bbf\u95ee\u6444\u50cf\u5934\uff1a' + msg;
      }

      async function startVideoCall(options) {
        options = options || {};
        if (!isMediaSupported()) {
          Toast.error(getMediaUnsupportedMessage()); return false;
        }
        var cfg = await ensureAgoraReady();
        if (!cfg) return false;
        try {
          remoteMediaStream = null;
          var perms = await navigator.permissions.query({ name: 'camera' }).catch(function() { return null; });
          if (perms && perms.state === 'denied') { Toast.error('\u6444\u50cf\u5934\u6743\u9650\u5df2\u88ab\u62d2\u7edd\uff0c\u8bf7\u5728\u6d4f\u89c8\u5668\u8bbe\u7f6e\u4e2d\u5141\u8bb8'); return false; }
          callRoom.value = options.reuseRoom || AGORA_CHANNEL;
          var studentUid = getAgoraUid('student');
          var token = await fetchAgoraToken(callRoom.value, studentUid);
          var created = await Promise.all([AgoraRTC.createCameraVideoTrack(), AgoraRTC.createMicrophoneAudioTrack()]);
          var videoTrack = created[0], audioTrack = created[1];
          var client = AgoraRTC.createClient({ mode: 'rtc', codec: 'vp8' });
          client.on('user-published', async function(user, mediaType) {
            await client.subscribe(user, mediaType);
            if (mediaType === 'video') {
              if (user.videoTrack && user.videoTrack.play) user.videoTrack.play(remoteVideo.value);
              refreshAudioDiag('remote', getRemoteMediaStream(user));
            } else if (mediaType === 'audio') {
              if (user.audioTrack && user.audioTrack.play) user.audioTrack.play();
              refreshAudioDiag('remote', getRemoteMediaStream(user));
            }
          });
          client.on('user-left', function() { if (isInCall.value) endVideoCall(true); });
          agoraClient = client; localVideoTrack = videoTrack; localAudioTrack = audioTrack;
          await client.join(cfg.appId, callRoom.value, token, studentUid);
          await client.publish([videoTrack, audioTrack]);
          refreshAudioDiag('local', getLocalMediaStream());
          isInCall.value = true; isVideoEnabled.value = true; isAudioEnabled.value = true;
          await nextTick();
          if (localVideo.value && localVideoTrack.play) localVideoTrack.play(localVideo.value);
          if (!socket) { Toast.error('\u8fde\u63a5\u672a\u5c31\u7eea\uff0c\u8bf7\u5237\u65b0\u9875\u9762'); endVideoCall(true); return false; }
          initStudentVideo();
          socket.emit('join', { room: callRoom.value });
          if (!options.skipRequest) socket.emit('video_call_request', { caller: 'student', student_id: currentUser.student_id, student_name: currentUser.name, room: callRoom.value, counselor_id: (selectedContact.value && selectedContact.value.id) || null });
          return true;
        } catch (err) {
          if (agoraClient) { agoraClient.leave().catch(function() {}); agoraClient = null; }
          if (localVideoTrack) { localVideoTrack.close(); localVideoTrack = null; }
          if (localAudioTrack) { localAudioTrack.close(); localAudioTrack = null; }
          if (localVideo.value) localVideo.value.srcObject = null;
          remoteMediaStream = null;
          isInCall.value = false;
          if (err.name === 'NotAllowedError') Toast.error('\u6444\u50cf\u5934\u6216\u9ea6\u514b\u98ce\u6743\u9650\u88ab\u62d2\u7edd');
          else if (err.name === 'NotFoundError') Toast.error('\u672a\u68c0\u6d4b\u5230\u6444\u50cf\u5934\u6216\u9ea6\u514b\u98ce\u8bbe\u5907');
          else Toast.error(agoraJoinErrorMessage(err));
          return false;
        }
      }

      function endVideoCall(silent) {
        stopAllRealtime();
        if (agoraClient) { agoraClient.leave().catch(function() {}); agoraClient = null; }
        if (localVideoTrack) { localVideoTrack.close(); localVideoTrack = null; }
        if (localAudioTrack) { localAudioTrack.close(); localAudioTrack = null; }
        if (localVideo.value) localVideo.value.srcObject = null;
        if (remoteVideo.value) remoteVideo.value.srcObject = null;
        remoteMediaStream = null;
        resetAudioDiag();
        isInCall.value = false;
        if (!silent && socket) socket.emit('video_call_end', { room: callRoom.value, sender: 'student' });
      }

      function toggleVideo() {
        if (!localVideoTrack) return;
        var next = !isVideoEnabled.value;
        localVideoTrack.setEnabled(next);
        isVideoEnabled.value = next;
      }
      function toggleAudio() {
        if (!localAudioTrack) return;
        var next = !isAudioEnabled.value;
        localAudioTrack.setEnabled(next);
        isAudioEnabled.value = next;
        refreshAudioDiag('local', getLocalMediaStream());
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
        callRoom.value = incomingStudentCall.value.room || AGORA_CHANNEL;
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
        });
        socket.on('video_call_ended', function(data) { if (!data || data.sender !== 'teacher') endTeacherVideo(true); });
      }

      async function startTeacherVideo(options) {
        options = options || {};
        if (!isMediaSupported()) {
          Toast.error(getMediaUnsupportedMessage()); return false;
        }
        var cfg = await ensureAgoraReady();
        if (!cfg) return false;
        try {
          remoteMediaStream = null;
          videoRoom.value = options.reuseRoom || AGORA_CHANNEL;
          var teacherUid = getAgoraUid('teacher');
          var token = await fetchAgoraToken(videoRoom.value, teacherUid);
          var created = await Promise.all([AgoraRTC.createCameraVideoTrack(), AgoraRTC.createMicrophoneAudioTrack()]);
          var videoTrack = created[0], audioTrack = created[1];
          var client = AgoraRTC.createClient({ mode: 'rtc', codec: 'vp8' });
          client.on('user-published', async function(user, mediaType) {
            await client.subscribe(user, mediaType);
            if (mediaType === 'video') {
              var remoteStream = getRemoteMediaStream(user);
              if (user.videoTrack && user.videoTrack.play) user.videoTrack.play(teacherRemoteVideo.value);
              refreshAudioDiag('remote', remoteStream);
              autoStartRealtimeEmotion(remoteStream, teacherRemoteVideo.value);
            } else if (mediaType === 'audio') {
              if (user.audioTrack && user.audioTrack.play) user.audioTrack.play();
              var stream = getRemoteMediaStream(user);
              refreshAudioDiag('remote', stream);
              if (yoloActive.value) startRealtimeEmotion(stream);
            }
          });
          client.on('user-left', function() { if (teacherInCall.value) endTeacherVideo(true); });
          agoraTeacherClient = client; teacherVideoTrack = videoTrack; teacherAudioTrack = audioTrack;
          await client.join(cfg.appId, videoRoom.value, token, teacherUid);
          await client.publish([videoTrack, audioTrack]);
          refreshAudioDiag('local', combineTrackStreams([teacherVideoTrack, teacherAudioTrack]));
          teacherInCall.value = true; teacherVideoEnabled.value = true; teacherAudioEnabled.value = true;
          await nextTick();
          if (teacherLocalVideo.value && teacherVideoTrack.play) teacherVideoTrack.play(teacherLocalVideo.value);
          if (socket) { socket.emit('join', { room: videoRoom.value }); }
          return true;
        } catch (err) {
          if (agoraTeacherClient) { agoraTeacherClient.leave().catch(function() {}); agoraTeacherClient = null; }
          if (teacherVideoTrack) { teacherVideoTrack.close(); teacherVideoTrack = null; }
          if (teacherAudioTrack) { teacherAudioTrack.close(); teacherAudioTrack = null; }
          if (teacherLocalVideo.value) teacherLocalVideo.value.srcObject = null;
          remoteMediaStream = null;
          teacherInCall.value = false;
          if (err.name === 'NotAllowedError') Toast.error('\u6444\u50cf\u5934\u6216\u9ea6\u514b\u98ce\u6743\u9650\u88ab\u62d2\u7edd');
          else if (err.name === 'NotFoundError') Toast.error('\u672a\u68c0\u6d4b\u5230\u6444\u50cf\u5934\u6216\u9ea6\u514b\u98ce\u8bbe\u5907');
          else Toast.error(agoraJoinErrorMessage(err));
          return false;
        }
      }

      async function acceptVideoCall() {
        if (incomingCall.value) await ensureTeacherCallContact(incomingCall.value);
        if (incomingCall.value) videoRoom.value = incomingCall.value.room || AGORA_CHANNEL;
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
        if (agoraTeacherClient) { agoraTeacherClient.leave().catch(function() {}); agoraTeacherClient = null; }
        if (teacherVideoTrack) { teacherVideoTrack.close(); teacherVideoTrack = null; }
        if (teacherAudioTrack) { teacherAudioTrack.close(); teacherAudioTrack = null; }
        if (teacherLocalVideo.value) teacherLocalVideo.value.srcObject = null;
        if (teacherRemoteVideo.value) teacherRemoteVideo.value.srcObject = null;
        remoteMediaStream = null;
        resetAudioDiag();
        teacherInCall.value = false;
        if (!silent && socket) socket.emit('video_call_end', { room: videoRoom.value, sender: 'teacher' });
      }

      function toggleTeacherVideo() {
        if (!teacherVideoTrack) return;
        var next = !teacherVideoEnabled.value;
        teacherVideoTrack.setEnabled(next);
        teacherVideoEnabled.value = next;
      }
      function toggleTeacherAudio() {
        if (!teacherAudioTrack) return;
        var next = !teacherAudioEnabled.value;
        teacherAudioTrack.setEnabled(next);
        teacherAudioEnabled.value = next;
        refreshAudioDiag('local', combineTrackStreams([teacherVideoTrack, teacherAudioTrack]));
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
        autoStartRealtimeEmotion(remoteMediaStream || videoEl.srcObject, videoEl);
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


      return {
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
        initStudentVideo, stopAllRealtime, setSocket
      };
    }
  };
})();
