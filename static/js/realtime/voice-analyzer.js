/**
 * Lingxin realtime voice prosody analyzer (Web Audio API).
 * Extracts volume, pitch, estimated speech rate and pause ratio.
 * 新增：连续 PCM 音频采集，供上传后端 emotion2vec 做高精度语音情绪识别。
 */
window.VoiceProsodyAnalyzer = (function() {
  function create(stream) {
    let audioCtx = null;
    let analyser = null;
    let source = null;
    let running = false;

    // 连续 PCM 采集（用于后端 emotion2vec 真模型）
    let pcmNode = null;
    let pcmSilentGain = null;
    let pcmChunks = [];
    let pcmSampleCount = 0;

    const state = {
      volume: 0,
      pitch: 0,
      speechRate: 0,
      pauseRatio: 0,
      isSpeaking: false,
      analyzerReady: false,
      contextState: '--',
      sampleRate: 0,
      energyHistory: [],
      pitchHistory: [],
      emotionHint: '正常',
      // 后端真模型情绪结果（由 app.js 回填）
      modelEmotion: null
    };

    function start() {
      if (running) return;
      try {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 2048;
        analyser.smoothingTimeConstant = 0.65;
        source = audioCtx.createMediaStreamSource(stream);
        source.connect(analyser);
        running = true;
        state.analyzerReady = true;
        state.contextState = audioCtx.state;
        state.sampleRate = audioCtx.sampleRate;
        resumeContext();
        startPcmCapture();
        console.log('Voice analyzer started');
      } catch (e) {
        state.analyzerReady = false;
        state.contextState = audioCtx ? audioCtx.state : 'failed';
        console.error('Voice analyzer failed:', e);
      }
    }

    // 连续采集 PCM（ScriptProcessorNode），供后端 emotion2vec 使用
    function startPcmCapture() {
      try {
        pcmNode = audioCtx.createScriptProcessor(4096, 1, 1);
        pcmNode.onaudioprocess = function(e) {
          const input = e.inputBuffer.getChannelData(0);
          const copy = new Float32Array(input.length);
          copy.set(input);
          pcmChunks.push(copy);
          pcmSampleCount += copy.length;
        };
        // 静音节点：让 ScriptProcessor 持续处理，但不重复输出到扬声器
        pcmSilentGain = audioCtx.createGain();
        pcmSilentGain.gain.value = 0;
        source.connect(pcmNode);
        pcmNode.connect(pcmSilentGain);
        pcmSilentGain.connect(audioCtx.destination);
      } catch (e) {
        console.warn('PCM capture failed:', e);
      }
    }

    // 取出并清空已累积的 PCM 音频（返回 Float32Array + 采样率）
    function getAudioChunk() {
      if (pcmSampleCount === 0) return null;
      const flat = new Float32Array(pcmSampleCount);
      let offset = 0;
      for (let i = 0; i < pcmChunks.length; i++) {
        flat.set(pcmChunks[i], offset);
        offset += pcmChunks[i].length;
      }
      pcmChunks = [];
      pcmSampleCount = 0;
      return { pcm: flat, sampleRate: audioCtx ? audioCtx.sampleRate : 44100 };
    }

    function resumeContext() {
      if (audioCtx && audioCtx.state === 'suspended' && audioCtx.resume) {
        audioCtx.resume().then(function() {
          state.contextState = audioCtx.state;
        }).catch(function() {});
      }
    }

    function stop() {
      running = false;
      state.analyzerReady = false;
      state.contextState = audioCtx ? audioCtx.state : '--';
      if (pcmNode) { try { pcmNode.disconnect(); } catch (e) {} pcmNode = null; }
      if (pcmSilentGain) { try { pcmSilentGain.disconnect(); } catch (e) {} pcmSilentGain = null; }
      pcmChunks = [];
      pcmSampleCount = 0;
      if (source) { source.disconnect(); source = null; }
      if (audioCtx && audioCtx.state !== 'closed') { audioCtx.close().catch(function(){}); }
      audioCtx = null;
      analyser = null;
    }

    function analyze() {
      state.contextState = audioCtx ? audioCtx.state : '--';
      state.analyzerReady = !!(running && analyser);
      resumeContext();
      if (!running || !analyser) return state;

      const bufferLength = analyser.fftSize;
      const timeData = new Float32Array(bufferLength);
      analyser.getFloatTimeDomainData(timeData);

      let sumSquares = 0;
      let peak = 0;
      for (let i = 0; i < bufferLength; i++) {
        const v = timeData[i];
        sumSquares += v * v;
        peak = Math.max(peak, Math.abs(v));
      }
      state.volume = Math.min(1, Math.max(Math.sqrt(sumSquares / bufferLength) * 6, peak * 0.8));

      const sampleRate = audioCtx ? audioCtx.sampleRate : 48000;
      state.sampleRate = sampleRate;
      const minSamples = Math.floor(sampleRate / 400);
      const maxSamples = Math.floor(sampleRate / 80);
      let bestCorr = -1, bestLag = -1;
      for (let lag = minSamples; lag < Math.min(maxSamples, bufferLength / 2); lag++) {
        let corr = 0;
        for (let i = 0; i < bufferLength - lag; i++) {
          corr += timeData[i] * timeData[i + lag];
        }
        if (corr > bestCorr) { bestCorr = corr; bestLag = lag; }
      }
      const estimatedPitch = bestLag > 0 ? Math.round(sampleRate / bestLag) : 0;
      state.pitch = state.volume > 0.015 ? estimatedPitch : 0;

      let zcr = 0;
      for (let i = 1; i < bufferLength; i++) {
        if (timeData[i] * timeData[i - 1] < 0) zcr++;
      }
      const zcrNorm = zcr / bufferLength;
      state.energyHistory.push(state.volume);
      if (state.energyHistory.length > 30) state.energyHistory.shift();
      const recent = state.energyHistory.slice(-8);
      let energyDelta = 0;
      for (let i = 1; i < recent.length; i++) energyDelta += Math.abs(recent[i] - recent[i - 1]);
      state.speechRate = state.volume > 0.015 ? Math.min(1, zcrNorm * 14 + energyDelta * 1.8) : 0;

      state.isSpeaking = state.volume > 0.018;
      const silenceCount = state.energyHistory.filter(function(v) { return v < 0.015; }).length;
      state.pauseRatio = state.energyHistory.length ? silenceCount / state.energyHistory.length : 1;

      // 启发式情绪仅作「实时占位」，最终以后端 emotion2vec 真模型结果为准
      let emotionHint = '正常';
      if (state.modelEmotion) {
        emotionHint = state.modelEmotion.emotion || state.modelEmotion.text || '正常';
      } else if (state.isSpeaking) {
        if (state.pitch > 250 && state.speechRate > 0.5) emotionHint = '紧张';
        else if (state.pitch < 100 && state.speechRate < 0.2) emotionHint = '低落';
        else if (state.volume > 0.6 && state.speechRate > 0.4) emotionHint = '愤怒';
        else if (state.pauseRatio > 0.4) emotionHint = '焦虑';
        else if (state.pitch > 200 && state.volume > 0.4) emotionHint = '高兴';
      } else if (state.pauseRatio > 0.7) {
        emotionHint = '低落';
      }
      state.emotionHint = emotionHint;
      state.contextState = audioCtx ? audioCtx.state : '--';

      return state;
    }

    return { start, stop, analyze, getAudioChunk: getAudioChunk, getState: function() { return state; } };
  }

  return { create: create };
})();
