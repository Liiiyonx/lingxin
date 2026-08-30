# 视频通话声网（Agora）SDK 接入改造计划书

> 目标：把视频通话的「媒体传输层」从自建 WebRTC（RTCPeerConnection + 公共 STUN）替换为声网 Agora RTC SDK，从而**跨网 / 复杂 NAT 也能稳定打通视频**，同时**保留本项目核心的实时情绪分析 + 预警闭环**。
> 基线：`tag before-agora-integration`（commit `424ca1c`）—— 改造前存档，可随时回滚。
> 编写日期：2026-08-29

---

## 0.5 当前进度（2026-08-30 更新）

| 项 | 状态 |
|---|---|
| Agora Web SDK 4.22.2 本地化引入 | ✅ |
| 学生端 / 老师端声网 `join/publish/subscribe` 改造 | ✅ |
| 老师端订阅后情绪分析缝合 | ✅ |
| 后端 token 接口 `/api/video/agora-token` | ✅（支持临时 Token / App 证书生成 / 无鉴权三模式） |
| 前端 join 失败中文提示 | ✅（`dynamic use static key` 等错误会给出明确操作指引） |
| **声网控制台鉴权模式确认** | ✅ 项目 `16137f231ee34811bc8aa0381086dcbc` 为安全模式（`Primary certificate: Enabled`），控制台没有「关闭证书」开关；采用**临时 Token 接入** |
| 本地双端 E2E 打通 | ✅ 学生发起呼叫 → 老师接听 → 双方出画 → 实时情绪面板 → 挂断生成总结，`E2E_RESULT: PASS` |
| 当前接入方式 | 临时 Token（约 24 小时有效）写入 `.env` 的 `AGORA_TOKEN=`；前端频道固定为 `video_check` |
| 云服务器部署 | ✅ 2026-08-30 上线 `8.153.151.13`（HTTPS + nginx 反代 + systemd，公网 token/信令接口验证通过），详见 [云服务器部署计划书](云服务器部署计划书.md) 0.0 节 |

### 控制台需要做的（二选一）

> 现状（2026-08-30）：项目证书为启用状态且无关闭开关，当前演示已走**临时 Token** 方案，本地双端 E2E 通过。后续二选一：

1. **比赛演示（保持现状）**：临时 Token 过期前无需再动控制台；过期后在「Token 生成工具」重新生成临时 Token，填入 `.env` 的 `AGORA_TOKEN=` 并重启服务。
2. **正式接入**：把项目的 App 证书填入 `.env` 的 `AGORA_APP_CERT=`（服务端会自动签发 Token），前端可改回动态频道（当前 `video_check` 是配合临时 Token 的固定值）。

> 验证方式：访问 `http://127.0.0.1:5100/api/video/agora-token?channel=video_check&uid=20230035`，应返回 `"mode":"static_token"` 且真实 `"token":"007..."`。若返回 `dynamic use static key` 类错误，通常是临时 Token 过期或频道名与生成时不一致。

## 0. 一句话结论

**只换「媒体怎么传」，不碰「情绪怎么算」。** 改造集中在 `static/js/modules/video-call.js` 的传输层约 300 行，三个情绪核心文件（`face-detector.js` / `voice-analyzer.js` / `emotion-fusion.js`）与后端 `/emotion/*` 接口**零改动**。风险可控，最坏情况只影响视频通话功能本身。

---

## 1. 现状代码地图（精确到函数 / 行号）

### 1.1 前端 `static/js/modules/video-call.js`（961 行）

| 区域 | 函数 | 行号 | 改造动作 |
|---|---|---|---|
| 学生端信令 | `initStudentVideo` | 138 | **改**（删媒体信令监听，加订阅回调） |
| 学生端建连 | `createPeerConn` | 179 | **删**（换成声网 client） |
| 学生端协商 | `createOffer` / `createAnswer` | 197 / 204 | **删**（声网自动协商） |
| 学生端拨号 | `startVideoCall` | 222 | **改**（getUserMedia → 声网建轨 + join + publish） |
| 学生端挂断 | `endVideoCall` | 249 | **改**（加 `client.leave()`） |
| 学生端开关 | `toggleVideo` / `toggleAudio` | 261 / 264 | **改**（track.setEnabled） |
| 学生端接听/拒接 | `acceptStudentCall` / `rejectStudentCall` | 288 / 298 | 基本保留 |
| 老师端信令 | `initTeacherVideo` | 301 | **改**（同学生端） |
| 老师端拨号 | `startTeacherVideo` | 345 | **改**（声网建轨 + join + publish） |
| 老师端建连 | `createTeacherPeerConn` | 367 | **删**（换成声网 client） |
| 老师端协商 | `createTeacherOffer` / `createTeacherAnswer` | 386 / 393 | **删** |
| 老师端接听/拒接 | `acceptVideoCall` / `rejectVideoCall` | 400 / 414 | 基本保留 |
| 老师端挂断 | `endTeacherVideo` | 416 | **改**（加 `client.leave()`，保留情绪总结提交） |
| 老师端开关 | `toggleTeacherVideo` / `toggleTeacherAudio` | 429 / 432 | **改**（setEnabled） |
| 老师端发起 | `openTeacherVideo` | 436 | 基本保留 |
| **情绪分析（不动）** | `autoStartRealtimeEmotion` / `startRealtimeEmotion` | 765 / 774 | **保留** |
| **情绪分析（不动）** | `runFaceDetectionLoop` / `runVoiceAnalysisLoop` | 797 / 840 | **保留** |
| **情绪分析（不动）** | `fallbackServerDetection` / `startYolo` / `stopYolo` | 874 / 906 / 914 | **保留** |

