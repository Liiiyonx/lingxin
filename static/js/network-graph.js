/**
 * 聆心 — 情绪网络图（Awwwards 级 Canvas 力导向图）
 *
 * 结构：中心(辅导员/全校) → 情绪分支 → 学生节点（按严重程度着色）
 *
 * 特性：
 *   - 60fps rAF 渲染：锚点弹簧 + 同组斥力 + 节点漂浮，运动柔和自然
 *   - 相机系统：滚轮缩放（指向指针）、拖拽平移、双击复位，带缓动过渡
 *   - 流动粒子：沿边巡游的光点，中心 → 情绪 → 学生 方向流动
 *   - 入场编排：节点自中心错峰绽放；数据刷新时旧节点平滑迁移不重置
 *   - 交互：悬停高亮邻居并弹出信息卡片、拖拽回弹、点击学生跳转对话、
 *     点击情绪分支聚焦/取消聚焦、搜索定位学生（脉冲标记 + 自动飞行）
 *   - 待跟进模式：仅渲染高/中风险学生，一屏看清需要跟进的对象
 *   - 深色/浅色主题自适应，DPR 高清渲染
 *
 * 用法：
 *   const g = EmotionNetworkGraph.create(canvas, {
 *     dark: false,
 *     onStudentClick: (student) => {},
 *     onHover: (info|null) => {},        // info: {node, x, y} 屏幕坐标，供 HTML 卡片定位
 *     onVisibleChange: (n) => {},        // 当前可见学生数（供空态提示）
 *   });
 *   g.setData(data);                     // data 来自 /api/network/emotion-graph
 *   g.setSeverityFilter(['high','medium','low']);
 *   g.setFollowUpMode(false);
 *   g.setSearchQuery('张三');
 *   g.focusEmotion('焦虑');  g.focusEmotion(null);
 *   g.zoomIn(); g.zoomOut(); g.resetView();
 *   g.setTheme(true); g.resize(); g.destroy();
 */
