/**
 * 聆心 — 多模态情绪融合引擎
 * 融合面部表情识别 + 语音韵律分析 → 综合情绪评估
 */
window.EmotionFusionEngine = (function() {
  // 12种聆心情绪标签
  const EMOTIONS = ['正常','平静','高兴','低落','焦虑','烦躁','压抑','愤怒','恐惧','惊讶','厌恶','悲伤','紧张'];

  // 情绪强度权重
  const SEVERITY = { 正常:0,高兴:0,惊讶:1,低落:4,烦躁:5,紧张:5,焦虑:7,悲伤:7,愤怒:8,压抑:8,恐惧:9,厌恶:6 };
  const HIGH_RISK = ['焦虑','压抑','恐惧','愤怒','悲伤'];

  // 面部表情 → 聆心情绪的映射权重
  const FACE_TO_EMOTION = {
    happy:       { 高兴:0.9, 正常:0.1 },
    sad:         { 悲伤:0.7, 低落:0.3 },
    angry:       { 愤怒:0.8, 烦躁:0.2 },
    fearful:     { 恐惧:0.7, 焦虑:0.3 },
    disgusted:   { 厌恶:0.7, 烦躁:0.2, 愤怒:0.1 },
    surprised:   { 惊讶:0.7, 紧张:0.2, 恐惧:0.1 },
    neutral:     { 正常:0.8, 低落:0.1, 平静:0.1 }
  };

  function fuse(faceResult, voiceState, history) {
    history = history || [];
    const now = Date.now();

    // === 1. 面部情绪得分 ===
    const faceScores = {};
    EMOTIONS.forEach(function(e) { faceScores[e] = 0; });

    if (faceResult && faceResult.expressions) {
      Object.entries(faceResult.expressions).forEach(function(entry) {
        var expr = entry[0], score = entry[1];
        var mapping = FACE_TO_EMOTION[expr];
        if (mapping) {
          Object.entries(mapping).forEach(function(m) {
            faceScores[m[0]] = (faceScores[m[0]] || 0) + score * m[1];
          });
        }
      });
    }

    // ===== FACS 面部动作单元 → 情绪映射（7 类基础表情）=====
    var microRaw = (faceResult && faceResult.micro) ? faceResult.micro : {};

    // 快乐（真笑）：嘴角上扬 + 眼轮匝肌收缩（眼睛微眯，杜彻尼微笑）
    if (microRaw.mouthCornerUp > 0.25) {
      var smile = microRaw.mouthCornerUp * 0.7 + (microRaw.eyeSquint > 0.2 ? 0.3 : 0);
      faceScores['高兴'] = Math.max(faceScores['高兴'] || 0, smile);
    }

    // 悲伤：眉毛内角上扬（倒八字）+ 嘴角下拉
    if (microRaw.mouthCornerDrop > 0.30 || microRaw.innerBrowRaise > 0.30) {
      var sad = Math.max(microRaw.mouthCornerDrop * 0.6, microRaw.innerBrowRaise * 0.5);
      faceScores['悲伤'] = Math.max(faceScores['悲伤'] || 0, sad);
      faceScores['低落'] = Math.max(faceScores['低落'] || 0, sad * 0.5);
    }

    // 愤怒：眉毛下压紧锁 + 嘴唇紧抿 / 眼睛瞪大
    if (microRaw.browFurrow > 0.22) {
      var angry = microRaw.browFurrow * 0.7 + (microRaw.lipTight > 0.3 ? 0.2 : 0);
      faceScores['愤怒'] = Math.max(faceScores['愤怒'] || 0, angry);
      faceScores['烦躁'] = Math.max(faceScores['烦躁'] || 0, microRaw.browFurrow * 0.4);
    }

    // 恐惧：眼睛瞪大 + 眉毛抬起 + 嘴巴张开/收紧
    if (microRaw.eyeOpen > 0.3) {
      var fear = microRaw.eyeOpen * 0.6 + (microRaw.mouthOpen > 0.3 ? 0.2 : 0) + (microRaw.innerBrowRaise > 0.3 ? 0.2 : 0);
      faceScores['恐惧'] = Math.max(faceScores['恐惧'] || 0, fear);
      faceScores['焦虑'] = Math.max(faceScores['焦虑'] || 0, microRaw.eyeOpen * 0.4);
    }

    // 惊讶：眉毛高抬 + 嘴巴自然张开
    if (microRaw.mouthOpen > 0.35) {
      var surprise = microRaw.mouthOpen * 0.6 + (microRaw.innerBrowRaise > 0.3 ? 0.3 : 0);
      faceScores['惊讶'] = Math.max(faceScores['惊讶'] || 0, surprise);
    }

    // 厌恶：眼睛微眯 + 上唇拉高（鼻皱）
    if (microRaw.eyeSquint > 0.4) {
      faceScores['厌恶'] = Math.max(faceScores['厌恶'] || 0, microRaw.eyeSquint * 0.7);
      faceScores['烦躁'] = Math.max(faceScores['烦躁'] || 0, microRaw.eyeSquint * 0.3);
    }

    // 轻蔑：单侧嘴角上扬（不对称，唯一不对称表情）
    if (microRaw.mouthAsymmetry > 0.3) {
      faceScores['厌恶'] = Math.max(faceScores['厌恶'] || 0, microRaw.mouthAsymmetry * 0.6);
      faceScores['烦躁'] = Math.max(faceScores['烦躁'] || 0, microRaw.mouthAsymmetry * 0.3);
    }

    // === 2. 语音情绪得分 ===
    const voiceScores = {};
    EMOTIONS.forEach(function(e) { voiceScores[e] = 0; });

    if (voiceState && voiceState.isSpeaking) {
      const hint = voiceState.emotionHint || '正常';
      voiceScores[hint] = 0.7;
      voiceScores['正常'] = 0.3;

      // 语速异常 → 焦虑/紧张
      if (voiceState.speechRate > 0.45) { voiceScores['紧张'] = Math.max(voiceScores['紧张']||0, 0.5); voiceScores['焦虑'] = Math.max(voiceScores['焦虑']||0, 0.3); }
      // 停顿过多 → 低落/压抑
      if (voiceState.pauseRatio > 0.35) { voiceScores['低落'] = Math.max(voiceScores['低落']||0, 0.4); voiceScores['压抑'] = Math.max(voiceScores['压抑']||0, 0.3); }
      // 高音量 → 愤怒/烦躁
      if (voiceState.volume > 0.5) { voiceScores['烦躁'] = Math.max(voiceScores['烦躁']||0, 0.5); }
    } else if (voiceState && voiceState.pauseRatio > 0.7) {
      voiceScores['低落'] = 0.6;
      voiceScores['正常'] = 0.4;
    } else {
      voiceScores['正常'] = 1.0;
    }

    // === 3. 多模态融合 ===
    const voiceWeight = voiceState && voiceState.isSpeaking ? 0.45 : 0.15;
    const faceWeight = faceResult && faceResult.facesDetected > 0 ? 0.55 : 0.1;
    const historyWeight = history.length > 3 ? 0.15 : 0;
    const totalWeight = faceWeight + voiceWeight + historyWeight || 1;

    const fusedScores = {};
    EMOTIONS.forEach(function(e) {
      fusedScores[e] = (faceScores[e] * faceWeight + voiceScores[e] * voiceWeight) / (faceWeight + voiceWeight || 1);
      // 历史平滑
      if (historyWeight > 0) {
        const histAvg = history.slice(-5).reduce(function(s, h) { return s + (h.scores[e] || 0); }, 0) / Math.min(5, history.length);
        fusedScores[e] = fusedScores[e] * (1 - historyWeight) + histAvg * historyWeight;
      }
    });

    // 找到最高情绪
    const sorted = Object.entries(fusedScores).sort(function(a, b) { return b[1] - a[1]; });
    const primary = sorted[0];
    const secondary = sorted[1];

    // === 4. 微表情/肢体指标 ===
    const micro = faceResult && faceResult.micro ? faceResult.micro : {
      browFurrow: 0, gazeAversion: 0, headDown: 0, postureStiffness: 0, lipTight: 0, shoulderSlope: 0, forwardHead: 0, slouch: 0, scratchHead: 0, touchNose: 0, handNearFace: 0, gazeInstability: 0
    };

    // === 5. 情绪强度 ===
    const primaryEmotion = primary[0];
    const confidence = Math.round(primary[1] * 100);
    let intensity = Math.round(primary[1] * 10);
    if (SEVERITY[primaryEmotion] >= 7) intensity = Math.min(10, intensity + 1);
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
    if (weightedActionSignal > 0.28) intensity = Math.min(10, intensity + 1);
    if (weightedActionSignal > 0.55) intensity = Math.min(10, intensity + 1);
    if ((micro.browFurrow || 0) > 0.50 && (micro.gazeInstability || 0) > 0.25) intensity = Math.min(10, intensity + 1);

    // === 6. 风险等级 ===
    let riskLevel = 'none';
    if (HIGH_RISK.indexOf(primaryEmotion) >= 0 && intensity >= 7) riskLevel = 'high';
    else if (intensity >= 5) riskLevel = 'medium';
    else if (primaryEmotion !== '正常' && primaryEmotion !== '高兴' && intensity >= 3) riskLevel = 'low';

    // === 7. 记录历史 ===
    const record = { time: now, emotion: primaryEmotion, scores: Object.assign({}, fusedScores), intensity: intensity };
    history.push(record);
    if (history.length > 60) history.shift(); // 保留最近60条(约1分钟)

    // === 8. 组装结果 ===
    return {
      icon: emotionIcon(primaryEmotion),
      text: primaryEmotion,
      confidence: confidence,
      intensity: intensity,
      color: emotionColor(primaryEmotion),
      riskLevel: riskLevel,
      // 微表情/肢体
      faceTension: micro.browFurrow > 0.22 ? '#ef4444' : '#10b981',
      faceLabel: micro.browFurrow > 0.22 ? '\u504f\u9ad8' : '\u6b63\u5e38',
      browFurrow: Math.round((micro.browFurrow || 0) * 100),
      mouthCornerDrop: Math.round((micro.mouthCornerDrop || 0) * 100),
      mouthDown: (micro.mouthCornerDrop || 0) > 0.18 ? '#f59e0b' : '#10b981',
      mouthCornerUp: Math.round((micro.mouthCornerUp || 0) * 100),
      mouthOpen: Math.round((micro.mouthOpen || 0) * 100),
      mouthAsymmetry: Math.round((micro.mouthAsymmetry || 0) * 100),
      eyeOpen: Math.round((micro.eyeOpen || 0) * 100),
      eyeOpenColor: (micro.eyeOpen || 0) > 0.3 ? '#f59e0b' : '#10b981',
      gazeAvert: Math.max(micro.gazeAversion || 0, micro.gazeInstability || 0) > 0.22 ? '#f59e0b' : '#10b981',
      gazeLabel: Math.max(micro.gazeAversion || 0, micro.gazeInstability || 0) > 0.22 ? '\u6ce8\u610f' : '\u6b63\u5e38',
      gazeAversion: Math.round((micro.gazeAversion || 0) * 100),
      headDownPercent: Math.round((micro.headDown || 0) * 100),
      posture: (micro.headDown > 0.4 || micro.postureStiffness > 0.45) ? '#ef4444' : '#10b981',
      postureLabel: (micro.headDown > 0.4 || micro.postureStiffness > 0.45) ? '\u504f\u9ad8' : '\u6b63\u5e38',
      postureStiffness: Math.round((micro.postureStiffness || 0) * 100),
      postureStiffnessLabel: micro.postureStiffness > 0.45 ? '\u504f\u50f5\u786c' : '\u6b63\u5e38',
      postureStiffnessColor: micro.postureStiffness > 0.45 ? '#f59e0b' : '#10b981',
      poseDetected: !!micro.poseDetected,
      detectionSource: micro.detectionSource || 'face-keypoints',
      shoulderSlope: Math.round((micro.shoulderSlope || 0) * 100),
      forwardHead: Math.round((micro.forwardHead || 0) * 100),
      slouch: Math.round((micro.slouch || 0) * 100),
      scratchHead: Math.round((micro.scratchHead || 0) * 100),
      touchNose: Math.round((micro.touchNose || 0) * 100),
      handNearFace: Math.round((micro.handNearFace || 0) * 100),
      gazeInstability: Math.round((micro.gazeInstability || 0) * 100),
      rawMicro: {
        browFurrow: Number((micro.browFurrow || 0).toFixed(3)),
        gazeAversion: Number((micro.gazeAversion || 0).toFixed(3)),
        headDown: Number((micro.headDown || 0).toFixed(3)),
        postureStiffness: Number((micro.postureStiffness || 0).toFixed(3)),
        shoulderSlope: Number((micro.shoulderSlope || 0).toFixed(3)),
        forwardHead: Number((micro.forwardHead || 0).toFixed(3)),
        slouch: Number((micro.slouch || 0).toFixed(3)),
        scratchHead: Number((micro.scratchHead || 0).toFixed(3)),
        touchNose: Number((micro.touchNose || 0).toFixed(3)),
        handNearFace: Number((micro.handNearFace || 0).toFixed(3)),
        gazeInstability: Number((micro.gazeInstability || 0).toFixed(3))
      },
      // 语音
      speechRate: voiceState ? Math.round(voiceState.speechRate * 100) : 0,
      speechRateLabel: voiceState && voiceState.speechRate > 0.45 ? '偏快' : '正常',
      pauseRatio: voiceState ? Math.round(voiceState.pauseRatio * 100) : 0,
      isSpeaking: voiceState ? voiceState.isSpeaking : false,
      audioVolume: voiceState ? Math.round((voiceState.volume || 0) * 100) : 0,
      pitch: voiceState ? Math.round(voiceState.pitch || 0) : 0,
      // 综合
      secondaryEmotion: secondary[0],
      allScores: fusedScores,
      timestamp: now
    };
  }

  function emotionIcon(e) {
    var m = { 高兴:'😊',正常:'😐',平静:'😌',焦虑:'😰',恐惧:'😨',愤怒:'😡',悲伤:'😢',压抑:'😞',紧张:'😬',惊讶:'😲',烦躁:'😤',低落:'😔',厌恶:'🤢' };
    return m[e] || '🤔';
  }

  function emotionColor(e) {
    var c = { 高兴:'#10b981',正常:'#94a3b8',平静:'#3b82f6',焦虑:'#f59e0b',恐惧:'#ef4444',愤怒:'#ef4444',悲伤:'#6366f1',压抑:'#8b5cf6',紧张:'#e67e22',惊讶:'#f39c12',烦躁:'#f97316',低落:'#94a3b8',厌恶:'#7f8c8d' };
    return c[e] || '#94a3b8';
  }

  return {
    fuse: fuse,
    emotionIcon: emotionIcon,
    emotionColor: emotionColor,
    EMOTIONS: EMOTIONS,
    HIGH_RISK: HIGH_RISK
  };
})();
