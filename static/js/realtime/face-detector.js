
/**
 * Lingxin realtime face landmarks and lightweight pose detector.
 * Face: face-api.js 68 landmarks + MediaPipe FaceMesh; Pose: MediaPipe Pose when available.
 */
window.FaceEmotionDetector = (function() {
  const MODEL_URLS = [
    '/static/models/faceapi/',                                    // 本地模型（优先，摆脱 CDN）
    'https://cdn.bootcdn.net/ajax/libs/face-api.js/0.22.2/model/',  // 国内 CDN 兜底
    'https://cdn.jsdelivr.net/npm/face-api.js@0.22.2/model/'       // 国际 CDN 兜底
  ];

  const POSE_SCRIPT_URLS = [
    'https://cdn.jsdelivr.net/npm/@mediapipe/pose/pose.js',
    'https://unpkg.com/@mediapipe/pose/pose.js'
  ];

  const FACEMESH_SCRIPT_URLS = [
    'https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/face_mesh.js',
    'https://unpkg.com/@mediapipe/face_mesh/face_mesh.js'
  ];

  let modelsLoaded = false;
  let loadingPromise = null;
  let poseLoadingPromise = null;
  let poseEstimator = null;
  let faceMeshEstimator = null;
  let lastPoseAt = 0;
  let lastFaceMeshAt = 0;
  let lastPoseMicro = null;
  let lastPoseLandmarks = null;
  let faceMeshLoadingPromise = null;
  let lastFaceMeshMicro = null;
  let lastFaceMeshLandmarks = null;
  let faceCropCanvas = null;
  let faceMeshCropCanvas = null;
  let activeFaceMeshCropRegion = null;
  let lastFaceMeshCropUsed = false;
  const microHistory = [];
  let faceBaseline = null;
  let faceBaselineCount = 0;
  let lastMetricKey = '';
  const diagnostics = {
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
  };

  const EMOTION_MAP = {
    happy: '\u9ad8\u5174', sad: '\u60b2\u4f24', angry: '\u6124\u6012',
    fearful: '\u6050\u60e7', disgusted: '\u538c\u6076', surprised: '\u60ca\u8bb6',
    neutral: '\u6b63\u5e38'
  };

  function clamp01(value) {
    if (!Number.isFinite(value)) return 0;
    return Math.max(0, Math.min(1, value));
  }

  function distance(a, b) {
    if (!a || !b) return 0;
    const dx = (a.x || 0) - (b.x || 0);
    const dy = (a.y || 0) - (b.y || 0);
    return Math.sqrt(dx * dx + dy * dy);
  }

  function center(points) {
    if (!points || !points.length) return null;
    const total = points.reduce(function(acc, p) {
      acc.x += p.x || 0; acc.y += p.y || 0; return acc;
    }, { x: 0, y: 0 });
    return { x: total.x / points.length, y: total.y / points.length };
  }

  function avg(values) {
    const valid = values.filter(function(v) { return Number.isFinite(v); });
    return valid.length ? valid.reduce(function(a, b) { return a + b; }, 0) / valid.length : 0;
  }

  function nowTime() {
    return new Date().toTimeString().slice(0, 8);
  }

  function updateDiagnostics(patch) {
    Object.assign(diagnostics, patch || {});
    diagnostics.lastUpdate = nowTime();
  }

  function metricSnapshot(micro) {
    micro = micro || {};
    return {
      browFurrow: Math.round((micro.browFurrow || 0) * 100),
      gazeAversion: Math.round((micro.gazeAversion || 0) * 100),
      headDown: Math.round((micro.headDown || 0) * 100),
      postureStiffness: Math.round((micro.postureStiffness || 0) * 100),
      shoulderSlope: Math.round((micro.shoulderSlope || 0) * 100),
      forwardHead: Math.round((micro.forwardHead || 0) * 100),
      slouch: Math.round((micro.slouch || 0) * 100),
      scratchHead: Math.round((micro.scratchHead || 0) * 100),
      touchNose: Math.round((micro.touchNose || 0) * 100),
      handNearFace: Math.round((micro.handNearFace || 0) * 100),
      gazeInstability: Math.round((micro.gazeInstability || 0) * 100)
    };
  }

  function metricDiagnostics(micro) {
    diagnostics.frameCount += 1;
    const snapshot = metricSnapshot(micro);
    const metricKey = Object.keys(snapshot).map(function(key) { return snapshot[key]; }).join('|');
    const patch = { frameCount: diagnostics.frameCount, rawMicro: snapshot };
    if (metricKey !== lastMetricKey) {
      lastMetricKey = metricKey;
      patch.changedAt = nowTime();
    }
    return patch;
  }

  function updateFaceBaseline(metrics, expressions) {
    if (!metrics) return;
    const expressive = Math.max(
      getExpressionScore(expressions, 'angry'),
      getExpressionScore(expressions, 'sad'),
      getExpressionScore(expressions, 'fearful')
    );
    if (expressive > 0.35 && faceBaselineCount > 8) return;
    if (!faceBaseline) {
      faceBaseline = Object.assign({}, metrics);
      faceBaselineCount = 1;
      return;
    }
    const alpha = faceBaselineCount < 20 ? 0.16 : 0.04;
    Object.keys(metrics).forEach(function(key) {
      if (Number.isFinite(metrics[key])) {
        if (!Number.isFinite(faceBaseline[key])) faceBaseline[key] = metrics[key];
        else faceBaseline[key] = faceBaseline[key] * (1 - alpha) + metrics[key] * alpha;
      }
    });
    faceBaselineCount = Math.min(60, faceBaselineCount + 1);
  }

  function loadScriptOnce(urls, globalName) {
    if (window[globalName]) return Promise.resolve(true);
    return new Promise(function(resolve) {
      let index = 0;
      function next() {
        if (window[globalName]) return resolve(true);
        if (index >= urls.length) return resolve(false);
        const script = document.createElement('script');
        script.src = urls[index++];
        script.crossOrigin = 'anonymous';
        script.onload = function() { resolve(!!window[globalName]); };
        script.onerror = next;
        document.head.appendChild(script);
      }
      next();
    });
  }

  function getExpressionScore(expressions, name) {
    return expressions && Number.isFinite(expressions[name]) ? expressions[name] : 0;
  }

  function pointFromLandmark(landmarks, index) {
    const point = landmarks && landmarks[index];
    if (!point) return null;
    return { x: point.x || 0, y: point.y || 0, z: point.z || 0 };
  }

  function avgPoint(landmarks, indexes) {
    const points = (indexes || []).map(function(index) { return pointFromLandmark(landmarks, index); }).filter(Boolean);
    if (!points.length) return null;
    return {
      x: avg(points.map(function(point) { return point.x; })),
      y: avg(points.map(function(point) { return point.y; })),
      z: avg(points.map(function(point) { return point.z || 0; }))
    };
  }

  function visiblePosePoint(pointValue, threshold) {
    threshold = threshold === undefined ? 0.25 : threshold;
    return !!(pointValue && (pointValue.visibility === undefined || pointValue.visibility > threshold));
  }

  function getPoseFaceCropRegion(videoElement, scale) {
    const width = videoElement && videoElement.videoWidth ? videoElement.videoWidth : 0;
    const height = videoElement && videoElement.videoHeight ? videoElement.videoHeight : 0;
    if (!width || !height || !lastPoseLandmarks || !lastPoseLandmarks[0]) return null;
    const nose = lastPoseLandmarks[0];
    const leftEar = lastPoseLandmarks[7];
    const rightEar = lastPoseLandmarks[8];
    const leftEye = lastPoseLandmarks[2];
    const rightEye = lastPoseLandmarks[5];
    const leftShoulder = lastPoseLandmarks[11];
    const rightShoulder = lastPoseLandmarks[12];
    if (!visiblePosePoint(nose, 0.18)) return null;
    const shoulderWidth = visiblePosePoint(leftShoulder, 0.18) && visiblePosePoint(rightShoulder, 0.18) ? Math.abs(leftShoulder.x - rightShoulder.x) * width : width * 0.25;
    const earWidth = visiblePosePoint(leftEar, 0.18) && visiblePosePoint(rightEar, 0.18) ? Math.abs(leftEar.x - rightEar.x) * width : 0;
    const eyeWidth = visiblePosePoint(leftEye, 0.18) && visiblePosePoint(rightEye, 0.18) ? Math.abs(leftEye.x - rightEye.x) * width : 0;
    const boxSize = Math.max(112, Math.min(width, height, Math.max(shoulderWidth * (scale || 1.35), earWidth * 3.2, eyeWidth * 5.8, width * 0.22)));
    return {
      x: Math.max(0, Math.min(width - boxSize, nose.x * width - boxSize / 2)),
      y: Math.max(0, Math.min(height - boxSize, nose.y * height - boxSize * 0.48)),
      size: boxSize,
      width: width,
      height: height
    };
  }

  function mapFaceMeshLandmarks(landmarks, region) {
    if (!region || !landmarks || !landmarks.length) return landmarks || null;
    return landmarks.map(function(point) {
      return {
        x: (region.x + (point.x || 0) * region.size) / region.width,
        y: (region.y + (point.y || 0) * region.size) / region.height,
        z: point.z || 0
      };
    });
  }

  function updateFaceMeshBaseline(metrics) {
    if (!metrics) return;
    if (!faceBaseline) {
      faceBaseline = Object.assign({}, metrics);
      faceBaselineCount = 1;
      return;
    }
    const alpha = faceBaselineCount < 20 ? 0.18 : 0.035;
    Object.keys(metrics).forEach(function(key) {
      if (Number.isFinite(metrics[key])) {
        if (!Number.isFinite(faceBaseline[key])) faceBaseline[key] = metrics[key];
        else faceBaseline[key] = faceBaseline[key] * (1 - alpha) + metrics[key] * alpha;
      }
    });
    faceBaselineCount = Math.min(60, faceBaselineCount + 1);
  }

  function analyzeFaceMeshLandmarks(landmarks) {
    const result = {
      browFurrow: 0,
      gazeAversion: 0,
      gazeInstability: 0,
      headYaw: 0,
      headTilt: 0,
      mouthCornerDrop: 0,
      mouthCornerUp: 0,
      mouthOpen: 0,
      mouthAsymmetry: 0,
      innerBrowRaise: 0,
      eyeOpen: 0,
      eyeSquint: 0,
      faceDetected: !!(landmarks && landmarks.length),
      poseDetected: false,
      detectionSource: 'facemesh'
    };
    if (!landmarks || landmarks.length < 468) return result;

    const leftEyeOuter = pointFromLandmark(landmarks, 33);
    const leftEyeInner = pointFromLandmark(landmarks, 133);
    const rightEyeInner = pointFromLandmark(landmarks, 362);
    const rightEyeOuter = pointFromLandmark(landmarks, 263);
    const leftEyeCenter = avgPoint(landmarks, [33, 133, 159, 145]);
    const rightEyeCenter = avgPoint(landmarks, [362, 263, 386, 374]);
    const eyeMid = avgPoint(landmarks, [33, 133, 362, 263]);
    const eyeDistance = Math.max(0.001, distance(leftEyeCenter, rightEyeCenter));
    const leftInnerBrow = avgPoint(landmarks, [55, 65, 52, 53]);
    const rightInnerBrow = avgPoint(landmarks, [285, 295, 282, 283]);
    const leftOuterBrow = avgPoint(landmarks, [70, 63, 105]);
    const rightOuterBrow = avgPoint(landmarks, [336, 296, 300]);
    const noseTip = pointFromLandmark(landmarks, 1) || pointFromLandmark(landmarks, 4);
    const mouthCenter = avgPoint(landmarks, [13, 14, 78, 308]);
    const leftMouthCorner = pointFromLandmark(landmarks, 61);
    const rightMouthCorner = pointFromLandmark(landmarks, 291);
    const chin = pointFromLandmark(landmarks, 152);
    const faceHeight = Math.max(0.001, distance(eyeMid, chin));
    const metrics = {};

    if (leftInnerBrow && rightInnerBrow && leftEyeCenter && rightEyeCenter) {
      metrics.fmInnerBrowGap = distance(leftInnerBrow, rightInnerBrow) / eyeDistance;
      const leftBrowEye = Math.abs(leftInnerBrow.y - leftEyeCenter.y) / eyeDistance;
      const rightBrowEye = Math.abs(rightInnerBrow.y - rightEyeCenter.y) / eyeDistance;
      metrics.fmBrowEyeGap = avg([leftBrowEye, rightBrowEye]);
      const innerDrop = avg([
        leftOuterBrow ? (leftInnerBrow.y - leftOuterBrow.y) / eyeDistance : 0,
        rightOuterBrow ? (rightInnerBrow.y - rightOuterBrow.y) / eyeDistance : 0
      ]);
      metrics.fmInnerBrowDrop = innerDrop;
      const inwardScore = clamp01((0.32 - metrics.fmInnerBrowGap) / 0.14);
      const lowerScore = clamp01((0.245 - metrics.fmBrowEyeGap) / 0.105);
      const squeezeScore = clamp01((innerDrop + 0.015) / 0.085);
      const relativeInward = faceBaseline && Number.isFinite(faceBaseline.fmInnerBrowGap) ? clamp01((faceBaseline.fmInnerBrowGap - metrics.fmInnerBrowGap) / 0.04) : 0;
      const relativeLower = faceBaseline && Number.isFinite(faceBaseline.fmBrowEyeGap) ? clamp01((faceBaseline.fmBrowEyeGap - metrics.fmBrowEyeGap) / 0.035) : 0;
      const relativeDrop = faceBaseline && Number.isFinite(faceBaseline.fmInnerBrowDrop) ? clamp01((metrics.fmInnerBrowDrop - faceBaseline.fmInnerBrowDrop) / 0.045) : 0;
      result.browFurrow = clamp01(Math.max(
        inwardScore * 0.46 + lowerScore * 0.30 + squeezeScore * 0.22,
        relativeInward * 0.55 + relativeLower * 0.36 + relativeDrop * 0.32
      ));
    }

    if (leftEyeOuter && leftEyeInner && rightEyeInner && rightEyeOuter) {
      const leftIris = avgPoint(landmarks, [468, 469, 470, 471, 472]);
      const rightIris = avgPoint(landmarks, [473, 474, 475, 476, 477]);
      let irisOffset = 0;
      if (leftIris && rightIris) {
        const leftRatio = (leftIris.x - leftEyeOuter.x) / Math.max(0.001, leftEyeInner.x - leftEyeOuter.x);
        const rightRatio = (rightIris.x - rightEyeInner.x) / Math.max(0.001, rightEyeOuter.x - rightEyeInner.x);
        const leftVertical = Math.abs((leftIris.y - leftEyeCenter.y) / Math.max(0.001, distance(leftEyeOuter, leftEyeInner)));
        const rightVertical = Math.abs((rightIris.y - rightEyeCenter.y) / Math.max(0.001, distance(rightEyeOuter, rightEyeInner)));
        const horizontal = Math.max(Math.abs(leftRatio - 0.5), Math.abs(rightRatio - 0.5));
        // 校准：虹膜检测有噪声，阈值大幅抬高；注视不动应接近 0，明显侧视才触发
        irisOffset = clamp01((horizontal - 0.25) / 0.18 + Math.max(leftVertical, rightVertical) * 0.3);
      }
      const yaw = noseTip && eyeMid ? Math.abs(noseTip.x - eyeMid.x) / eyeDistance : 0;
      const eyeLineTilt = leftEyeCenter && rightEyeCenter ? Math.abs(leftEyeCenter.y - rightEyeCenter.y) / eyeDistance : 0;
      result.headYaw = clamp01(yaw / 0.16);
      result.headTilt = clamp01(eyeLineTilt / 0.10);
      result.gazeAversion = clamp01(Math.max(irisOffset, result.headYaw * 0.25 + result.headTilt * 0.10));
    }

    if (eyeMid && noseTip && mouthCenter && chin) {
      metrics.fmNoseBelowEyes = (noseTip.y - eyeMid.y) / faceHeight;
      metrics.fmNoseToMouth = distance(noseTip, mouthCenter) / faceHeight;
      // 只用相对基线：低头 = 相对平静时鼻子位置下降，坐直自然为 0
      const relativePitch = faceBaseline && Number.isFinite(faceBaseline.fmNoseBelowEyes) ? clamp01((metrics.fmNoseBelowEyes - faceBaseline.fmNoseBelowEyes) / 0.04) : 0;
      result.headDown = clamp01(relativePitch * 1.5);
    }

    // ===== FACS 面部动作单元（AU）提取 =====
    // 1. 嘴角方向：上扬（真笑/快乐）vs 下拉（悲伤），以及左右不对称（轻蔑）
    if (leftMouthCorner && rightMouthCorner && mouthCenter) {
      const cornerOffset = ((leftMouthCorner.y - mouthCenter.y) + (rightMouthCorner.y - mouthCenter.y)) / 2 / faceHeight;
      metrics.fmMouthCornerOffset = cornerOffset;  // 记录原始值供基线
      // 相对平静基线的偏离：平静=0，下拉/上扬才有值
      const baselineOffset = faceBaseline && Number.isFinite(faceBaseline.fmMouthCornerOffset) ? faceBaseline.fmMouthCornerOffset : cornerOffset;
      result.mouthCornerDrop = clamp01((cornerOffset - baselineOffset) / 0.03);  // 下拉 → 悲伤
      result.mouthCornerUp = clamp01((baselineOffset - cornerOffset) / 0.03);    // 上扬 → 快乐
      result.mouthAsymmetry = clamp01(Math.abs(leftMouthCorner.y - rightMouthCorner.y) / faceHeight / 0.05); // 单侧 → 轻蔑
    }

    // 2. 嘴巴张开度：上下唇距离（惊讶/恐惧）
    const upperLip = pointFromLandmark(landmarks, 13);
    const lowerLip = pointFromLandmark(landmarks, 14);
    if (upperLip && lowerLip) {
      result.mouthOpen = clamp01(distance(upperLip, lowerLip) / faceHeight / 0.35);
    }

    // 3. 眼睛睁开度：瞪大（恐惧/愤怒）vs 微眯（厌恶/真笑时眼轮匝肌收缩）
    const leftUpperLid = pointFromLandmark(landmarks, 159);
    const leftLowerLid = pointFromLandmark(landmarks, 145);
    const rightUpperLid = pointFromLandmark(landmarks, 386);
    const rightLowerLid = pointFromLandmark(landmarks, 374);
    if (leftUpperLid && leftLowerLid && rightUpperLid && rightLowerLid) {
      const leftOpen = distance(leftUpperLid, leftLowerLid) / eyeDistance;
      const rightOpen = distance(rightUpperLid, rightLowerLid) / eyeDistance;
      const open = (leftOpen + rightOpen) / 2;
      metrics.fmEyeOpen = open;  // 记录原始值供基线
      // 相对平静基线的偏离：平静=0，瞪大/微眯才有值
      const baselineOpen = faceBaseline && Number.isFinite(faceBaseline.fmEyeOpen) ? faceBaseline.fmEyeOpen : open;
      result.eyeOpen = clamp01((open - baselineOpen) / 0.06);   // 瞪大
      result.eyeSquint = clamp01((baselineOpen - open) / 0.06); // 微眯
    }

    // 4. 眉毛内角上扬（悲伤的倒八字眉 / 惊讶）
    if (leftInnerBrow && rightInnerBrow && leftEyeCenter && rightEyeCenter) {
      const leftRaise = (leftEyeCenter.y - leftInnerBrow.y) / eyeDistance;
      const rightRaise = (rightEyeCenter.y - rightInnerBrow.y) / eyeDistance;
      const raise = (leftRaise + rightRaise) / 2;
      result.innerBrowRaise = clamp01((raise - 0.15) / 0.25);
    }

    updateFaceMeshBaseline(metrics);
    result.gazeInstability = clamp01(Math.max(result.gazeInstability || 0, result.gazeAversion * 0.9));
    return result;
  }

  function mergeMicro(baseMicro, extraMicro) {
    if (!extraMicro) return baseMicro || {};
    const merged = Object.assign({}, baseMicro || {});
    ['browFurrow', 'gazeAversion', 'gazeInstability', 'headYaw', 'headTilt', 'headDown', 'mouthCornerDrop', 'mouthCornerUp', 'mouthOpen', 'mouthAsymmetry', 'innerBrowRaise', 'eyeOpen', 'eyeSquint', 'postureStiffness', 'lipTight', 'shoulderSlope', 'forwardHead', 'slouch', 'scratchHead', 'touchNose', 'handNearFace'].forEach(function(key) {
      merged[key] = clamp01(Math.max(merged[key] || 0, extraMicro[key] || 0));
    });
    merged.faceDetected = !!(merged.faceDetected || extraMicro.faceDetected);
    merged.poseDetected = !!(merged.poseDetected || extraMicro.poseDetected);
    const sources = [];
    [merged.detectionSource, extraMicro.detectionSource].forEach(function(source) {
      if (!source) return;
      String(source).split('+').forEach(function(part) {
        if (part && sources.indexOf(part) < 0) sources.push(part);
      });
    });
    merged.detectionSource = sources.join('+') || 'face-keypoints';
    return merged;
  }

  function analyzeFaceGeometry(expressions, landmarks) {
    const result = {
      browFurrow: 0,
      gazeAversion: 0,
      headDown: 0,
      postureStiffness: 0,
      lipTight: 0,
      mouthCornerDrop: 0,
      headYaw: 0,
      headTilt: 0,
      gazeInstability: 0,
      slouch: 0,
      scratchHead: 0,
      touchNose: 0,
      handNearFace: 0,
      faceDetected: true,
      poseDetected: false,
      detectionSource: 'face-keypoints'
    };

    if (!landmarks) return result;

    const leftBrow = landmarks.getLeftEyeBrow ? landmarks.getLeftEyeBrow() : [];
    const rightBrow = landmarks.getRightEyeBrow ? landmarks.getRightEyeBrow() : [];
    const leftEye = landmarks.getLeftEye ? landmarks.getLeftEye() : [];
    const rightEye = landmarks.getRightEye ? landmarks.getRightEye() : [];
    const nose = landmarks.getNose ? landmarks.getNose() : [];
    const mouth = landmarks.getMouth ? landmarks.getMouth() : [];
    const jaw = landmarks.getJawOutline ? landmarks.getJawOutline() : [];

    const leftEyeCenter = center(leftEye);
    const rightEyeCenter = center(rightEye);
    const eyeDistance = Math.max(1, distance(leftEyeCenter, rightEyeCenter));
    const faceWidth = jaw.length > 16 ? Math.max(1, distance(jaw[0], jaw[16])) : eyeDistance * 2.15;
    const faceHeight = jaw.length > 8 && nose.length > 0 ? Math.max(1, distance(center([leftBrow[0] || leftEye[0], rightBrow[4] || rightEye[3]]), jaw[8])) : eyeDistance * 2.6;
    const noseTip = nose.length ? nose[Math.min(3, nose.length - 1)] : null;
    const eyeMid = center([leftEyeCenter, rightEyeCenter].filter(Boolean));
    const mouthCenter = center(mouth);
    const metrics = {};

    if (leftBrow.length >= 5 && rightBrow.length >= 5 && leftEyeCenter && rightEyeCenter) {
      metrics.innerBrowGap = distance(leftBrow[4], rightBrow[0]) / eyeDistance;
      const leftBrowEye = avg(leftBrow.map(function(p) { return Math.abs(p.y - leftEyeCenter.y); })) / eyeDistance;
      const rightBrowEye = avg(rightBrow.map(function(p) { return Math.abs(p.y - rightEyeCenter.y); })) / eyeDistance;
      metrics.browEyeGap = avg([leftBrowEye, rightBrowEye]);
      metrics.innerBrowDrop = avg([
        (leftBrow[4].y - leftBrow[0].y) / eyeDistance,
        (rightBrow[0].y - rightBrow[4].y) / eyeDistance
      ]);
      metrics.browTilt = avg([
        Math.abs(leftBrow[4].y - leftBrow[0].y) / eyeDistance,
        Math.abs(rightBrow[0].y - rightBrow[4].y) / eyeDistance
      ]);
      const expressionBoost = getExpressionScore(expressions, 'angry') * 0.55 + getExpressionScore(expressions, 'sad') * 0.20;
      const absoluteInward = clamp01((0.68 - metrics.innerBrowGap) / 0.34);
      const absoluteLowered = clamp01((0.38 - metrics.browEyeGap) / 0.18);
      const innerDropScore = clamp01((metrics.innerBrowDrop + 0.02) / 0.16);
      const browTiltScore = clamp01((metrics.browTilt - 0.035) / 0.16);
      const relativeInward = faceBaseline ? clamp01((faceBaseline.innerBrowGap - metrics.innerBrowGap) / 0.07) : 0;
      const relativeLowered = faceBaseline ? clamp01((faceBaseline.browEyeGap - metrics.browEyeGap) / 0.05) : 0;
      const relativeDrop = faceBaseline ? clamp01((metrics.innerBrowDrop - (faceBaseline.innerBrowDrop || 0)) / 0.08) : 0;
      result.browFurrow = clamp01(
        Math.max(
          absoluteInward * 0.36 + absoluteLowered * 0.24 + innerDropScore * 0.22 + browTiltScore * 0.16,
          relativeInward * 0.48 + relativeLowered * 0.30 + relativeDrop * 0.28
        ) + expressionBoost
      );
    }

    if (eyeMid && noseTip) {
      const yaw = Math.abs(noseTip.x - eyeMid.x) / eyeDistance;
      const noseBias = clamp01(Math.abs(noseTip.x - eyeMid.x) / eyeDistance / 0.22);
      let eyeAsymmetry = 0;
      if (leftEye.length >= 6 && rightEye.length >= 6) {
        const leftOpen = distance(leftEye[1], leftEye[5]) / eyeDistance;
        const rightOpen = distance(rightEye[1], rightEye[5]) / eyeDistance;
        const leftWidth = Math.max(1, distance(leftEye[0], leftEye[3])) / eyeDistance;
        const rightWidth = Math.max(1, distance(rightEye[0], rightEye[3])) / eyeDistance;
        eyeAsymmetry = clamp01((Math.abs(leftOpen - rightOpen) * 5.0) + (Math.abs(leftWidth - rightWidth) * 1.6));
      }
      result.headYaw = clamp01(yaw / 0.24);
      result.gazeAversion = clamp01(result.headYaw * 0.48 + noseBias * 0.34 + eyeAsymmetry * 0.28 + Math.max(0, getExpressionScore(expressions, 'neutral') - 0.70) * 0.12);
      result.gazeInstability = clamp01(Math.max(result.gazeInstability || 0, result.gazeAversion * 0.72 + eyeAsymmetry * 0.35));
    }

    if (eyeMid && noseTip && mouthCenter) {
      metrics.noseBelowEyes = (noseTip.y - eyeMid.y) / faceHeight;
      metrics.noseToMouth = distance(noseTip, mouthCenter) / faceHeight;
      metrics.jawDrop = jaw.length > 8 ? (jaw[8].y - eyeMid.y) / faceHeight : metrics.noseBelowEyes + metrics.noseToMouth;
      const absolutePitch = clamp01((metrics.noseBelowEyes - 0.22) / 0.15);
      const compressedLowerFace = clamp01((0.36 - metrics.noseToMouth) / 0.14);
      const jawLowScore = clamp01((metrics.jawDrop - 0.70) / 0.20);
      const relativePitch = faceBaseline ? clamp01((metrics.noseBelowEyes - faceBaseline.noseBelowEyes) / 0.08) : 0;
      const relativeCompression = faceBaseline ? clamp01((faceBaseline.noseToMouth - metrics.noseToMouth) / 0.08) : 0;
      result.headDown = clamp01(
        Math.max(absolutePitch * 0.42 + compressedLowerFace * 0.22 + jawLowScore * 0.18, relativePitch * 0.58 + relativeCompression * 0.22) + getExpressionScore(expressions, 'sad') * 0.16
      );
    }

    if (leftEyeCenter && rightEyeCenter) {
      result.headTilt = clamp01(Math.abs(leftEyeCenter.y - rightEyeCenter.y) / eyeDistance / 0.16);
    }

    if (mouth.length > 9) {
      const mouthWidth = distance(mouth[0], mouth[6]) / faceWidth;
      const mouthHeight = distance(mouth[3], mouth[9]) / faceHeight;
      result.lipTight = clamp01((0.32 - mouthWidth) / 0.17 + (0.055 - mouthHeight) / 0.08 + getExpressionScore(expressions, 'angry') * 0.35);
      // 嘴角向下（frown）：嘴角低于嘴唇中心 → 难过/悲伤
      const lipMid = center([mouth[3], mouth[9]].filter(Boolean));
      if (lipMid) {
        const cornerDrop = ((mouth[0].y - lipMid.y) + (mouth[6].y - lipMid.y)) / 2 / faceHeight;
        result.mouthCornerDrop = clamp01(cornerDrop / 0.055);
      }
    }

    updateFaceBaseline(metrics, expressions);
    result.postureStiffness = clamp01(result.headTilt * 0.18 + result.headDown * 0.42 + result.lipTight * 0.20 + result.browFurrow * 0.12);
    return result;
  }

  function smoothMicro(micro) {
    microHistory.push(micro);
    if (microHistory.length > 5) microHistory.shift();
    const keys = ['browFurrow', 'gazeAversion', 'headDown', 'postureStiffness', 'lipTight', 'headYaw', 'headTilt', 'shoulderSlope', 'forwardHead', 'slouch', 'scratchHead', 'touchNose', 'handNearFace', 'gazeInstability'];
    const smoothed = Object.assign({}, micro);
    keys.forEach(function(key) {
      const historyAvg = avg(microHistory.map(function(item) { return item[key]; }));
      smoothed[key] = clamp01((micro[key] || 0) * 0.62 + historyAvg * 0.38);
    });
    if (microHistory.length > 1) {
      let motion = 0;
      let count = 0;
      for (let index = Math.max(1, microHistory.length - 5); index < microHistory.length; index++) {
        const prev = microHistory[index - 1] || {};
        const curr = microHistory[index] || {};
        motion += Math.abs((curr.headYaw || 0) - (prev.headYaw || 0));
        motion += Math.abs((curr.headTilt || 0) - (prev.headTilt || 0));
        motion += Math.abs((curr.gazeAversion || 0) - (prev.gazeAversion || 0));
        count += 1;
      }
      const instability = clamp01((motion / Math.max(1, count)) * 3.8 + (smoothed.gazeAversion || 0) * 0.72);
      smoothed.gazeInstability = clamp01(Math.max(smoothed.gazeInstability || 0, instability));
      smoothed.handNearFace = clamp01(Math.max(smoothed.handNearFace || 0, smoothed.scratchHead || 0, smoothed.touchNose || 0));
    }
    return smoothed;
  }

  async function ensurePoseEstimator() {
    if (poseEstimator) return poseEstimator;
    if (poseLoadingPromise) return poseLoadingPromise;
    poseLoadingPromise = (async function() {
      const ok = await loadScriptOnce(POSE_SCRIPT_URLS, 'Pose');
      if (!ok || !window.Pose) {
        updateDiagnostics({ poseDetected: false, status: diagnostics.faceDetected ? 'face-only' : diagnostics.status, lastError: 'pose-model-unavailable' });
        return null;
      }
      const pose = new window.Pose({ locateFile: function(file) { return 'https://cdn.jsdelivr.net/npm/@mediapipe/pose/' + file; } });
      pose.setOptions({
        modelComplexity: 0,
        smoothLandmarks: true,
        enableSegmentation: false,
        minDetectionConfidence: 0.30,
        minTrackingConfidence: 0.30
      });
      pose.onResults(function(results) {
        lastPoseLandmarks = results && results.poseLandmarks ? results.poseLandmarks : null;
        lastPoseMicro = analyzePose(results);
      });
      poseEstimator = pose;
      return poseEstimator;
    })();
    return poseLoadingPromise;
  }

  async function ensureFaceMeshEstimator() {
    if (faceMeshEstimator) return faceMeshEstimator;
    if (faceMeshLoadingPromise) return faceMeshLoadingPromise;
    faceMeshLoadingPromise = (async function() {
      const ok = await loadScriptOnce(FACEMESH_SCRIPT_URLS, 'FaceMesh');
      if (!ok || !window.FaceMesh) {
        updateDiagnostics({ faceMeshDetected: false, lastError: diagnostics.lastError || 'facemesh-model-unavailable' });
        return null;
      }
      const faceMesh = new window.FaceMesh({ locateFile: function(file) { return 'https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/' + file; } });
      faceMesh.setOptions({
        maxNumFaces: 1,
        refineLandmarks: true,
        minDetectionConfidence: 0.35,
        minTrackingConfidence: 0.35
      });
      faceMesh.onResults(function(results) {
        const rawLandmarks = results && results.multiFaceLandmarks && results.multiFaceLandmarks.length ? results.multiFaceLandmarks[0] : null;
        lastFaceMeshLandmarks = rawLandmarks ? mapFaceMeshLandmarks(rawLandmarks, activeFaceMeshCropRegion) : null;
        lastFaceMeshMicro = lastFaceMeshLandmarks ? analyzeFaceMeshLandmarks(lastFaceMeshLandmarks) : null;
        lastFaceMeshCropUsed = !!(lastFaceMeshMicro && activeFaceMeshCropRegion);
      });
      faceMeshEstimator = faceMesh;
      return faceMeshEstimator;
    })();
    return faceMeshLoadingPromise;
  }

  async function estimateFaceMesh(videoElement) {
    if (!videoElement || videoElement.readyState < 2) return null;
    const now = Date.now();
    if (now - lastFaceMeshAt < 260) return lastFaceMeshMicro;
    lastFaceMeshAt = now;
    try {
      const faceMesh = await ensureFaceMeshEstimator();
      if (!faceMesh || !faceMesh.send) return lastFaceMeshMicro;
      diagnostics.faceMeshFrameCount += 1;
      lastFaceMeshCropUsed = false;
      activeFaceMeshCropRegion = null;
      await faceMesh.send({ image: videoElement });
      if (!lastFaceMeshMicro) {
        const region = getPoseFaceCropRegion(videoElement, 1.55);
        if (region) {
          faceMeshCropCanvas = faceMeshCropCanvas || document.createElement('canvas');
          faceMeshCropCanvas.width = 416;
          faceMeshCropCanvas.height = 416;
          const ctx = faceMeshCropCanvas.getContext('2d');
          if (ctx) {
            ctx.clearRect(0, 0, 416, 416);
            ctx.drawImage(videoElement, region.x, region.y, region.size, region.size, 0, 0, 416, 416);
            activeFaceMeshCropRegion = region;
            await faceMesh.send({ image: faceMeshCropCanvas });
            activeFaceMeshCropRegion = null;
          }
        }
      }
      updateDiagnostics({ faceMeshDetected: !!lastFaceMeshMicro, faceMeshFrameCount: diagnostics.faceMeshFrameCount, faceMeshCropUsed: !!lastFaceMeshCropUsed });
      return lastFaceMeshMicro;
    } catch (e) {
      activeFaceMeshCropRegion = null;
      updateDiagnostics({ faceMeshDetected: false, lastError: e && e.message ? e.message : 'facemesh-detect-error' });
      return lastFaceMeshMicro;
    }
  }

  function analyzePose(results) {
    const landmarks = results && results.poseLandmarks;
    if (!landmarks || landmarks.length < 25) return null;
    function point(index) { return landmarks[index] || {}; }
    function visible(pointValue) { return pointValue && (pointValue.visibility === undefined || pointValue.visibility > 0.35); }

    const nose = point(0), leftEar = point(7), rightEar = point(8);
    const leftShoulder = point(11), rightShoulder = point(12);
    const leftWrist = point(15), rightWrist = point(16);
    const leftHip = point(23), rightHip = point(24);
    if (!visible(leftShoulder) || !visible(rightShoulder)) return null;

    const shoulderWidth = Math.max(0.001, Math.abs(leftShoulder.x - rightShoulder.x));
    const shoulderSlope = Math.abs(leftShoulder.y - rightShoulder.y) / shoulderWidth;
    const shoulderCenter = { x: (leftShoulder.x + rightShoulder.x) / 2, y: (leftShoulder.y + rightShoulder.y) / 2 };
    const hipVisible = visible(leftHip) && visible(rightHip);
    const hipCenter = hipVisible ? { x: (leftHip.x + rightHip.x) / 2, y: (leftHip.y + rightHip.y) / 2 } : null;
    const earCenter = visible(leftEar) && visible(rightEar) ? { x: (leftEar.x + rightEar.x) / 2, y: (leftEar.y + rightEar.y) / 2 } : null;

    let forwardHead = 0;
    let headDown = 0;
    if (visible(nose)) {
      forwardHead = clamp01(Math.abs(nose.x - shoulderCenter.x) / shoulderWidth / 0.38);
      if (earCenter) headDown = clamp01((nose.y - earCenter.y) / 0.09);
      else headDown = clamp01((nose.y - shoulderCenter.y + 0.18) / 0.18);
    }

    let slouch = 0;
    if (hipCenter) {
      const torsoLean = Math.abs(shoulderCenter.x - hipCenter.x) / shoulderWidth;
      const torsoCompression = clamp01((0.42 - Math.abs(hipCenter.y - shoulderCenter.y)) / 0.24);
      slouch = clamp01(torsoLean * 0.52 + torsoCompression * 0.40 + forwardHead * 0.30);
    }

    const wrists = [leftWrist, rightWrist].filter(visible);
    let scratchHead = 0;
    let touchNose = 0;
    let handNearFace = 0;
    if (wrists.length && visible(nose)) {
      const wristNose = Math.min.apply(null, wrists.map(function(wrist) { return distance(wrist, nose) / shoulderWidth; }));
      touchNose = clamp01((0.58 - wristNose) / 0.34);
      const headAnchors = [leftEar, rightEar, nose].filter(visible);
      const wristHead = headAnchors.length ? Math.min.apply(null, wrists.map(function(wrist) {
        return Math.min.apply(null, headAnchors.map(function(anchor) { return distance(wrist, anchor) / shoulderWidth; }));
      })) : 9;
      const handAboveFace = wrists.some(function(wrist) { return wrist.y < nose.y + 0.04 && Math.abs(wrist.x - nose.x) / shoulderWidth < 0.95; });
      scratchHead = clamp01(Math.max((0.68 - wristHead) / 0.42, handAboveFace ? 0.65 : 0));
      handNearFace = clamp01(Math.max(touchNose, scratchHead, (0.78 - wristHead) / 0.48));
    }

    const postureStiffness = clamp01(shoulderSlope * 0.26 + forwardHead * 0.24 + slouch * 0.36 + headDown * 0.18 + handNearFace * 0.08);
    return {
      headDown: clamp01(headDown),
      postureStiffness: postureStiffness,
      shoulderSlope: clamp01(shoulderSlope / 0.35),
      forwardHead: forwardHead,
      slouch: slouch,
      scratchHead: scratchHead,
      touchNose: touchNose,
      handNearFace: handNearFace,
      poseDetected: true,
      detectionSource: 'face-keypoints+pose'
    };
  }

  async function estimatePose(videoElement) {
    if (!videoElement || videoElement.readyState < 2) return null;
    const now = Date.now();
    if (now - lastPoseAt < 450) return lastPoseMicro;
    lastPoseAt = now;
    try {
      const pose = await ensurePoseEstimator();
      if (!pose || !pose.send) {
        updateDiagnostics({ poseDetected: false, status: diagnostics.faceDetected ? 'face-only' : diagnostics.status, lastError: 'pose-model-unavailable' });
        return lastPoseMicro;
      }
      diagnostics.poseFrameCount += 1;
      await pose.send({ image: videoElement });
      if (!lastPoseMicro) diagnostics.poseNoLandmarkCount += 1;
      return lastPoseMicro;
    } catch (e) {
      updateDiagnostics({ poseDetected: false, lastError: e && e.message ? e.message : 'pose-detect-error' });
      return lastPoseMicro;
    }
  }

  function mergePoseMicro(faceMicro, poseMicro) {
    if (!poseMicro) return faceMicro || {};
    faceMicro = faceMicro || {};
    const merged = mergeMicro(faceMicro, poseMicro);
    merged.headDown = clamp01(Math.max(faceMicro.headDown || 0, (faceMicro.headDown || 0) * 0.45 + (poseMicro.headDown || 0) * 0.55));
    merged.postureStiffness = clamp01(Math.max((faceMicro.postureStiffness || 0) * 0.35 + (poseMicro.postureStiffness || 0) * 0.65, poseMicro.slouch || 0, faceMicro.postureStiffness || 0));
    merged.poseDetected = !!poseMicro.poseDetected;
    merged.shoulderSlope = poseMicro.shoulderSlope || 0;
    merged.forwardHead = poseMicro.forwardHead || 0;
    merged.slouch = poseMicro.slouch || 0;
    merged.scratchHead = poseMicro.scratchHead || 0;
    merged.touchNose = poseMicro.touchNose || 0;
    merged.handNearFace = Math.max(poseMicro.handNearFace || 0, poseMicro.scratchHead || 0, poseMicro.touchNose || 0);
    merged.detectionSource = merged.detectionSource || poseMicro.detectionSource || faceMicro.detectionSource;
    return merged;
  }


  async function detectFaceResult(videoElement, options) {
    let result = await faceapi.detectSingleFace(videoElement, options)
      .withFaceLandmarks()
      .withFaceExpressions();
    if (result || !lastPoseLandmarks || !lastPoseLandmarks[0]) return { result: result, cropUsed: false };

    const region = getPoseFaceCropRegion(videoElement, 1.35);
    if (!region) return { result: null, cropUsed: false };
    faceCropCanvas = faceCropCanvas || document.createElement('canvas');
    faceCropCanvas.width = 416;
    faceCropCanvas.height = 416;
    const ctx = faceCropCanvas.getContext('2d');
    if (!ctx) return { result: null, cropUsed: false };
    ctx.clearRect(0, 0, 416, 416);
    ctx.drawImage(videoElement, region.x, region.y, region.size, region.size, 0, 0, 416, 416);
    result = await faceapi.detectSingleFace(faceCropCanvas, new faceapi.TinyFaceDetectorOptions({ inputSize: 416, scoreThreshold: 0.18 }))
      .withFaceLandmarks()
      .withFaceExpressions();
    return { result: result, cropUsed: !!result };
  }

  async function loadModels() {
    if (modelsLoaded) return true;
    if (loadingPromise) return loadingPromise;
    if (typeof faceapi === 'undefined') {
      console.warn('face-api.js not loaded; please check network');
      updateDiagnostics({ modelReady: false, status: 'waiting-faceapi-script', lastError: 'face-api.js not loaded' });
      return false;
    }

    loadingPromise = (async function() {
      for (var i = 0; i < MODEL_URLS.length; i++) {
        try {
          await faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URLS[i]);
          await faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URLS[i]);
          await faceapi.nets.faceExpressionNet.loadFromUri(MODEL_URLS[i]);
          modelsLoaded = true;
          updateDiagnostics({ modelReady: true, status: 'models-ready', lastError: '' });
          ensurePoseEstimator().catch(function() {});
          ensureFaceMeshEstimator().catch(function() {});
          return true;
        } catch (e) {
          console.warn('face-api model source ' + (i + 1) + ' failed: ' + e.message);
        }
      }
      console.error('all face-api model sources failed; face detection unavailable');
      updateDiagnostics({ modelReady: false, status: 'model-load-failed', lastError: 'model-load-failed' });
      return false;
    })();
    return loadingPromise;
  }

  async function detect(videoElement) {
    if (!videoElement || videoElement.readyState < 2) {
      updateDiagnostics({ status: 'waiting-video', faceDetected: false });
      return null;
    }

    try {
      let faceReady = modelsLoaded;
      if (!faceReady) faceReady = await loadModels();
      if (faceReady && (!faceapi.nets.tinyFaceDetector || !faceapi.nets.tinyFaceDetector.isLoaded)) {
        modelsLoaded = false;
        faceReady = await loadModels();
      }

      let result = null;
      const poseMicro = await estimatePose(videoElement);
      const faceMeshMicro = await estimateFaceMesh(videoElement);
      if (faceReady && faceapi.nets.tinyFaceDetector && faceapi.nets.tinyFaceDetector.isLoaded) {
        const options = new faceapi.TinyFaceDetectorOptions({ inputSize: 416, scoreThreshold: 0.25 });
        const faceDetection = await detectFaceResult(videoElement, options);
        result = faceDetection.result;
        diagnostics.faceCropUsed = !!faceDetection.cropUsed;
      }

      const expressions = result && result.expressions ? result.expressions : {};
      const topEmotion = Object.entries(expressions).sort(function(a, b) { return b[1] - a[1]; })[0] || ['neutral', 0];
      let faceMicro = result ? analyzeFaceGeometry(expressions, result.landmarks) : {};
      faceMicro = mergeMicro(faceMicro, faceMeshMicro);
      let micro = smoothMicro(mergePoseMicro(faceMicro, poseMicro));
      const hasFaceSignal = !!(result || faceMeshMicro);

      if (!hasFaceSignal && !poseMicro) {
        diagnostics.noFaceCount += 1;
        updateDiagnostics(Object.assign({
          status: faceReady ? 'no-face-no-pose' : 'models-unavailable',
          faceDetected: false,
          poseDetected: false,
          detectionSource: 'no-face',
          videoSize: (videoElement.videoWidth || 0) + 'x' + (videoElement.videoHeight || 0),
          faceCropUsed: !!diagnostics.faceCropUsed,
          faceMeshDetected: false,
          faceMeshCropUsed: !!diagnostics.faceMeshCropUsed,
          lastError: diagnostics.lastError
        }, metricDiagnostics(micro)));
        return { emotion: '\u6b63\u5e38', confidence: 0, expressions: {}, micro: micro, facesDetected: 0 };
      }

      if (!hasFaceSignal) diagnostics.noFaceCount += 1;
      const status = hasFaceSignal && micro.poseDetected ? 'detecting' : (hasFaceSignal ? 'face-detail-only' : 'pose-only');
      updateDiagnostics(Object.assign({
        status: status,
        faceDetected: hasFaceSignal,
        poseDetected: !!micro.poseDetected,
        detectionSource: micro.detectionSource || (poseMicro ? 'pose-only' : 'facemesh'),
        videoSize: (videoElement.videoWidth || 0) + 'x' + (videoElement.videoHeight || 0),
        faceCropUsed: !!diagnostics.faceCropUsed,
        faceMeshDetected: !!faceMeshMicro,
        faceMeshCropUsed: !!diagnostics.faceMeshCropUsed,
        lastError: (hasFaceSignal || micro.poseDetected) ? '' : diagnostics.lastError
      }, metricDiagnostics(micro)));

      return {
        emotion: EMOTION_MAP[topEmotion[0]] || '\u6b63\u5e38',
        confidence: result ? Math.round((topEmotion[1] || 0) * 100) : 0,
        expressions: expressions,
        micro: micro,
        facesDetected: hasFaceSignal ? 1 : 0,
        landmarks: result ? result.landmarks : null,
        faceMeshLandmarks: lastFaceMeshLandmarks
      };
    } catch (e) {
      diagnostics.failCount += 1;
      updateDiagnostics({ status: 'detect-error', lastError: e && e.message ? e.message : 'detect-error' });
      console.warn('face/pose detection error', e.message);
      return null;
    }
  }

  function drawOverlay(canvas, video, detection) {
    if (!canvas || !detection) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const width = video.videoWidth || 320;
    const height = video.videoHeight || 240;
    canvas.width = width;
    canvas.height = height;
    ctx.clearRect(0, 0, width, height);

    if (detection.landmarks && window.faceapi) {
      faceapi.draw.drawFaceLandmarks(canvas, detection.landmarks);
    }
    if (detection.faceMeshLandmarks && detection.faceMeshLandmarks.length) {
      ctx.fillStyle = 'rgba(56,189,248,0.78)';
      [33, 133, 263, 362, 55, 65, 285, 295, 468, 473].forEach(function(index) {
        const point = detection.faceMeshLandmarks[index];
        if (!point) return;
        ctx.beginPath();
        ctx.arc(point.x * width, point.y * height, 2.2, 0, Math.PI * 2);
        ctx.fill();
      });
    }

    // \u8bf4\u660e\uff1a\u5fae\u8868\u60c5/\u59ff\u6001\u7b49\u68c0\u6d4b\u6570\u636e\u5df2\u5728\u53f3\u4fa7\u300c\u5b9e\u65f6\u60c5\u7eea\u611f\u77e5\u300d\u9762\u677f\u7edf\u4e00\u5c55\u793a\uff0c
    // \u8fd9\u91cc\u4e0d\u518d\u5728\u753b\u9762\u5de6\u4e0a\u89d2\u91cd\u590d\u7ed8\u5236\uff0c\u907f\u514d\u4e24\u5904\u6570\u636e\u663e\u793a\u4e0d\u4e00\u81f4\u3002
  }

  return {
    loadModels: loadModels,
    detect: detect,
    drawOverlay: drawOverlay,
    isReady: function() { return modelsLoaded; },
    getDiagnostics: function() { return Object.assign({}, diagnostics); },
    EMOTION_MAP: EMOTION_MAP
  };
})();