window.EmotionNetworkGraph = (function() {
  'use strict';

  var RISK_COLOR = { high: '#ef4444', medium: '#f59e0b', low: '#10b981' };
  var RISK_LABEL = { high: '高风险', medium: '中风险', low: '低风险' };
  var TWO_PI = Math.PI * 2;

  function hexToRgba(hex, a) {
    hex = (hex || '#94a3b8').replace('#', '');
    if (hex.length === 3) hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
    var n = parseInt(hex, 16);
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
  }
  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }
  function easeOutCubic(p) { return 1 - Math.pow(1 - p, 3); }

  function create(canvas, opts) {
    opts = opts || {};
    var ctx = canvas.getContext('2d');
    var W = 0, H = 0, dpr = 1;
    var rafId = null;
    var running = false;
    var lastT = 0;
    var now = 0;

    var dark = !!opts.dark;
    var clusterMode = opts.clusterMode || 'auto';
    var clusterBy = opts.clusterBy || 'class';
    if (['off', 'auto', 'force'].indexOf(clusterMode) < 0) clusterMode = 'auto';
    if (['class', 'college'].indexOf(clusterBy) < 0) clusterBy = 'class';
    var data = null;
    var nodes = [];
    var links = [];
    var particles = [];
    var severityFilter = ['high', 'medium', 'low'];
    var followUpMode = false;
    var searchQuery = '';
    var focusedEmotion = null;
    var focusedCluster = null;

    var hoverNode = null;
    var dragNode = null;
    var panning = false;
    var panMoved = false;
    var downX = 0, downY = 0;
    var pointer = { x: -9999, y: -9999 };

    // 相机：世界坐标 → 屏幕  sx = (wx - cam.x) * cam.z + W/2
    var cam = { x: 0, y: 0, z: 1, tx: 0, ty: 0, tz: 1, anim: false };

    var onStudentClick = opts.onStudentClick || function() {};
    var onHover = opts.onHover || function() {};
    var onVisibleChange = opts.onVisibleChange || function() {};
    var visibleStudentCount = 0;

    var ROOT_R = 44;

    /* ── 主题 ─────────────────────────────────────────── */
    function theme() {
      return dark ? {
        bg0: '#0b1120', bg1: '#111a2e',
        gridDot: 'rgba(148,163,184,0.10)',
        rootFill1: '#6366f1', rootFill2: '#a855f7',
        rootText: '#ffffff',
        emotionText: '#e2e8f0', studentText: '#cbd5e1', mutedText: '#64748b',
        edgeRoot: 'rgba(129,140,248,0.35)',
        vignette: 'rgba(3,7,18,0.55)'
      } : {
        bg0: '#f1f5fb', bg1: '#e8eef8',
        gridDot: 'rgba(100,116,139,0.13)',
        rootFill1: '#6366f1', rootFill2: '#8b5cf6',
        rootText: '#ffffff',
        emotionText: '#334155', studentText: '#475569', mutedText: '#94a3b8',
        edgeRoot: 'rgba(99,102,241,0.30)',
        vignette: 'rgba(148,163,184,0.16)'
      };
    }

    /* ── 尺寸 ─────────────────────────────────────────── */
    function resize() {
      var parent = canvas.parentElement;
      if (!parent) return;
      var rect = parent.getBoundingClientRect();
      dpr = window.devicePixelRatio || 1;
      W = Math.max(280, rect.width);
      H = Math.max(360, rect.height);
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
      canvas.style.width = W + 'px';
      canvas.style.height = H + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (data) layout();
    }

    /* ── 布局：世界坐标锚点 ───────────────────────────── */
    function layout() {
      var visibleGroups = nodes.filter(function(n) { return n.kind === 'emotion'; });
      var spread = Math.min(W, H);
      var R1 = spread * (visibleGroups.length > 8 ? 0.40 : 0.34);
      nodes.forEach(function(n) {
        if (n.kind === 'root') { n.ax = 0; n.ay = 0; return; }
        if (n.kind === 'emotion') {
          var ang = n._angle - Math.PI / 2;
          n.ax = Math.cos(ang) * R1;
          n.ay = Math.sin(ang) * R1;
          return;
        }
        if (n.kind === 'cluster') {
          var parentEmo = n._parent;
          var cCount = n._siblings;
          var perRingC = Math.max(2, Math.min(5, Math.ceil(cCount / 2)));
          var ringC = Math.floor(n._index / perRingC);
          var idxC = n._index % perRingC;
          var ringCountC = Math.min(perRingC, cCount - ringC * perRingC);
          var RCluster = (parentEmo.r || 26) + 38 + ringC * 34 + Math.min(24, cCount * 1.2);
          var angC = (idxC / Math.max(1, ringCountC)) * TWO_PI + parentEmo._angle + ringC * 0.28;
          n.ax = parentEmo.ax + Math.cos(angC) * RCluster;
          n.ay = parentEmo.ay + Math.sin(angC) * RCluster;
          return;
        }
        // 学生：围绕所属情绪节点排成 1~2 圈
        var parent = n._parent;
        var cnt = n._siblings;
        var perRing = Math.max(8, Math.min(14, Math.ceil(cnt / 2)));
        var ring = Math.floor(n._index / perRing);
        var idxInRing = n._index % perRing;
        var ringCnt = Math.min(perRing, cnt - ring * perRing);
        var baseR = parent.kind === 'cluster' ? 18 : 26;
        var R2 = (parent.r || baseR) + (parent.kind === 'cluster' ? 24 : 34) + ring * 30 + Math.min(26, cnt * 0.6);
        var ang2 = (idxInRing / Math.max(1, ringCnt)) * TWO_PI + (parent._angle || 0) + ring * 0.35;
        n.ax = parent.ax + Math.cos(ang2) * R2;
        n.ay = parent.ay + Math.sin(ang2) * R2;
      });
    }

    /* ── 数据 → 图 ────────────────────────────────────── */
    function rebuild() {
      nodes = [];
      links = [];
      if (!data || !data.groups) { visibleStudentCount = 0; onVisibleChange(0); return; }

      var root = {
        id: 'root', kind: 'root',
        label: (data.root && data.root.name) || '辅导员',
        sub: (data.root && data.root.college) || '',
        r: ROOT_R,
        x: 0, y: 0, ax: 0, ay: 0, vx: 0, vy: 0,
        progress: 1, spawnX: 0, spawnY: 0
      };
      nodes.push(root);

      var effFilter = followUpMode ? severityFilter.filter(function(s) { return s !== 'low'; }) : severityFilter;
      var vCount = 0;

      var visGroups = data.groups.map(function(g) {
        var students = g.students.filter(function(s) { return effFilter.indexOf(s.risk_level) >= 0; });
        return { g: g, students: students };
      }).filter(function(x) { return x.students.length > 0; });

      var visibleTotal = visGroups.reduce(function(total, x) { return total + x.students.length; }, 0);
      var useClusters = clusterMode === 'force' || (clusterMode !== 'off' && (visibleTotal > 120 || ((data.stats && data.stats.total) > 120)));

      visGroups.forEach(function(x, gi) {
        var g = x.g;
        var angle = (gi / Math.max(1, visGroups.length)) * TWO_PI;
        var emoNode = {
          id: 'emotion_' + g.emotion, kind: 'emotion',
          emotion: g.emotion, icon: g.icon || '🙂', color: g.color || '#94a3b8',
          count: x.students.length, totalCount: g.count,
          highCount: g.high || 0, mediumCount: g.medium || 0,
          _angle: angle,
          r: 24 + Math.min(16, x.students.length * 1.1),
          x: 0, y: 0, ax: 0, ay: 0, vx: 0, vy: 0,
          progress: 0, spawnX: 0, spawnY: 0
        };
        nodes.push(emoNode);
        links.push({ source: root, target: emoNode, type: 'root' });

        if (useClusters) {
          var clusterMap = {};
          x.students.forEach(function(s) {
            var label = clusterBy === 'college'
              ? (s.college || s.class_name || '未分学院')
              : (s.class_name || s.college || '未分班');
            if (!clusterMap[label]) {
              clusterMap[label] = {
                id: 'cluster_' + encodeURIComponent(g.emotion + '_' + label),
                kind: 'cluster',
                label: label,
                _parent: emoNode,
                students: [],
                count: 0,
                high: 0,
                medium: 0,
                low: 0
              };
            }
            var c = clusterMap[label];
            c.students.push(s);
            c.count++;
            c[s.risk_level] = (c[s.risk_level] || 0) + 1;
          });

          var clusterNodes = Object.keys(clusterMap).map(function(label) { return clusterMap[label]; });
          clusterNodes.forEach(function(c, ci) {
            c._index = ci;
            c._siblings = clusterNodes.length;
            c.r = 15 + Math.min(14, c.count * 0.55);
            c.x = 0; c.y = 0; c.ax = 0; c.ay = 0; c.vx = 0; c.vy = 0;
            c.progress = 0; c.spawnX = 0; c.spawnY = 0;
            nodes.push(c);
            links.push({ source: emoNode, target: c, type: 'cluster' });

            c.students.forEach(function(s, si) {
              vCount++;
              var sn = makeStudentNode(s, si, c);
              nodes.push(sn);
              links.push({ source: c, target: sn, type: 'student' });
            });
          });
        } else {
          x.students.forEach(function(s, si) {
            vCount++;
            var sn = makeStudentNode(s, si, emoNode);
            nodes.push(sn);
            links.push({ source: emoNode, target: sn, type: 'student' });
          });
        }
      });

      layout();
      buildParticles();
      seedMissingNodes();
      if (vCount !== visibleStudentCount) { visibleStudentCount = vCount; onVisibleChange(vCount); }
    }

    function seedMissingNodes() {
      var t0 = now || performance.now();
      nodes.forEach(function(n) {
        if (n.kind === 'root' || n._enterStart !== undefined || n.progress === 1) return;
        n.progress = 0;
        n._enterStart = t0 + (n.kind === 'emotion' ? 0 : 100 + (n._index || 0) * 26);
        n.spawnX = n._parent ? n._parent.ax : 0;
        n.spawnY = n._parent ? n._parent.ay : 0;
        n.x = n.spawnX;
        n.y = n.spawnY;
      });
    }

    function makeStudentNode(s, si, parent) {
      return {
        id: 'student_' + s.db_id, kind: 'student',
        student: s,
        risk: s.risk_level,
        name: s.name,
        student_no: s.student_no,
        class_name: s.class_name || '',
        college: s.college || '',
        _parent: parent,
        _index: si,
        _siblings: parent.students ? parent.students.length : (parent.count || 0),
        r: 5.5 + (s.risk_level === 'high' ? 2.5 : s.risk_level === 'medium' ? 1.5 : 0.5),
        x: 0, y: 0, ax: 0, ay: 0, vx: 0, vy: 0,
        progress: 0, spawnX: 0, spawnY: 0,
        phase: (si * 0.73) % TWO_PI,
        drift: 2 + (si % 3)
      };
    }

    /* ── 流动粒子 ─────────────────────────────────────── */
    function buildParticles() {
      particles = [];
      var rootLinks = links.filter(function(l) { return l.type === 'root'; });
      var studentLinks = links.filter(function(l) { return l.type === 'student'; });
      var maxP = nodes.length > 250 ? 60 : 110;
      rootLinks.forEach(function(l) {
        var n = clamp(Math.round(l.target.count / 6) + 1, 1, 4);
        for (var i = 0; i < n; i++) {
          particles.push({ link: l, t: Math.random(), speed: 0.10 + Math.random() * 0.10, size: 1.6 + Math.random() * 1.4, kind: 'root' });
        }
      });
      studentLinks.forEach(function(l) {
        if (Math.random() < (nodes.length > 250 ? 0.15 : 0.35)) {
          particles.push({ link: l, t: Math.random(), speed: 0.14 + Math.random() * 0.16, size: 1.2 + Math.random() * 1.1, kind: 'student' });
        }
      });
      if (particles.length > maxP) particles = particles.slice(0, maxP);
    }

    /* ── 对外：数据 ───────────────────────────────────── */
    function setData(d) {
      var prev = {};
      nodes.forEach(function(n) { prev[n.id] = { x: n.x, y: n.y }; });
      var isFirst = !data;
      data = d;
      rebuild();
      var t0 = now || performance.now();
      nodes.forEach(function(n) {
        if (n.kind === 'root') { n.progress = 1; return; }
        if (isFirst) {
          n.progress = 0;
          n._enterStart = t0 + (n.kind === 'emotion' ? 0 : 100 + (n._index || 0) * 26);
          n.spawnX = 0; n.spawnY = 0;
          n.x = 0; n.y = 0;
        } else if (prev[n.id]) {
          n.x = prev[n.id].x; n.y = prev[n.id].y;
          n.progress = 1;
        } else {
          n.progress = 0;
          n._enterStart = t0;
          n.spawnX = n._parent ? n._parent.ax : 0;
          n.spawnY = n._parent ? n._parent.ay : 0;
          n.x = n.spawnX; n.y = n.spawnY;
        }
      });
      if (!running) start();
    }

    function setSeverityFilter(arr) {
      severityFilter = (arr && arr.length) ? arr : ['high', 'medium', 'low'];
      if (data) { rebuild(); }
    }
    function setFollowUpMode(on) {
      followUpMode = !!on;
      if (data) { rebuild(); }
    }
    function setClusterMode(mode) {
      if (['off', 'auto', 'force'].indexOf(mode) < 0) return;
      clusterMode = mode;
      if (data) { rebuild(); }
    }
    function setClusterBy(by) {
      if (['class', 'college'].indexOf(by) < 0) return;
      clusterBy = by;
      if (data) { rebuild(); }
    }
    function setSearchQuery(q) {
      searchQuery = (q || '').trim();
    }
    function focusEmotion(emotion) {
      focusedEmotion = emotion || null;
    }
    function focusCluster(id) {
      focusedCluster = id || null;
      focusedEmotion = null;
    }
    function setTheme(d) { dark = !!d; }

    /* ── 相机控制 ─────────────────────────────────────── */
    function zoomAt(factor, px, py) {
      var p = (px === undefined) ? { x: W / 2, y: H / 2 } : { x: px, y: py };
      var wx = (p.x - W / 2) / cam.tz + cam.tx;
      var wy = (p.y - H / 2) / cam.tz + cam.ty;
      cam.tz = clamp(cam.tz * factor, 0.35, 3);
      cam.tx = wx - (p.x - W / 2) / cam.tz;
      cam.ty = wy - (p.y - H / 2) / cam.tz;
      cam.anim = true;
    }
    function zoomIn() { zoomAt(1.28); }
    function zoomOut() { zoomAt(1 / 1.28); }
    function resetView() {
      cam.tx = 0; cam.ty = 0; cam.tz = 1; cam.anim = true;
    }
    function flyTo(wx, wy, z) {
      cam.tx = wx; cam.ty = wy; cam.tz = z || 1.4; cam.anim = true;
    }
    function locateFirstMatch() {
      if (!searchQuery) return false;
      var q = searchQuery.toLowerCase();
      var m = nodes.find(function(n) {
        return n.kind === 'student' && (n.name.toLowerCase().indexOf(q) >= 0 || String(n.student_no).toLowerCase().indexOf(q) >= 0);
      });
      if (m) { flyTo(m.ax, m.ay, 1.6); return true; }
      return false;
    }

    /* ── 坐标变换 ─────────────────────────────────────── */
    function w2sx(wx) { return (wx - cam.x) * cam.z + W / 2; }
    function w2sy(wy) { return (wy - cam.y) * cam.z + H / 2; }
    function s2wx(sx) { return (sx - W / 2) / cam.z + cam.x; }
    function s2wy(sy) { return (sy - H / 2) / cam.z + cam.y; }

    /* ── 物理 ─────────────────────────────────────────── */
    function step(dt) {
      // 相机缓动
      if (cam.anim) {
        var ck = 0.12;
        cam.x += (cam.tx - cam.x) * ck;
        cam.y += (cam.ty - cam.y) * ck;
        cam.z += (cam.tz - cam.z) * ck;
        if (Math.abs(cam.tx - cam.x) < 0.3 && Math.abs(cam.ty - cam.y) < 0.3 && Math.abs(cam.tz - cam.z) < 0.002) {
          cam.x = cam.tx; cam.y = cam.ty; cam.z = cam.tz; cam.anim = false;
        }
      }

      var k = 0.055;
      var repel = 900;
      var minDist = 20;
      var i, j, n, m;

      for (i = 0; i < nodes.length; i++) {
        n = nodes[i];
        if (n === dragNode) {
          n.x += (s2wx(pointer.x) - n.x) * 0.45;
          n.y += (s2wy(pointer.y) - n.y) * 0.45;
          n.vx = 0; n.vy = 0;
          continue;
        }
        // 入场期间由进度驱动
        if (n.progress < 1) {
          var p = clamp((now - n._enterStart) / 750, 0, 1);
          n.progress = easeOutCubic(p);
          n.x = n.spawnX + (n.ax - n.spawnX) * n.progress;
          n.y = n.spawnY + (n.ay - n.spawnY) * n.progress;
          continue;
        }
        n.vx += (n.ax - n.x) * k * dt * 60;
        n.vy += (n.ay - n.y) * k * dt * 60;
        // 漂浮
        if (n.kind === 'student') {
          n.vx += Math.cos(now / 1500 + n.phase) * 0.008 * n.drift * dt * 60;
          n.vy += Math.sin(now / 1700 + n.phase * 1.3) * 0.008 * n.drift * dt * 60;
        }
        // 同组学生间斥力
        if (n.kind === 'student') {
          for (j = i + 1; j < nodes.length; j++) {
            m = nodes[j];
            if (m.kind !== 'student' || m._parent !== n._parent) continue;
            var dx = m.x - n.x, dy = m.y - n.y;
            var d2 = dx * dx + dy * dy;
            if (d2 < minDist * minDist && d2 > 0.01) {
              var d = Math.sqrt(d2);
              var f = repel / d2 * dt;
              n.vx -= (dx / d) * f; n.vy -= (dy / d) * f;
              m.vx += (dx / d) * f; m.vy += (dy / d) * f;
            }
          }
        }
        n.vx *= 0.88; n.vy *= 0.88;
        n.x += n.vx * dt * 60;
        n.y += n.vy * dt * 60;
      }

      // 粒子
      for (i = 0; i < particles.length; i++) {
        var pt = particles[i];
        pt.t += pt.speed * dt;
        if (pt.t >= 1) pt.t -= 1;
      }
    }

    /* ── 绘制 ─────────────────────────────────────────── */
    function drawBackground(t) {
      var g = ctx.createLinearGradient(0, 0, 0, H);
      g.addColorStop(0, t.bg0);
      g.addColorStop(1, t.bg1);
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, W, H);

      // 点阵背景（随相机微移，营造纵深）
      var gap = 34 * cam.z;
      if (gap > 12 && gap < 200) {
        var offX = ((-cam.x * cam.z) % gap + gap) % gap;
        var offY = ((-cam.y * cam.z) % gap + gap) % gap;
        ctx.fillStyle = t.gridDot;
        for (var x = offX; x < W; x += gap) {
          for (var y = offY; y < H; y += gap) {
            ctx.fillRect(x, y, 1.4, 1.4);
          }
        }
      }
      // 中心柔光
      var rg = ctx.createRadialGradient(W / 2, H / 2, 10, W / 2, H / 2, Math.max(W, H) * 0.62);
      rg.addColorStop(0, dark ? 'rgba(99,102,241,0.12)' : 'rgba(99,102,241,0.08)');
      rg.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = rg;
      ctx.fillRect(0, 0, W, H);
    }

    function edgeDimmed(l) {
      if (focusedCluster) {
        var fc = nodes.find(function(n) { return n.id === focusedCluster; });
        if (!fc) return false;
        return !(
          l.source === fc || l.target === fc ||
          l.source === fc._parent || l.target === fc._parent
        );
      }
      if (focusedEmotion) {
        var emo = (l.source.kind === 'emotion' ? l.source : l.target.kind === 'emotion' ? l.target : null);
        if (emo && emo.emotion !== focusedEmotion) return true;
        if (l.source.kind === 'root' && l.target.kind === 'emotion' && l.target.emotion !== focusedEmotion) return true;
      }
      if (hoverNode) {
        return !(l.source === hoverNode || l.target === hoverNode);
      }
      return false;
    }

    function drawEdge(l, t) {
      var a = l.source, b = l.target;
      var x1 = w2sx(a.x), y1 = w2sy(a.y);
      var x2 = w2sx(b.x), y2 = w2sy(b.y);
      if (!Number.isFinite(x1) || !Number.isFinite(y1) || !Number.isFinite(x2) || !Number.isFinite(y2)) {
        return;
      }
      var dim = edgeDimmed(l);
      var isRoot = l.type === 'root';

      ctx.save();
      if (dim) ctx.globalAlpha = 0.08;
      if (isRoot) {
        // 渐变曲线
        var midX = (x1 + x2) / 2, midY = (y1 + y2) / 2;
        var cx = midX + (y2 - y1) * 0.12, cy = midY - (x2 - x1) * 0.12;
        var grad = ctx.createLinearGradient(x1, y1, x2, y2);
        grad.addColorStop(0, t.edgeRoot);
        grad.addColorStop(1, hexToRgba(b.color, dark ? 0.5 : 0.4));
        ctx.strokeStyle = grad;
        ctx.lineWidth = 1.5 * Math.sqrt(cam.z);
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.quadraticCurveTo(cx, cy, x2, y2);
        ctx.stroke();
        l._mid = { cx: cx, cy: cy };
      } else if (l.type === 'cluster') {
        var clusterColor = b._parent && b._parent.color ? b._parent.color : '#94a3b8';
        var hovered = hoverNode === b;
        ctx.strokeStyle = hexToRgba(clusterColor, hovered ? 0.75 : dark ? 0.38 : 0.34);
        ctx.lineWidth = (hovered ? 1.8 : 1.1) * Math.sqrt(cam.z);
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
        ctx.setLineDash([]);
      } else {
        var hover = hoverNode === b;
        ctx.strokeStyle = hexToRgba(RISK_COLOR[b.risk] || '#94a3b8', hover ? 0.65 : dark ? 0.22 : 0.30);
        ctx.lineWidth = (hover ? 1.8 : 1) * Math.sqrt(cam.z);
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }
      ctx.restore();
    }

    function drawParticles(t) {
      if (cam.z < 0.5) return;
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      for (var i = 0; i < particles.length; i++) {
        var p = particles[i];
        var a = p.link.source, b = p.link.target;
        if (edgeDimmed(p.link)) continue;
        var x, y;
        if (p.kind === 'root' && p.link._mid) {
          // 二次贝塞尔取点
          var x1 = w2sx(a.x), y1 = w2sy(a.y), x2 = w2sx(b.x), y2 = w2sy(b.y);
          var u = 1 - p.t;
          x = u * u * x1 + 2 * u * p.t * p.link._mid.cx + p.t * p.t * x2;
          y = u * u * y1 + 2 * u * p.t * p.link._mid.cy + p.t * p.t * y2;
        } else {
          x = w2sx(a.x + (b.x - a.x) * p.t);
          y = w2sy(a.y + (b.y - a.y) * p.t);
        }
        var fade = Math.sin(p.t * Math.PI);
        var col = p.kind === 'root' ? (b.color || '#818cf8') : (RISK_COLOR[b.risk] || '#94a3b8');
        ctx.fillStyle = hexToRgba(col, 0.75 * fade);
        ctx.beginPath();
        ctx.arc(x, y, p.size * cam.z, 0, TWO_PI);
        ctx.fill();
      }
      ctx.restore();
    }

    function nodeDimmed(n) {
      if (focusedCluster) {
        var fc = nodes.find(function(x) { return x.id === focusedCluster; });
        if (!fc) return false;
        if (n === fc || n === fc._parent) return false;
        if (n.kind === 'student' && n._parent === fc) return false;
        return true;
      }
      if (focusedEmotion) {
        if (n.kind === 'emotion' && n.emotion !== focusedEmotion) return true;
        if (n.kind === 'cluster' && n._parent.emotion !== focusedEmotion) return true;
        if (n.kind === 'student') {
          var emotion = n._parent.kind === 'cluster' ? n._parent._parent.emotion : n._parent.emotion;
          if (emotion !== focusedEmotion) return true;
        }
      }
      if (hoverNode) {
        if (n === hoverNode) return false;
        return !links.some(function(l) {
          return (l.source === hoverNode && l.target === n) || (l.target === hoverNode && l.source === n);
        });
      }
      return false;
    }

    function isSearchMatch(n) {
      if (!searchQuery || n.kind !== 'student') return false;
      var q = searchQuery.toLowerCase();
      return n.name.toLowerCase().indexOf(q) >= 0 || String(n.student_no).toLowerCase().indexOf(q) >= 0;
    }

    function drawNode(n, t) {
      var x = w2sx(n.x), y = w2sy(n.y);
      // 屏幕外剔除
      var margin = 90;
      if (x < -margin || x > W + margin || y < -margin || y > H + margin) return;

      var dim = nodeDimmed(n);
      var isHover = hoverNode === n;
      ctx.save();
      if (dim) ctx.globalAlpha = 0.12;
      if (n.progress < 1) ctx.globalAlpha = Math.min(dim ? 0.12 : 1, n.progress);

      if (n.kind === 'root') {
        var breathe = 1 + Math.sin(now / 1600) * 0.02;
        var r = n.r * breathe * Math.sqrt(cam.z);
        // 旋转虚线环
        ctx.save();
        ctx.strokeStyle = hexToRgba('#818cf8', 0.5);
        ctx.setLineDash([4, 7]);
        ctx.lineDashOffset = -now / 40;
        ctx.lineWidth = 1.4;
        ctx.beginPath(); ctx.arc(x, y, r + 9, 0, TWO_PI); ctx.stroke();
        ctx.restore();
        var g = ctx.createRadialGradient(x - r * 0.3, y - r * 0.3, r * 0.1, x, y, r);
        g.addColorStop(0, t.rootFill1);
        g.addColorStop(1, t.rootFill2);
        ctx.shadowColor = hexToRgba('#6366f1', 0.55);
        ctx.shadowBlur = 26;
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(x, y, r, 0, TWO_PI); ctx.fill();
        ctx.shadowBlur = 0;
        var fs = clamp(r * 0.3, 10, 15);
        ctx.fillStyle = t.rootText;
        ctx.font = '600 ' + fs + 'px Inter, "PingFang SC", "Microsoft YaHei", sans-serif';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(n.label, x, y - r * 0.12);
        if (n.sub) {
          ctx.font = (fs * 0.78) + 'px Inter, "PingFang SC", "Microsoft YaHei", sans-serif';
          ctx.fillStyle = hexToRgba('#ffffff', 0.82);
          ctx.fillText(n.sub, x, y + r * 0.35);
        }
        if (data && data.stats) {
          ctx.font = (fs * 0.78) + 'px Inter, "PingFang SC", "Microsoft YaHei", sans-serif';
          ctx.fillStyle = hexToRgba('#ffffff', 0.7);
          ctx.fillText(data.stats.total + ' 名学生', x, y + r + 20 * cam.z);
        }
      } else if (n.kind === 'emotion') {
        var breathe2 = 1 + Math.sin(now / 1400 + n._angle) * 0.03;
        var r2 = n.r * breathe2 * (isHover ? 1.12 : 1) * Math.sqrt(cam.z);
        // 光晕底
        ctx.fillStyle = hexToRgba(n.color, dark ? 0.16 : 0.14);
        ctx.beginPath(); ctx.arc(x, y, r2 * 1.45, 0, TWO_PI); ctx.fill();
        var g2 = ctx.createRadialGradient(x - r2 * 0.25, y - r2 * 0.3, r2 * 0.1, x, y, r2);
        g2.addColorStop(0, hexToRgba(n.color, 1));
        g2.addColorStop(1, hexToRgba(n.color, 0.75));
        ctx.shadowColor = hexToRgba(n.color, 0.45);
        ctx.shadowBlur = 18;
        ctx.fillStyle = g2;
        ctx.beginPath(); ctx.arc(x, y, r2, 0, TWO_PI); ctx.fill();
        ctx.shadowBlur = 0;
        // 高光
        ctx.fillStyle = hexToRgba('#ffffff', 0.22);
        ctx.beginPath(); ctx.arc(x - r2 * 0.22, y - r2 * 0.28, r2 * 0.4, 0, TWO_PI); ctx.fill();
        // emoji
        var efs = clamp(r2 * 0.6, 11, 26);
        ctx.font = efs + 'px sans-serif';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(n.icon, x, y + efs * 0.05);
        // 数量徽标
        var badgeR = clamp(r2 * 0.34, 8, 12);
        var bx = x + r2 * 0.78, by = y - r2 * 0.78;
        ctx.fillStyle = dark ? '#1e293b' : '#ffffff';
        ctx.strokeStyle = hexToRgba(n.color, 0.8);
        ctx.lineWidth = 1.4;
        ctx.beginPath(); ctx.arc(bx, by, badgeR, 0, TWO_PI); ctx.fill(); ctx.stroke();
        ctx.fillStyle = dark ? '#e2e8f0' : '#334155';
        ctx.font = '700 ' + badgeR + 'px Inter, sans-serif';
        ctx.fillText(String(n.count), bx, by + 0.5);
        // 标签
        if (cam.z > 0.45) {
          var lfs = clamp(11 * Math.sqrt(cam.z), 9, 13);
          ctx.font = '600 ' + lfs + 'px Inter, "PingFang SC", "Microsoft YaHei", sans-serif';
          ctx.fillStyle = t.emotionText;
          ctx.fillText(n.emotion, x, y + r2 + lfs + 4);
        }
      } else if (n.kind === 'cluster') {
        var rc = n.r * (isHover ? 1.12 : 1) * Math.sqrt(cam.z);
        var cText = n.label || '未分班';
        var cw = Math.max(54, rc * 2.2 + cText.length * 7);
        var ch = Math.max(22, rc * 1.35);
        var cColor = n._parent && n._parent.color ? n._parent.color : '#94a3b8';
        ctx.fillStyle = hexToRgba(cColor, dark ? 0.24 : 0.18);
        ctx.strokeStyle = hexToRgba(cColor, isHover ? 0.95 : dark ? 0.65 : 0.58);
        ctx.lineWidth = isHover ? 1.8 : 1.1;
        ctx.beginPath();
        if (ctx.roundRect) {
          ctx.roundRect(x - cw / 2, y - ch / 2, cw, ch, Math.min(12, ch / 2));
        } else {
          ctx.rect(x - cw / 2, y - ch / 2, cw, ch);
        }
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = dark ? '#e2e8f0' : '#334155';
        ctx.font = '600 ' + clamp(11 * Math.sqrt(cam.z), 9, 12) + 'px Inter, "PingFang SC", "Microsoft YaHei", sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(cText, x, y - ch * 0.12);
        ctx.fillStyle = dark ? '#cbd5e1' : '#64748b';
        ctx.font = '600 10px Inter, sans-serif';
        ctx.fillText(String(n.count) + ' 人 · ' + (n.high || 0) + ' 高', x, y + ch * 0.16);
      } else {
        // 学生节点
        var high = n.risk === 'high';
        var matched = isSearchMatch(n);
        var pulse = high ? 1 + Math.sin(now / 340 + n.phase) * 0.2 : 1;
        var r3 = n.r * (isHover ? 1.6 : 1) * pulse * Math.sqrt(cam.z);
        var color = RISK_COLOR[n.risk] || RISK_COLOR.low;

        if (high || matched) {
          // 脉冲光环
          var haloR = r3 + 4 + Math.sin(now / 340 + n.phase) * 2;
          ctx.strokeStyle = hexToRgba(matched ? '#6366f1' : color, 0.4);
          ctx.lineWidth = 1.4;
          ctx.beginPath(); ctx.arc(x, y, haloR, 0, TWO_PI); ctx.stroke();
        }
        if (high || isHover) {
          ctx.shadowColor = hexToRgba(color, 0.7);
          ctx.shadowBlur = 12;
        }
        ctx.fillStyle = hexToRgba(color, high ? 0.95 : 0.9);
        ctx.beginPath(); ctx.arc(x, y, r3, 0, TWO_PI); ctx.fill();
        ctx.shadowBlur = 0;
        ctx.strokeStyle = hexToRgba('#ffffff', dark ? 0.25 : 0.65);
        ctx.lineWidth = 1.1;
        ctx.stroke();

        // 名字：高危 / 搜索命中 / 悬停 / 高倍缩放时显示
        var showLabel = isHover || high || matched || cam.z > 1.5;
        if (showLabel && cam.z > 0.5) {
          var sfs = clamp(10.5 * Math.sqrt(cam.z), 9, 12);
          ctx.font = '600 ' + sfs + 'px Inter, "PingFang SC", "Microsoft YaHei", sans-serif';
          ctx.fillStyle = matched ? '#6366f1' : t.studentText;
          ctx.fillText(n.name, x, y - r3 - sfs * 0.7);
        }
      }
      ctx.restore();
    }

    function render() {
      var t = theme();
      ctx.clearRect(0, 0, W, H);
      drawBackground(t);

      links.forEach(function(l) { drawEdge(l, t); });
      drawParticles(t);

      var order = { root: 0, emotion: 1, cluster: 2, student: 3 };
      var sorted = nodes.slice().sort(function(a, b) { return order[a.kind] - order[b.kind]; });
      sorted.forEach(function(n) { drawNode(n, t); });

      // 暗角
      var vg = ctx.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.42, W / 2, H / 2, Math.max(W, H) * 0.78);
      vg.addColorStop(0, 'rgba(0,0,0,0)');
      vg.addColorStop(1, t.vignette);
      ctx.fillStyle = vg;
      ctx.fillRect(0, 0, W, H);
    }

    function loop(ts) {
      if (!running) return;
      var dt = clamp((ts - lastT) / 1000, 0.001, 0.05);
      lastT = ts;
      now = ts;
      step(dt);
      render();
      rafId = requestAnimationFrame(loop);
    }
    function start() {
      if (running) return;
      running = true;
      lastT = performance.now();
      rafId = requestAnimationFrame(loop);
    }

    /* ── 命中检测 ─────────────────────────────────────── */
    function findNode(sx, sy) {
      // 学生优先（绘制在最上层），其次班级聚合、情绪分支
      var order = { student: 0, cluster: 1, emotion: 2, root: 3 };
      var sorted = nodes.slice().sort(function(a, b) { return order[a.kind] - order[b.kind]; });
      for (var i = 0; i < sorted.length; i++) {
        var n = sorted[i];
        var x = w2sx(n.x), y = w2sy(n.y);
        var r = (n.kind === 'root' ? n.r + 8 : n.kind === 'emotion' ? n.r + 10 : n.kind === 'cluster' ? n.r + 16 : Math.max(n.r + 7, 12)) * Math.sqrt(cam.z);
        var dx = sx - x, dy = sy - y;
        if (dx * dx + dy * dy <= r * r) return n;
      }
      return null;
    }
    function getPos(e) {
      var rect = canvas.getBoundingClientRect();
      return { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }
    function emitHover() {
      if (hoverNode && (hoverNode.kind === 'student' || hoverNode.kind === 'emotion' || hoverNode.kind === 'cluster')) {
        onHover({
          node: hoverNode,
          x: w2sx(hoverNode.x),
          y: w2sy(hoverNode.y)
        });
      } else {
        onHover(null);
      }
    }

    /* ── 事件 ─────────────────────────────────────────── */
    canvas.addEventListener('mousemove', function(e) {
      var p = getPos(e);
      var prevHover = hoverNode;
      if (panning) {
        var dx = p.x - pointer.x, dy = p.y - pointer.y;
        if (Math.abs(p.x - downX) + Math.abs(p.y - downY) > 4) panMoved = true;
        cam.x -= dx / cam.z; cam.y -= dy / cam.z;
        cam.tx = cam.x; cam.ty = cam.y; cam.anim = false;
      }
      pointer.x = p.x; pointer.y = p.y;
      if (!dragNode && !panning) hoverNode = findNode(p.x, p.y);
      if (prevHover !== hoverNode) emitHover();
      canvas.style.cursor = dragNode ? 'grabbing' : panning ? 'grabbing' : hoverNode ? 'pointer' : 'grab';
    });
    canvas.addEventListener('mousedown', function(e) {
      var p = getPos(e);
      downX = p.x; downY = p.y;
      var n = findNode(p.x, p.y);
      if (n && n.kind !== 'root') {
        dragNode = n;
      } else {
        panning = true;
        panMoved = false;
      }
      pointer.x = p.x; pointer.y = p.y;
    });
    window.addEventListener('mouseup', function() {
      if (dragNode) {
        var moved = Math.abs(pointer.x - downX) + Math.abs(pointer.y - downY) > 7;
        if (!moved) {
          if (dragNode.kind === 'student') onStudentClick(dragNode.student, dragNode);
          else if (dragNode.kind === 'emotion') {
            focusEmotion(focusedEmotion === dragNode.emotion ? null : dragNode.emotion);
          } else if (dragNode.kind === 'cluster') {
            focusCluster(focusedCluster === dragNode.id ? null : dragNode.id);
          }
        }
      } else if (panning && !panMoved) {
        // 点击空白：取消分支聚焦
        if (focusedEmotion) focusEmotion(null);
        if (focusedCluster) focusCluster(null);
      }
      dragNode = null;
      panning = false;
      emitHover();
    });
    canvas.addEventListener('mouseleave', function() {
      hoverNode = null;
      emitHover();
      pointer.x = -9999; pointer.y = -9999;
    });
    canvas.addEventListener('wheel', function(e) {
      e.preventDefault();
      var p = getPos(e);
      var factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      // 滚轮直接生效（无缓动更跟手）
      var wx = s2wx(p.x), wy = s2wy(p.y);
      cam.z = clamp(cam.z * factor, 0.35, 3);
      cam.x = wx - (p.x - W / 2) / cam.z;
      cam.y = wy - (p.y - H / 2) / cam.z;
      cam.tx = cam.x; cam.ty = cam.y; cam.tz = cam.z; cam.anim = false;
      emitHover();
    }, { passive: false });
    canvas.addEventListener('dblclick', function() { resetView(); });

    // 触屏
    var lastTouchDist = 0;
    canvas.addEventListener('touchstart', function(e) {
      if (e.touches.length === 2) {
        lastTouchDist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY);
        return;
      }
      var t0 = e.touches[0]; if (!t0) return;
      var p = getPos(t0);
      downX = p.x; downY = p.y;
      var n = findNode(p.x, p.y);
      if (n && n.kind !== 'root') dragNode = n; else { panning = true; panMoved = false; }
      pointer.x = p.x; pointer.y = p.y;
      e.preventDefault();
    }, { passive: false });
    canvas.addEventListener('touchmove', function(e) {
      if (e.touches.length === 2) {
        var d = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY);
        if (lastTouchDist > 0) {
          var cx = (e.touches[0].clientX + e.touches[1].clientX) / 2;
          var cy = (e.touches[0].clientY + e.touches[1].clientY) / 2;
          var rect = canvas.getBoundingClientRect();
          var p = { x: cx - rect.left, y: cy - rect.top };
          var wx = s2wx(p.x), wy = s2wy(p.y);
          cam.z = clamp(cam.z * (d / lastTouchDist), 0.35, 3);
          cam.x = wx - (p.x - W / 2) / cam.z;
          cam.y = wy - (p.y - H / 2) / cam.z;
          cam.tx = cam.x; cam.ty = cam.y; cam.tz = cam.z; cam.anim = false;
        }
        lastTouchDist = d;
        e.preventDefault();
        return;
      }
      var t0 = e.touches[0]; if (!t0) return;
      var p = getPos(t0);
      if (panning) {
        var dx = p.x - pointer.x, dy = p.y - pointer.y;
        cam.x -= dx / cam.z; cam.y -= dy / cam.z;
        cam.tx = cam.x; cam.ty = cam.y;
        panMoved = true;
      }
      pointer.x = p.x; pointer.y = p.y;
      e.preventDefault();
    }, { passive: false });
    canvas.addEventListener('touchend', function() {
      lastTouchDist = 0;
      if (dragNode) {
        var moved = Math.abs(pointer.x - downX) + Math.abs(pointer.y - downY) > 9;
        if (!moved && dragNode.kind === 'student') onStudentClick(dragNode.student, dragNode);
        else if (!moved && dragNode.kind === 'emotion') {
          focusEmotion(focusedEmotion === dragNode.emotion ? null : dragNode.emotion);
        } else if (!moved && dragNode.kind === 'cluster') {
          focusCluster(focusedCluster === dragNode.id ? null : dragNode.id);
        }
      } else if (panning && !panMoved) {
        if (focusedEmotion) focusEmotion(null);
        if (focusedCluster) focusCluster(null);
      }
      dragNode = null;
      panning = false;
    });

    function destroy() {
      running = false;
      if (rafId) cancelAnimationFrame(rafId);
      nodes = []; links = []; particles = [];
      onHover(null);
    }

    resize();
    start();

    return {
      setData: setData,
      setSeverityFilter: setSeverityFilter,
      setFollowUpMode: setFollowUpMode,
      setClusterMode: setClusterMode,
      setClusterBy: setClusterBy,
      setSearchQuery: setSearchQuery,
      locateFirstMatch: locateFirstMatch,
      focusEmotion: focusEmotion,
      focusCluster: focusCluster,
      setTheme: setTheme,
      zoomIn: zoomIn,
      zoomOut: zoomOut,
      resetView: resetView,
      resize: resize,
      destroy: destroy
    };
  }

  return { create: create, RISK_COLOR: RISK_COLOR, RISK_LABEL: RISK_LABEL };
})();