### 1.2 关键耦合点（改造的「缝合线」）

情绪分析唯一依赖的，是拿到一个**远端 `MediaStream`**，然后喂给两个现有函数：

```js
// 现状：老师端 ontrack 里（video-call.js:378-383）
teacherPeerConn.ontrack = function(e) {
  attachRemoteStream(teacherRemoteVideo.value, e.streams[0]);       // 绑画面
  autoStartRealtimeEmotion(e.streams[0], teacherRemoteVideo.value); // 启动情绪分析
};
```

只要声网 SDK 拿到远端流后，**原样调用这两个函数**，情绪分析就无缝续接。这是整个改造的核心保证。

### 1.3 后端 `app.py` 信令事件

| Socket.IO 事件 | 行号 | 用途 | 改造动作 |
|---|---|---|---|
| `video_call_request` | 77 | 呼叫请求（广播） | **保留** |
| `video_call_accept` | 85 | 接受呼叫 | **保留** |
| `video_offer` | 93 | 媒体协商 | 可删（留也不碍事） |
| `video_answer` | 99 | 媒体协商 | 可删 |
| `video_ice_candidate` | 105 | 媒体协商 | 可删 |
| `video_call_end` | 111 | 结束通话 | **保留** |
| `join` / `leave` | 62 / 69 | 房间管理 | **保留** |

---

## 2. 改造原则

1. **只换媒体层，业务信令不动**：保留 Socket.IO 的 `video_call_request / video_call_accept / video_call_end` 做「来电通知 / 接听 / 挂断」，仅把 `video_offer / video_answer / video_ice_candidate` 这 3 个媒体协商事件交给声网内部完成。
2. **情绪分析零改动**：三个 `realtime/*.js` 文件与后端 `/emotion/*` 接口一个字符不改。
3. **房间名复用**：声网 `channel` 名直接复用现有 `callRoom` / `videoRoom` 的值（`video_xxx`），保证信令与媒体通道对得上。当前临时 Token 阶段，学生/老师两端固定为 `AGORA_CHANNEL = 'video_check'`；接入 App 证书后可恢复动态频道。

---

## 3. 前置准备

### 3.1 注册声网并创建项目

