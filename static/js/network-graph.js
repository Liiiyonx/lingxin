/**
 * 聆心 — 情绪网络图（自定义 Canvas 力导向图）
 *
 * 结构：中心(辅导员/全校) → 情绪分支 → 学生节点（按严重程度着色）
 * 特性：
 *   - 60fps requestAnimationFrame 渲染，锚点弹簧 + 柔和斥力，节点轻微浮动
 *   - 入场动画（节点从中心绽放）、高风险节点脉冲发光、悬停高亮邻居、拖拽回弹
 *   - 深色/浅色主题自适应，DPR 高清渲染，支持严重程度筛选
 *   - 点击学生节点回调 → 跳转师生对话
 *
 * 用法：
 *   const g = EmotionNetworkGraph.create(canvas, { onStudentClick: fn });
 *   g.setData(data);            // data 来自 /api/network/emotion-graph
 *   g.setSeverityFilter(['high','medium','low']);
 *   g.setTheme(true); g.resize(); g.destroy();
 */
window.EmotionNetworkGraph = (function() {
  'use strict';

  const RISK_COLOR = { high: '#ef4444', medium: '#f59e0b', low: '#10b981' };
  const RISK_LABEL = { high: '高风险', medium: '中风险', low: '低风险' };

  function hexToRgba(hex, a) {
    hex = (hex || '#94a3b8').replace('#', '');
    if (hex.length === 3) hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
    const n = parseInt(hex, 16);
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
  }

  function create(canvas, opts) {
    opts = opts || {};
    const ctx = canvas.getContext('2d');
    let W = 0, H = 0, dpr = 1;
    let rafId = null;
    let running = false;
    let lastT = 0;

    let dark = !!opts.dark;
    let data = null;
    let nodes = [];
    let links = [];
    let severityFilter = ['high', 'medium', 'low'];
    let hoverNode = null;
    let dragNode = null;
    let dragDX = 0, dragDY = 0;
    let pointer = { x: -9999, y: -9999 };
    let now = 0; // 每帧更新时间（毫秒），供动画使用

    const onStudentClick = opts.onStudentClick || function() {};

    // 布局常量
    const ROOT_R = 40;

    function theme() {
      return {
        bg: dark ? '#0f172a' : '#f8fafc',
        rootFill1: dark ? '#6366f1' : '#6366f1',
        rootFill2: dark ? '#a855f7' : '#8b5cf6',
        rootText: '#ffffff',
        emotionText: dark ? '#e2e8f0' : '#334155',
        studentText: dark ? '#cbd5e1' : '#475569',
        mutedText: dark ? '#64748b' : '#94a3b8',
        edgeRoot: dark ? 'rgba(148,163,184,0.28)' : 'rgba(148,163,184,0.35)',
        edgeStudent: dark ? 'rgba(148,163,184,0.18)' : 'rgba(148,163,184,0.25)',
      };
    }

    function resize() {
      const parent = canvas.parentElement;
      if (!parent) return;
      const rect = parent.getBoundingClientRect();
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

    // —— 布局：锚点计算 ——
    function layout() {
      const cx = W / 2, cy = H / 2;
      const R1 = Math.min(W, H) * 0.30; // 情绪分支环半径

      nodes.forEach(function(n) {
        if (n.kind === 'root') {
          n.ax = cx; n.ay = cy;
        } else if (n.kind === 'emotion') {
          const ang = n._angle - Math.PI / 2;
          n.ax = cx + Math.cos(ang) * R1;
          n.ay = cy + Math.sin(ang) * R1;
        } else {
          // 学生在所属情绪节点周围排成小圆环
          const parent = n._parent;
          const cnt = n._siblings;
          const R2 = 42 + Math.min(70, cnt * 9);
          const ang = (n._index / Math.max(1, cnt)) * Math.PI * 2 + n._parent._angle;
          n.ax = parent.ax + Math.cos(ang) * R2;
          n.ay = parent.ay + Math.sin(ang) * R2;
        }
      });
    }

    function rebuild() {
      nodes = [];
      links = [];
      if (!data || !data.groups) return;

      const root = {
        id: 'root', kind: 'root',
        label: (data.root && data.root.name) || '辅导员',
        sub: (data.root && data.root.college) || '',
        r: ROOT_R,
        x: W / 2, y: H / 2, ax: W / 2, ay: H / 2,
        vx: 0, vy: 0, progress: 1, spawnX: W / 2, spawnY: H / 2,
      };
      nodes.push(root);

      const visGroups = data.groups.filter(function(g) { return g.count > 0; });
      visGroups.forEach(function(g, gi) {
        const angle = (gi / Math.max(1, visGroups.length)) * Math.PI * 2;
        const emoNode = {
          id: 'emotion_' + g.emotion, kind: 'emotion',
          emotion: g.emotion, icon: g.icon || '🤔', color: g.color || '#94a3b8',
          count: g.count,
          _angle: angle,
          r: 22 + Math.min(14, g.count * 1.2),
          x: W / 2, y: H / 2, ax: W / 2, ay: H / 2,
          vx: 0, vy: 0, progress: 0, spawnX: W / 2, spawnY: H / 2,
        };
        nodes.push(emoNode);
        links.push({ source: root, target: emoNode, type: 'root' });

        const visibleStudents = g.students.filter(function(s) {
          return severityFilter.indexOf(s.risk_level) >= 0;
        });
        visibleStudents.forEach(function(s, si) {
          const sn = {
            id: 'student_' + s.db_id, kind: 'student',
            student: s,
            risk: s.risk_level,
            name: s.name,
            student_no: s.student_no,
            _parent: emoNode,
            _index: si,
            _siblings: visibleStudents.length,
            r: 5 + (s.risk_level === 'high' ? 3 : 2),
            x: W / 2, y: H / 2, ax: emoNode.ax, ay: emoNode.ay,
            vx: 0, vy: 0, progress: 0, spawnX: emoNode.ax, spawnY: emoNode.ay,
            phase: (si * 0.7) % (Math.PI * 2),
          };
          nodes.push(sn);
          links.push({ source: emoNode, target: sn, type: 'student' });
        });
      });
      layout();
    }

    // —— 数据与筛选 ——
    function setData(d) {
      // 记录旧节点位置，供刷新时平滑迁移（避免每 15s 轮询重新绽放）
      const prev = {};
      nodes.forEach(function(n) { prev[n.id] = { x: n.x, y: n.y }; });
      const isFirst = !data;
      data = d;
      rebuild();
      const t0 = performance.now();
      nodes.forEach(function(n) {
        if (n.kind === 'root') { n.progress = 1; return; }
        if (isFirst) {
          // 首次加载：从中心绽放入场
          n.progress = 0;
          n._enterStart = t0 + (n.kind === 'emotion' ? 0 : 60 + (n._index || 0) * 24);
          n.spawnX = W / 2; n.spawnY = H / 2;
          n.x = n.spawnX; n.y = n.spawnY;
        } else if (prev[n.id]) {
          // 刷新：保留旧位置，靠弹簧平滑迁移到新锚点
          n.x = prev[n.id].x; n.y = prev[n.id].y;
          n.progress = 1;
        } else {
          // 新出现的节点：从所属情绪分支弹出
          n.progress = 0;
          n._enterStart = t0;
          n.spawnX = n._parent ? n._parent.ax : W / 2;
          n.spawnY = n._parent ? n._parent.ay : H / 2;
          n.x = n.spawnX; n.y = n.spawnY;
        }
      });
      if (!running) { running = true; rafId = requestAnimationFrame(loop); }
    }

    function setSeverityFilter(arr) {
      severityFilter = arr || ['high', 'medium', 'low'];
      if (data) { rebuild(); layout(); }
    }

    function setTheme(d) { dark = !!d; }
    function setOnStudentClick(fn) { if (typeof fn === 'function') onStudentClickRef = fn; }
    let onStudentClickRef = onStudentClick;

    // —— 物理模拟 + 渲染 ——
    function step(dt) {
      const k = 0.045;          // 锚点弹簧
      const repel = 5200;       // 斥力强度
      const minDist = 26;

      // 弹簧 + 斥力
      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i];
        // 拖拽节点跟随鼠标
        if (n === dragNode) {
          n.x += (pointer.x - n.x) * 0.5;
          n.y += (pointer.y - n.y) * 0.5;
          n.vx = 0; n.vy = 0;
          continue;
        }
        n.vx += (n.ax - n.x) * k;
        n.vy += (n.ay - n.y) * k;
        // 斥力（仅学生节点之间，且只对较近的）
        for (let j = i + 1; j < nodes.length; j++) {
          const m = nodes[j];
          if (n.kind !== 'student' || m.kind !== 'student') continue;
          const dx = m.x - n.x, dy = m.y - n.y;
          const d2 = dx * dx + dy * dy;
          if (d2 < minDist * minDist && d2 > 0.01) {
            const d = Math.sqrt(d2);
            const f = repel / d2;
            const fx = (dx / d) * f * dt;
            const fy = (dy / d) * f * dt;
            n.vx -= fx; n.vy -= fy;
            m.vx += fx; m.vy += fy;
          }
        }
        n.vx *= 0.86; n.vy *= 0.86;
        n.x += n.vx * dt * 60;
        n.y += n.vy * dt * 60;
      }

      // 入场进度
      nodes.forEach(function(n) {
        if (n.progress < 1) {
          const elapsed = now - n._enterStart;
          const p = Math.min(1, Math.max(0, elapsed / 700));
          // ease-out cubic
          n.progress = 1 - Math.pow(1 - p, 3);
          if (n.progress >= 1) n.progress = 1;
          n.x = n.spawnX + (n.ax - n.spawnX) * n.progress;
          n.y = n.spawnY + (n.ay - n.spawnY) * n.progress;
        }
      });
    }

    function drawEdge(a, b, t) {
      const col = t.theme();
      const isRoot = a.kind === 'root' || b.kind === 'root';
      ctx.strokeStyle = isRoot ? col.edgeRoot : col.edgeStudent;
      ctx.lineWidth = isRoot ? 1.6 : 1.0;
      ctx.beginPath();
      if (isRoot) {
        const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
        ctx.moveTo(a.x, a.y);
        ctx.quadraticCurveTo(mx, my, b.x, b.y);
      } else {
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
      }
      ctx.stroke();
    }

    function drawNode(n, t) {
      const isHover = hoverNode === n;
      const focusDim = hoverNode && hoverNode !== n &&
        !(links.some(function(l) {
          return (l.source === hoverNode && l.target === n) || (l.target === hoverNode && l.source === n);
        }));

      if (focusDim) { ctx.globalAlpha = 0.18; }

      if (n.kind === 'root') {
        // 中心节点：渐变圆 + 光晕
        const g = ctx.createRadialGradient(n.x, n.y, 4, n.x, n.y, n.r + 10);
        g.addColorStop(0, t.theme().rootFill1);
        g.addColorStop(1, t.theme().rootFill2);
        ctx.save();
        ctx.shadowColor = hexToRgba('#6366f1', 0.55);
        ctx.shadowBlur = 26;
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
        ctx.fillStyle = t.theme().rootText;
        ctx.font = '600 14px Inter, "PingFang SC", "Microsoft YaHei", sans-serif';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(n.label, n.x, n.y - 6);
        ctx.font = '11px Inter, "PingFang SC", "Microsoft YaHei", sans-serif';
        ctx.fillStyle = hexToRgba('#ffffff', 0.8);
        if (n.sub) ctx.fillText(n.sub, n.x, n.y + 14);
        if (data && data.stats) {
          ctx.fillText(data.stats.total + ' 名学生', n.x, n.y + 30);
        }
      } else if (n.kind === 'emotion') {
        const breathe = 1 + Math.sin(now / 1400 + n._angle) * 0.03;
        const r = n.r * breathe * (isHover ? 1.14 : 1);
        ctx.save();
        ctx.shadowColor = hexToRgba(n.color, 0.45);
        ctx.shadowBlur = 16;
        ctx.fillStyle = hexToRgba(n.color, 0.9);
        ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
        // 内圈高光
        ctx.fillStyle = hexToRgba('#ffffff', 0.22);
        ctx.beginPath(); ctx.arc(n.x - r * 0.22, n.y - r * 0.25, r * 0.42, 0, Math.PI * 2); ctx.fill();
        ctx.font = (r * 0.62) + 'px sans-serif';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(n.icon, n.x, n.y);
        // 标签
        ctx.font = '600 12px Inter, "PingFang SC", "Microsoft YaHei", sans-serif';
        ctx.fillStyle = t.theme().emotionText;
        ctx.fillText(n.emotion + ' ' + n.count, n.x, n.y + r + 14);
      } else {
        // 学生节点
        const high = n.risk === 'high';
        const pulse = high ? 1 + Math.sin(now / 320 + n.phase) * 0.22 : 1;
        const r = n.r * (isHover ? 1.5 : 1) * pulse;
        const color = RISK_COLOR[n.risk] || RISK_COLOR.low;
        if (high) {
          ctx.save();
          ctx.shadowColor = hexToRgba(color, 0.75);
          ctx.shadowBlur = 16;
          ctx.fillStyle = hexToRgba(color, 0.95);
          ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, Math.PI * 2); ctx.fill();
          ctx.restore();
          // 外圈光环
          ctx.strokeStyle = hexToRgba(color, 0.35);
          ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.arc(n.x, n.y, r + 5 + Math.sin(now / 320 + n.phase) * 2, 0, Math.PI * 2); ctx.stroke();
        } else {
          ctx.fillStyle = hexToRgba(color, 0.92);
          ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, Math.PI * 2); ctx.fill();
          ctx.strokeStyle = hexToRgba('#ffffff', dark ? 0.25 : 0.6);
          ctx.lineWidth = 1.2;
          ctx.stroke();
        }
        // 姓名：高危常显，其余悬停显示
        if (isHover || high) {
          ctx.font = '600 11px Inter, "PingFang SC", "Microsoft YaHei", sans-serif';
          ctx.textAlign = 'center';
          ctx.fillStyle = t.theme().studentText;
          ctx.fillText(n.name, n.x, n.y - r - 8);
          ctx.font = '9px Inter, "PingFang SC", "Microsoft YaHei", sans-serif';
          ctx.fillStyle = t.theme().mutedText;
          ctx.fillText(n.student_no, n.x, n.y + r + 14);
        }
      }

      ctx.globalAlpha = 1;
    }

    function render() {
      const t = theme();
      ctx.clearRect(0, 0, W, H);
      // 背景微光
      ctx.fillStyle = t.bg;
      ctx.fillRect(0, 0, W, H);
      // 中心径向柔光
      const bg = ctx.createRadialGradient(W / 2, H / 2, 20, W / 2, H / 2, Math.max(W, H) * 0.6);
      bg.addColorStop(0, dark ? 'rgba(99,102,241,0.10)' : 'rgba(99,102,241,0.06)');
      bg.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, W, H);

      // 先画边
      links.forEach(function(l) { drawEdge(l.source, l.target, t); });
      // 再画节点（情绪分支优先，学生在其上）
      const order = { root: 0, emotion: 1, student: 2 };
      const sorted = nodes.slice().sort(function(a, b) { return order[a.kind] - order[b.kind]; });
      sorted.forEach(function(n) { drawNode(n, t); });
    }

    function loop(ts) {
      if (!running) return;
      const dt = Math.min(0.05, Math.max(0.001, (ts - lastT) / 1000));
      lastT = ts;
      now = ts;
      step(dt);
      render();
      rafId = requestAnimationFrame(loop);
    }

    // —— 交互 ——
    function findNode(x, y) {
      for (let i = nodes.length - 1; i >= 0; i--) {
        const n = nodes[i];
        const r = n.kind === 'root' ? n.r + 8 : n.kind === 'emotion' ? n.r + 10 : n.r + 12;
        const dx = x - n.x, dy = y - n.y;
        if (dx * dx + dy * dy <= r * r) return n;
      }
      return null;
    }

    function getPos(e) {
      const rect = canvas.getBoundingClientRect();
      return { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }

    canvas.addEventListener('mousemove', function(e) {
      const p = getPos(e);
      pointer.x = p.x; pointer.y = p.y;
      if (!dragNode) hoverNode = findNode(p.x, p.y);
      canvas.style.cursor = (dragNode || hoverNode) ? 'pointer' : 'default';
    });
    canvas.addEventListener('mousedown', function(e) {
      const p = getPos(e);
      const n = findNode(p.x, p.y);
      if (n && n.kind !== 'root') { dragNode = n; dragDX = p.x - n.x; dragDY = p.y - n.y; }
    });
    window.addEventListener('mouseup', function() {
      if (dragNode) {
        // 学生点击 → 跳转；仅当未发生明显拖拽
        const moved = Math.abs(dragNode.x - dragNode.ax) > 8 || Math.abs(dragNode.y - dragNode.ay) > 8;
        if (dragNode.kind === 'student' && !moved) {
          onStudentClickRef(dragNode.student, dragNode);
        }
      }
      dragNode = null;
    });
    // 触屏
    canvas.addEventListener('touchstart', function(e) {
      const t0 = e.touches[0]; if (!t0) return;
      const p = getPos(t0);
      const n = findNode(p.x, p.y);
      if (n && n.kind !== 'root') { dragNode = n; dragDX = p.x - n.x; dragDY = p.y - n.y; e.preventDefault(); }
    }, { passive: false });
    canvas.addEventListener('touchmove', function(e) {
      const t0 = e.touches[0]; if (!t0 || !dragNode) return;
      const p = getPos(t0);
      pointer.x = p.x; pointer.y = p.y;
      e.preventDefault();
    }, { passive: false });
    canvas.addEventListener('touchend', function() {
      if (dragNode && dragNode.kind === 'student') {
        const moved = Math.abs(dragNode.x - dragNode.ax) > 8 || Math.abs(dragNode.y - dragNode.ay) > 8;
        if (!moved) onStudentClickRef(dragNode.student, dragNode);
      }
      dragNode = null;
    });

    function destroy() {
      running = false;
      if (rafId) cancelAnimationFrame(rafId);
      nodes = []; links = [];
    }

    // 初始尺寸
    resize();
    if (!running) { running = true; lastT = performance.now(); rafId = requestAnimationFrame(loop); }

    return {
      setData: setData,
      setSeverityFilter: setSeverityFilter,
      setTheme: setTheme,
      setOnStudentClick: setOnStudentClick,
      resize: resize,
      destroy: destroy,
    };
  }

  return { create: create, RISK_COLOR: RISK_COLOR, RISK_LABEL: RISK_LABEL };
})();