1. 到 [声网 Agora 控制台](https://console.agora.io/) 注册账号（免费）。
2. 新建一个项目，拿到 **App ID**。
3. 鉴权方式（三选一，按顺序推荐）：
   - **临时 Token（推荐用于比赛演示）**：控制台「项目 → 鉴权」里用 Token 生成工具，填 channel 名生成临时 Token（默认 24 小时有效）。
   - **关闭证书鉴权（最快，仅测试）**：把「App 证书」鉴权开关关掉，`join` 时 token 传 `null`。**不安全，仅本地测试用。**
   - **服务端生成 Token（正式）**：用 App ID + App 证书，在后端加一个生成 Token 的接口。工作量 +0.5 天，比赛可选。

> 免费额度：声网每月有 1 万分钟免费时长（以官方最新为准），对比赛演示绰绰有余。

### 3.2 引入 SDK（与现有库保持一致，本地化）

下载声网 Web SDK 4.x（`AgoraRTC_N.js`）放到 `static/js/vendor/`，在 `templates/index.html` 里、`video-call.js` **之前**加入：

```html
<script src="/static/js/vendor/AgoraRTC_N.js"></script>
```

> 与现有 `vue.global.js` / `socket.io.min.js` 同样的本地化 + IIFE 全局暴露方式，全局对象为 `AgoraRTC`。

### 3.3 配置项

在 `video-call.js` 顶部新增配置（可走 `.env` / 后端 `/system/info` 下发，或先硬编码）：

```js
const AGORA_APP_ID = '你的 App ID';
const AGORA_TOKEN = null; // 或临时 token；若开鉴权需每次通话动态填
```

---

## 4. 详细改造步骤

### 4.1 学生端改造

**4.1.1 拨号 `startVideoCall`（替换 getUserMedia 部分，222 行）**

```js
// 旧：localStream = await navigator.mediaDevices.getUserMedia({ video:..., audio:true });
// 新：
agoraClient = AgoraRTC.createClient({ mode: 'rtc', codec: 'vp8' });
await agoraClient.join(AGORA_APP_ID, callRoom.value, AGORA_TOKEN, currentUser.user_id);
const [videoTrack, audioTrack] = await Promise.all([
  AgoraRTC.createCameraVideoTrack(),
  AgoraRTC.createMicrophoneAudioTrack()
]);
await agoraClient.publish([videoTrack, audioTrack]);
// 本地画面：videoTrack.play(localVideo.value)
```

> 权限错误处理（`NotAllowedError` / `NotFoundError`）逻辑保留，包在 `try/catch` 里即可。

**4.1.2 接听 `initStudentVideo`（删除媒体信令监听，138 行）**

删除对 `video_offer / video_answer / video_ice_candidate` 的 4 个 `socket.on`，改为订阅远端：

```js
agoraClient.on('user-published', async (user, mediaType) => {
  await agoraClient.subscribe(user, mediaType);
  if (mediaType === 'video') {
    user.videoTrack.play(remoteVideo.value);
    attachRemoteStream(remoteVideo.value, user.videoTrack.getMediaStream());
  }
  if (mediaType === 'audio') user.audioTrack.play();
});
agoraClient.on('user-left', () => { /* 对方离开，结束通话 */ });
```

**4.1.3 挂断 `endVideoCall`（249 行）**

在原有清理逻辑基础上，追加：

```js
if (agoraClient) { agoraClient.leave(); agoraClient = null; }
// 关闭本地轨
localVideoTrack?.close(); localAudioTrack?.close();
```

**4.1.4 开关 `toggleVideo` / `toggleAudio`（261 / 264 行）**

```js
// 旧：track.enabled = !track.enabled
// 新：
localVideoTrack.setEnabled(!isVideoEnabled.value);
localAudioTrack.setEnabled(!isAudioEnabled.value);
```

**4.1.5 删除 `createPeerConn` / `createOffer` / `createAnswer`（179 / 197 / 204）**

这三个函数整体删除。

### 4.2 老师端改造

与学生端对称，替换 `teacherPeerConn` 相关逻辑：

- `startTeacherVideo`（345）→ 声网建轨 + join + publish（复用同一 channel `videoRoom.value`）
- `createTeacherPeerConn`（367）→ **删**；`createTeacherOffer` / `createTeacherAnswer`（386 / 393）→ **删**
- `initTeacherVideo`（301）→ 删媒体信令监听，加 `user-published` 订阅
- **老师端订阅回调里做情绪分析对接（关键缝合点，对应旧 ontrack 378-383 行）**：

```js
agoraTeacherClient.on('user-published', async (user, mediaType) => {
  await agoraTeacherClient.subscribe(user, mediaType);
  if (mediaType === 'video') {
    user.videoTrack.play(teacherRemoteVideo.value);
    var ms = user.videoTrack.getMediaStream();
    attachRemoteStream(teacherRemoteVideo.value, ms);          // 绑画面
    autoStartRealtimeEmotion(ms, teacherRemoteVideo.value);    // 启动情绪分析 ← 核心
  }
  if (mediaType === 'audio') user.audioTrack.play();
});
```

- `endTeacherVideo`（416）→ 保留 `submitRealtimeCallSummary()`，追加 `agoraTeacherClient.leave()` + 关轨
- `toggleTeacherVideo` / `toggleTeacherAudio`（429 / 432）→ `setEnabled`

### 4.3 情绪分析对接（验证零改动）

`autoStartRealtimeEmotion(stream, videoEl)` 内部流程（774 行起）**完全不变**：

```
remoteStream ──> VoiceProsodyAnalyzer.create(stream)   // 语音韵律（Web Audio）
             └──> FaceEmotionDetector.detect(videoEl)  // 人脸情绪（face-api）
             └──> 上传后端 /emotion/audio-chunk + /emotion/yolo-detect
             └──> EmotionFusionEngine.fuse(...)        // 多模态融合
             └──> 风险回写 → 预警 → 危机工单
```

声网 `user.videoTrack.getMediaStream()` / `user.audioTrack.getMediaStream()` 返回的 `MediaStream` 与旧 `e.streams[0]` 完全等价，直接传入即可。

### 4.4 后端信令清理（可选，非必须）

`app.py` 里 `video_offer` / `video_answer` / `video_ice_candidate`（99-109 行）三个 handler 可删除；保留 `video_call_request / video_call_accept / video_call_end / join / leave`。**保留不动也完全不影响功能。**

### 4.5 统一状态管理建议

当前学生端 / 老师端各一套 `peerConnection`。改造时建议**保留两套变量结构**（`agoraClient` / `agoraTeacherClient`），最小化改动；后续可选优化为单一 `client` + 单通话会话（任何时刻只有一个通话）。**本阶段不强制。**

---

## 5. 状态机对照表

| 阶段 | 旧（自建 WebRTC） | 新（声网） |
|---|---|---|
| 拿本地流 | `getUserMedia` | `createCameraVideoTrack` + `createMicrophoneAudioTrack` |
| 建连接 | `new RTCPeerConnection` + `addTrack` | `AgoraRTC.createClient` + `join` + `publish` |
| 媒体协商 | `createOffer/Answer` + `video_offer/answer/ice` | 声网内部自动 |
| 收远端流 | `ontrack` → `e.streams[0]` | `user-published` → `subscribe` → `getMediaStream()` |
| 开关摄像头/麦 | `track.enabled = !` | `track.setEnabled(!)` |
| 挂断 | `peerConnection.close()` | `client.leave()` + `track.close()` |
| 来电信令 | `video_call_request/accept/end` | **保留不变** |

---

## 6. 测试与验证清单

| 场景 | 预期 | 备注 |
|---|---|---|
| 局域网同网段双向视频 | ✅ 打通 | 基础回归 |
| **手机 4G/5G ↔ 电脑 Wi-Fi 跨网** | ✅ 打通（声网中继） | **本次改造的核心目标** |
| 复杂 NAT（校园网/公司网） | ✅ 打通 | 旧方案失败场景 |
| 老师端订阅后情绪分析启动 | 面部 + 语音 + 融合正常，风险可回写 | 缝合点回归 |
| 开关摄像头/麦克风 | 双向生效 | setEnabled 回归 |
| 挂断/对方离开 | 通话结束，情绪总结提交，无残留轨 | 生命周期回归 |
| 弱网断线重连 | 声网自动重连 | 优于旧方案 |
| 现有 pytest | 全部通过（视频是前端逻辑，后端测试不覆盖） | 确认无回归 |

---

## 7. 回滚方案

- **代码回滚**：`git checkout before-agora-integration -- static/js/modules/video-call.js templates/index.html`，或整库 `git reset --hard before-agora-integration`（注意：会丢弃后续所有改动）。
- **环境回滚**：删除 `static/js/vendor/AgoraRTC_N.js` 及 index.html 里的引入行即可回到自建 WebRTC。

---

## 8. 风险与注意事项

1. **channel 一致性**：声网 channel 必须与 Socket.IO `video_call_request` 里的 `room` 完全一致，否则信令说「接听了」但媒体连不上。
2. **Token**：开鉴权后 token 错误/过期会导致 `join` 失败——建议先用「临时 token」或「关鉴权」跑通，最后再上服务端 token。
3. **HTTPS 前提不变**：声网同样要求安全上下文（HTTPS 或 localhost）才能用摄像头/麦克风，所以仍需走「云服务器 + 域名 HTTPS」或「localhost 本机」。
4. **单通话假设**：一个用户同一时刻只会有一次通话，若产品未来要支持多路/群组，需扩展（声网本身支持，超出本次范围）。
5. **两个 client 生命周期**：学生端 / 老师端各自 `join/leave`，务必在 `endVideoCall` / `endTeacherVideo` 里正确 `leave`，否则重拨会因「已在 channel 中」报错。
6. **本地画面绑定**：声网本地轨用 `track.play(el)` 绑定 `<video>`，不再走 `srcObject = localStream`，注意旧代码里所有 `localVideo.value.srcObject` 赋值点都要同步改。

---

## 9. 工作量与里程碑

| 阶段 | 内容 | 工时 |
|---|---|---|
| M1 准备 | 注册声网、拿 AppID、引入 SDK、配置项 | 0.5 天 |
| M2 学生端改造 | 拨号/接听/挂断/开关 + 订阅回调 | 0.5 天 |
| M3 老师端改造 | 同上 + 情绪分析缝合 | 0.5 天 |
| M4 联调 | 双端打通、情绪分析回归、生命周期测试 | 0.5 天 |
| M5 跨网验证 | 手机 4G ↔ 电脑 跨网 + 复杂 NAT | 0.5 天 |
| **合计** | | **2~2.5 天** |

---

## 10. 交付物

1. 改造后的 `static/js/modules/video-call.js`
2. `static/js/vendor/AgoraRTC_N.js` + `templates/index.html` 引入
3. （可选）后端 token 生成接口
4. 一份跨网测试记录
