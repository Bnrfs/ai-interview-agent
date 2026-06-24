/* AI模拟面试Agent —— 前端主逻辑 v2 */

let sessionId = (typeof SESSION_ID !== 'undefined') ? SESSION_ID : '';
let totalQuestions = 0;
let currentQuestion = 0;
let timeLeft = 0;
let timeLimit = 180;  // 用户配置的每题时限，默认 180 秒
let timerInterval = null;
let isInterviewActive = false;
let _allScenesData = [];
let _currentManageSceneId = '';
let _pressureOn = false;

// ==================== 初始化 ====================
if (window.location.pathname === '/') {
  loadScenes();
  checkCheckpoints();
  loadHistory();
  checkRetryParam();
}

// ==================== 压力模式 Toggle ====================
function togglePressure() {
  _pressureOn = !_pressureOn;
  const sw = document.getElementById('pressureSwitch');
  const extra = document.getElementById('pressureExtra');
  if (_pressureOn) {
    sw.classList.add('active');
    extra.style.display = 'flex';
  } else {
    sw.classList.remove('active');
    extra.style.display = 'none';
  }
}

// ==================== 场景加载 ====================
async function loadScenes() {
  try {
    const resp = await fetch('/api/scenes');
    const data = await resp.json();
    _allScenesData = data.scenes;
    const select = document.getElementById('sceneSelect');
    select.innerHTML = '';

    data.scenes.forEach(s => {
      const qc = s.question_count !== undefined ? ` · ${s.question_count}题` : '';
      const tag = s.builtin ? '内置' : '自定义';
      select.innerHTML += `<option value="${s.id}">${s.name}${qc}  [${tag}]</option>`;
    });

    if (data.scenes.length > 0) {
      updateCategories(data.scenes[0].id);
    }
    select.onchange = () => updateCategories(select.value);

    // 更新题目总数
    let total = 0;
    data.scenes.filter(s => s.builtin).forEach(() => {});
    document.getElementById('totalQuestionBadge').textContent = data.scenes.length + ' 场景';
  } catch (e) {
    console.error('加载场景失败:', e);
  }
}

function updateCategories(sceneId) {
  const scene = _allScenesData.find(s => s.id === sceneId);
  const select = document.getElementById('categorySelect');
  select.innerHTML = '<option value="">全部类别</option>';
  if (scene && scene.categories) {
    scene.categories.forEach(c => {
      select.innerHTML += `<option value="${c}">${c}</option>`;
    });
  }
}

// ==================== Checkpoints & History ====================
async function checkCheckpoints() {
  try {
    const resp = await fetch('/api/checkpoints');
    const data = await resp.json();
    if (data.checkpoints && data.checkpoints.length > 0) {
      const cp = data.checkpoints[0];
      const found = _allScenesData.find(s => s.id === cp.scene);
      const name = found ? found.name : cp.scene;
      document.getElementById('checkpointText').textContent =
        `检测到未完成的「${name}」面试（进度 ${cp.progress}）`;
      document.getElementById('checkpointBanner').style.display = 'flex';
      window._resumeId = cp.session_id;
    }
  } catch (e) {
    console.error('检查存档失败:', e);
  }
}

async function loadHistory() {
  try {
    const resp = await fetch('/api/records');
    const data = await resp.json();
    if (data.records && data.records.length > 0) {
      document.getElementById('historyCard').style.display = 'block';
      const list = document.getElementById('historyList');
      list.innerHTML = data.records.slice(0, 6).map(r => {
        const d = new Date(r.start_time * 1000);
        const time = d.toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        const found = _allScenesData.find(s => s.id === r.scene);
        const sceneName = found ? found.name : r.scene;
        const retryBtn = r.wrong_count > 0
          ? `<button class="btn btn-warning btn-sm" onclick="event.stopPropagation();location.href='/?retry=${r.session_id}'">重练${r.wrong_count}题</button>`
          : '';
        return `<div class="history-item" onclick="viewRecord('${r.session_id}')">
          <div class="history-dot">${r.total_score ? Math.round(r.total_score) : '--'}</div>
          <div class="history-info">
            <div class="scene">${escHtml(sceneName)}</div>
            <div class="meta">${r.question_count}题 · ${time}</div>
          </div>
          ${retryBtn}
        </div>`;
      }).join('');
    }
  } catch (e) {
    console.error('加载历史失败:', e);
  }
}

function viewRecord(sid) {
  location.href = `/report?session_id=${sid}`;
}

// ==================== 开始面试 ====================
async function startInterview() {
  const scene = document.getElementById('sceneSelect').value;
  const questionCount = parseInt(document.getElementById('questionCount').value);
  const timeLimit = parseInt(document.getElementById('timeLimit').value);
  const category = document.getElementById('categorySelect').value;
  const pressure = _pressureOn;
  const pressureLevel = pressure ? parseInt(document.getElementById('pressureLevel').value) : 0;

  const btn = document.getElementById('startBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 准备中...';

  try {
    const resp = await fetch('/api/interview/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scene, question_count: questionCount, time_limit: timeLimit, category, pressure, pressure_level: pressureLevel }),
    });

    if (!resp.ok) {
      const err = await resp.json();
      alert('启动失败：' + (err.detail || '未知错误'));
      btn.disabled = false;
      btn.innerHTML = '开始面试';
      return;
    }

    const data = await resp.json();
    location.href = `/interview?session_id=${data.session_id}`;
  } catch (e) {
    alert('网络错误：' + e.message);
    btn.disabled = false;
    btn.innerHTML = '开始面试';
  }
}

async function resumeInterview() {
  if (!window._resumeId) return;
  try {
    await fetch('/api/interview/resume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: window._resumeId }),
    });
    location.href = `/interview?session_id=${window._resumeId}`;
  } catch (e) {
    alert('恢复失败：' + e.message);
  }
}

async function dismissCheckpoint() {
  if (!window._resumeId) return;
  try {
    await fetch(`/api/checkpoints/${window._resumeId}`, { method: 'DELETE' });
  } catch (e) {
    console.error('删除存档失败:', e);
  }
  document.getElementById('checkpointBanner').style.display = 'none';
  window._resumeId = '';
}

async function clearRecords() {
  if (!confirm('确定要清空所有历史记录吗？此操作不可恢复。')) return;
  try {
    await fetch('/api/records', { method: 'DELETE' });
    document.getElementById('historyList').innerHTML = '';
    document.getElementById('historyCard').style.display = 'none';
  } catch (e) {
    alert('清空失败：' + e.message);
  }
}

// ==================== 错题重练 ====================
let _retrySid = '';

function checkRetryParam() {
  const params = new URLSearchParams(window.location.search);
  const retry = params.get('retry');
  if (retry) {
    _retrySid = retry;
    document.getElementById('retryBanner').style.display = 'flex';
  }
}

async function startRetry() {
  if (!_retrySid) return;
  const scene = document.getElementById('sceneSelect').value;
  const questionCount = parseInt(document.getElementById('questionCount').value);
  const timeLimit = parseInt(document.getElementById('timeLimit').value);
  const pressure = _pressureOn;

  const btn = document.getElementById('startBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 准备中...';

  try {
    const resp = await fetch('/api/interview/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scene, question_count: questionCount, time_limit: timeLimit, pressure, retry_session_id: _retrySid }),
    });
    if (!resp.ok) {
      const err = await resp.json();
      alert('重练启动失败：' + (err.detail || '未知错误'));
      btn.disabled = false;
      btn.innerHTML = '开始面试';
      return;
    }
    const data = await resp.json();
    location.href = `/interview?session_id=${data.session_id}`;
  } catch (e) {
    alert('网络错误：' + e.message);
    btn.disabled = false;
    btn.innerHTML = '开始面试';
  }
}

function dismissRetry() {
  document.getElementById('retryBanner').style.display = 'none';
  _retrySid = '';
}

// ==================== 面试页逻辑 ====================
if (window.location.pathname === '/interview') {
  initInterview();
}

async function initInterview() {
  if (!sessionId) {
    document.getElementById('chatArea').innerHTML =
      '<div class="loading-msg">缺少会话参数，请返回首页重新开始。</div>';
    return;
  }

  try {
    const resp = await fetch(`/api/interview/status/${sessionId}`);
    const status = await resp.json();
    if (!status.exists) {
      document.getElementById('chatArea').innerHTML =
        '<div class="loading-msg">会话不存在或已过期，请返回首页重新开始。</div>';
      return;
    }

    const found = (_allScenesData || []).find(s => s.id === status.scene);
    const sceneLabel = found ? found.name : status.scene;
    document.getElementById('sceneLabel').textContent = '🎯 ' + sceneLabel;
    totalQuestions = parseInt(status.progress.split('/')[1]) || 0;
    currentQuestion = parseInt(status.progress.split('/')[0]) || 0;
    timeLimit = status.time_limit || 180;  // 从后端读取用户配置的时限

    isInterviewActive = true;
    document.getElementById('submitBtn').disabled = false;
    document.getElementById('voiceBtn').disabled = false;
    document.getElementById('answerInput').disabled = false;

    // 根据当前 phase 分流处理
    if (status.phase === 'paused') {
      // 暂停状态：显示 overlay，不发消息
      document.getElementById('chatArea').innerHTML = '';
      updateProgress();
      document.getElementById('pauseOverlay').style.display = 'flex';
      return;
    }

    if (status.phase === 'questioning' || status.phase === 'followup') {
      // 恢复/刷新状态：调用 resume API 获取当前题目
      await resumeInterviewFlow();
      return;
    }

    // 正常开始流程（opening/idle）
    const chat = document.getElementById('chatArea');
    chat.innerHTML = '<div class="loading-msg">正在连接面试官...</div>';

    const answerResp = await fetch('/api/interview/answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, answer: '（开始面试）' }),
    });
    if (answerResp.ok) {
      const data = await answerResp.json();
      chat.innerHTML = '';
      addMessage('interviewer', data.message);
      if (data.question_index) {
        currentQuestion = data.question_index;
        totalQuestions = data.total_questions;
        updateProgress();
      }
      startTimer(timeLimit);  // 第一题开始计时
    }

    document.getElementById('answerInput').focus();
  } catch (e) {
    document.getElementById('chatArea').innerHTML =
      '<div class="loading-msg">初始化失败：' + e.message + '</div>';
  }
}

// ==================== 暂停恢复 ====================

async function resumeFromPause() {
  document.getElementById('pauseOverlay').style.display = 'none';
  await resumeInterviewFlow();
}

async function resumeInterviewFlow() {
  const chat = document.getElementById('chatArea');
  chat.innerHTML = '<div class="loading-msg">正在恢复面试...</div>';

  try {
    const resumeResp = await fetch('/api/interview/resume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });

    if (!resumeResp.ok) {
      chat.innerHTML = '<div class="loading-msg">恢复失败，请返回首页重新开始。</div>';
      return;
    }

    const data = await resumeResp.json();
    console.log('[DEBUG resumeInterviewFlow] data.remaining_time:', data.remaining_time, 'timeLimit:', timeLimit, 'data:', JSON.stringify(data));
    chat.innerHTML = '';
    addMessage('interviewer', data.message);
    // DEBUG: 显示恢复时的剩余时间
    addMessage('system', '[DEBUG] remaining_time=' + data.remaining_time + ', timeLimit=' + timeLimit);
    if (data.question_index) {
      currentQuestion = data.question_index;
      totalQuestions = data.total_questions;
      updateProgress();
    }

    isInterviewActive = true;
    document.getElementById('submitBtn').disabled = false;
    document.getElementById('voiceBtn').disabled = false;
    document.getElementById('answerInput').disabled = false;
    document.getElementById('answerInput').focus();
    // 优先使用后端保存的 remaining_time，无记录则使用用户配置的 timeLimit
    startTimer(data.remaining_time || timeLimit);
  } catch (e) {
    chat.innerHTML = '<div class="loading-msg">恢复失败：' + e.message + '</div>';
  }
}

function addMessage(type, text) {
  const chat = document.getElementById('chatArea');
  const div = document.createElement('div');
  div.className = `msg ${type}`;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function addScoreMessage(scores) {
  if (!scores) return;
  const chat = document.getElementById('chatArea');
  const div = document.createElement('div');
  div.className = 'msg scores';
  div.innerHTML = `📊 逻辑${scores.logic || '--'} | 内容${scores.completeness || '--'} | 组织${scores.organization || '--'} | 匹配${scores.match || '--'}<br>💬 ${scores.comment || ''}`;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function updateProgress() {
  document.getElementById('progressLabel').textContent = `第 ${currentQuestion}/${totalQuestions} 题`;
}

function startTimer(seconds) {
  clearInterval(timerInterval);
  timeLeft = seconds;
  updateTimerDisplay();
  timerInterval = setInterval(() => {
    timeLeft--;
    updateTimerDisplay();
    if (timeLeft <= 0) clearInterval(timerInterval);
  }, 1000);
}

function updateTimerDisplay() {
  const mins = Math.floor(timeLeft / 60);
  const secs = timeLeft % 60;
  const el = document.getElementById('timerLabel');
  el.textContent = `⏱ ${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  el.className = 'timer';
  if (timeLeft <= 30) el.className = 'timer danger';
  else if (timeLeft <= 60) el.className = 'timer warning';
}

// ==================== 回答提交 ====================
document.getElementById('submitBtn')?.addEventListener('click', submitAnswer);
document.getElementById('answerInput')?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && e.ctrlKey) submitAnswer();
});

async function submitAnswer() {
  if (!isInterviewActive) return;

  const input = document.getElementById('answerInput');
  const answer = input.value.trim();
  if (!answer) return;

  const btn = document.getElementById('submitBtn');
  btn.disabled = true;
  btn.textContent = '发送中...';

  addMessage('user', answer);
  input.value = '';
  clearInterval(timerInterval);

  try {
    const resp = await fetch('/api/interview/answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, answer }),
    });

    if (!resp.ok) {
      const err = await resp.json();
      addMessage('system', '错误：' + (err.detail || '未知'));
      btn.disabled = false;
      btn.textContent = '发送回答';
      return;
    }

    const data = await resp.json();

    if (data.scores) addScoreMessage(data.scores);
    if (data.message) addMessage('interviewer', data.message);

    if (data.question_index) {
      currentQuestion = data.question_index;
      totalQuestions = data.total_questions;
      updateProgress();
    }

    if (data.phase === 'report') {
      isInterviewActive = false;
      btn.textContent = '面试结束';
      document.getElementById('pauseBtn').style.display = 'none';
      document.getElementById('voiceBtn').style.display = 'none';
      input.disabled = true;
      setTimeout(() => { location.href = `/report?session_id=${sessionId}`; }, 3000);
      return;
    }

    startTimer(timeLimit);  // 下一题使用用户配置的时限
    btn.disabled = false;
    btn.textContent = '发送回答';
    input.focus();
  } catch (e) {
    addMessage('system', '网络错误：' + e.message);
    btn.disabled = false;
    btn.textContent = '发送回答';
  }
}

// ==================== 暂停 ====================
document.getElementById('pauseBtn')?.addEventListener('click', async () => {
  if (!sessionId) return;
  clearInterval(timerInterval);
  try {
    await fetch('/api/interview/pause', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, remaining_time: timeLeft }),
    });
    document.getElementById('pauseOverlay').style.display = 'flex';
  } catch (e) {
    alert('暂停失败：' + e.message);
  }
});

// ==================== 语音输入 ====================
document.getElementById('voiceBtn')?.addEventListener('click', () => {
  if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    alert('你的浏览器不支持语音输入，请使用 Chrome 浏览器或手动输入。');
    return;
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition = new SpeechRecognition();
  recognition.lang = 'zh-CN';
  recognition.interimResults = false;
  recognition.continuous = false;

  const btn = document.getElementById('voiceBtn');
  btn.textContent = '🎤 聆听中...';
  btn.style.background = 'var(--danger)';

  recognition.start();

  recognition.onresult = (event) => {
    const text = event.results[0][0].transcript;
    document.getElementById('answerInput').value = text;
    btn.textContent = '🎤 语音';
    btn.style.background = '';
  };

  recognition.onerror = () => {
    btn.textContent = '🎤 语音';
    btn.style.background = '';
    alert('语音识别失败，请手动输入。');
  };

  recognition.onend = () => {
    btn.textContent = '🎤 语音';
    btn.style.background = '';
  };
});

// ==================== 自定义场景管理 ====================

function toggleCustomPanel() {
  const panel = document.getElementById('customPanel');
  const btn = document.getElementById('toggleCustomBtn');
  if (panel.style.display === 'none') {
    panel.style.display = 'block';
    btn.textContent = '−';
    loadCustomScenes();
  } else {
    panel.style.display = 'none';
    btn.textContent = '＋';
  }
}

async function loadCustomScenes() {
  try {
    const resp = await fetch('/api/custom/scenes');
    const data = await resp.json();
    const list = document.getElementById('customSceneList');
    if (data.scenes.length === 0) {
      list.innerHTML = '<div class="empty-state"><div class="icon">📭</div>暂无自定义场景</div>';
      return;
    }
    list.innerHTML = data.scenes.map(s => `
      <div class="scene-list-item">
        <div class="scene-dot custom"></div>
        <div class="scene-info">
          <div class="name">${escHtml(s.name)}</div>
          <div class="meta">${s.question_count || 0} 题 · ${(s.categories || []).join('、')}</div>
        </div>
        <div class="scene-actions">
          <button class="btn btn-ghost btn-sm" onclick="manageQuestions('${s.id}','${escHtml(s.name)}')">题目</button>
          <button class="btn btn-ghost btn-sm" onclick="deleteScene('${s.id}','${escHtml(s.name)}')" style="color:var(--danger)">删除</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    console.error('加载自定义场景失败:', e);
  }
}

async function createCustomScene() {
  const name = document.getElementById('newSceneName').value.trim();
  const categoriesRaw = document.getElementById('newSceneCategories').value.trim();

  if (!name) { alert('请输入场景名称'); return; }

  const categories = categoriesRaw ? categoriesRaw.split(',').map(c => c.trim()).filter(Boolean) : [];

  try {
    const resp = await fetch('/api/custom/scenes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, categories }),
    });
    if (!resp.ok) {
      const err = await resp.json();
      alert('创建失败：' + (err.detail || '未知错误'));
      return;
    }
    document.getElementById('newSceneName').value = '';
    document.getElementById('newSceneCategories').value = '';
    loadCustomScenes();
    loadScenes();
  } catch (e) {
    alert('网络错误：' + e.message);
  }
}

async function deleteScene(sceneId, sceneName) {
  if (!confirm(`确定删除场景「${sceneName}」？关联题目也会被删除。`)) return;

  try {
    const resp = await fetch(`/api/custom/scenes/${sceneId}`, { method: 'DELETE' });
    if (!resp.ok) {
      const err = await resp.json();
      alert('删除失败：' + (err.detail || '未知错误'));
      return;
    }
    loadCustomScenes();
    loadScenes();
    if (_currentManageSceneId === sceneId) closeQuestionPanel();
  } catch (e) {
    alert('网络错误：' + e.message);
  }
}

// ==================== 自定义题目管理 ====================

function manageQuestions(sceneId, sceneName) {
  _currentManageSceneId = sceneId;
  document.getElementById('questionManageCard').style.display = 'block';
  document.getElementById('questionManageTitle').textContent = `「${sceneName}」题目`;
  document.getElementById('newQuestionText').value = '';
  document.getElementById('newQuestionCategory').value = '';
  document.getElementById('newQuestionDifficulty').value = '3';
  document.getElementById('newQuestionKeywords').value = '';
  document.getElementById('newQuestionModelAnswer').value = '';
  cancelAutoGenerate();
  loadCustomQuestions(sceneId);
  document.getElementById('questionManageCard').scrollIntoView({ behavior: 'smooth' });
}

function closeQuestionPanel() {
  document.getElementById('questionManageCard').style.display = 'none';
  _currentManageSceneId = '';
}

async function loadCustomQuestions(sceneId) {
  try {
    const resp = await fetch(`/api/custom/questions/${sceneId}`);
    const data = await resp.json();
    const list = document.getElementById('customQuestionList');
    if (data.questions.length === 0) {
      list.innerHTML = '<div class="empty-state"><div class="icon">📝</div>暂无题目，手动添加或使用 AI 自动生成</div>';
      return;
    }
    list.innerHTML = data.questions.map((q, i) => `
      <div class="question-item">
        <div class="question-idx">${i + 1}</div>
        <div class="question-body">
          <div class="q-text">${escHtml(q.question)}</div>
          <div class="q-tags">
            <span class="tag difficulty">${'⭐'.repeat(q.difficulty || 3)}</span>
            <span class="tag category">${escHtml(q.category || '综合')}</span>
            ${(q.keywords || []).slice(0, 3).map(k => `<span class="tag">${escHtml(k)}</span>`).join('')}
          </div>
        </div>
        <button class="btn btn-ghost btn-sm" onclick="deleteCustomQuestion('${q.id}')" style="color:var(--danger);flex-shrink:0;">删除</button>
      </div>
    `).join('');
  } catch (e) {
    console.error('加载题目失败:', e);
  }
}

async function addCustomQuestion() {
  if (!_currentManageSceneId) return;

  const question = document.getElementById('newQuestionText').value.trim();
  const category = document.getElementById('newQuestionCategory').value.trim();
  const difficulty = parseInt(document.getElementById('newQuestionDifficulty').value) || 3;
  const keywordsRaw = document.getElementById('newQuestionKeywords').value.trim();
  const modelAnswer = document.getElementById('newQuestionModelAnswer').value.trim();

  if (!question) { alert('请输入题目内容'); return; }

  const keywords = keywordsRaw ? keywordsRaw.split(',').map(k => k.trim()).filter(Boolean) : [];

  try {
    const resp = await fetch('/api/custom/questions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scene_id: _currentManageSceneId, question, category, difficulty, keywords, model_answer: modelAnswer }),
    });
    if (!resp.ok) {
      const err = await resp.json();
      alert('添加失败：' + (err.detail || '未知错误'));
      return;
    }
    document.getElementById('newQuestionText').value = '';
    document.getElementById('newQuestionKeywords').value = '';
    document.getElementById('newQuestionModelAnswer').value = '';
    loadCustomQuestions(_currentManageSceneId);
    loadCustomScenes();
    loadScenes();
  } catch (e) {
    alert('网络错误：' + e.message);
  }
}

async function deleteCustomQuestion(qid) {
  if (!confirm('确定删除这道题目？')) return;

  try {
    const resp = await fetch(`/api/custom/questions/${qid}`, { method: 'DELETE' });
    if (!resp.ok) {
      const err = await resp.json();
      alert('删除失败：' + (err.detail || '未知错误'));
      return;
    }
    loadCustomQuestions(_currentManageSceneId);
    loadCustomScenes();
    loadScenes();
  } catch (e) {
    alert('网络错误：' + e.message);
  }
}

// ==================== 自动生成题目 ====================

function autoGenerateQuestions() {
  document.getElementById('autoGenOptions').style.display = 'flex';
  document.getElementById('autoGenBtn').style.display = 'none';
}

function cancelAutoGenerate() {
  document.getElementById('autoGenOptions').style.display = 'none';
  document.getElementById('autoGenBtn').style.display = 'inline-flex';
}

async function confirmAutoGenerate() {
  if (!_currentManageSceneId) return;

  const count = parseInt(document.getElementById('autoGenCount').value);
  const confirmBtn = document.querySelector('#autoGenOptions .btn-success');
  confirmBtn.disabled = true;
  confirmBtn.innerHTML = '<span class="spinner"></span>';

  try {
    const resp = await fetch('/api/custom/questions/auto-generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scene_id: _currentManageSceneId, count }),
    });

    if (!resp.ok) {
      const err = await resp.json();
      alert('生成失败：' + (err.detail || '未知错误'));
      confirmBtn.disabled = false;
      confirmBtn.textContent = '确认';
      return;
    }

    const data = await resp.json();
    alert(`成功生成 ${data.generated} 道题目！`);
    loadCustomQuestions(_currentManageSceneId);
    loadCustomScenes();
    loadScenes();
    cancelAutoGenerate();
  } catch (e) {
    alert('网络错误：' + e.message);
    confirmBtn.disabled = false;
    confirmBtn.textContent = '确认';
  }
}

// ==================== 工具函数 ====================
function escHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
// ==================== 面试准备助手 ====================

function toggleAssistantPanel() {
  const panel = document.getElementById('assistantPanel');
  const btn = document.getElementById('toggleAssistantBtn');
  if (panel.style.display === 'none') {
    panel.style.display = 'block';
    btn.textContent = '−';
  } else {
    panel.style.display = 'none';
    btn.textContent = '＋';
  }
}

async function askAssistant() {
  const position = document.getElementById('assistantPosition').value.trim();
  const background = document.getElementById('assistantBackground').value.trim();
  const level = document.getElementById('assistantLevel').value;
  const focusRaw = document.getElementById('assistantFocus').value.trim();

  if (!position) { alert('请填写目标岗位'); return; }

  const focusAreas = focusRaw ? focusRaw.split(',').map(f => f.trim()).filter(Boolean) : [];
  const btn = document.getElementById('assistantBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 生成中...';

  try {
    const resp = await fetch('/api/assistant/prepare-guide', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ position, background, level, focus_areas: focusAreas }),
    });
    if (!resp.ok) {
      const err = await resp.json();
      alert('生成失败：' + (err.detail || '未知错误'));
      btn.disabled = false;
      btn.innerHTML = '🤖 生成准备指南';
      return;
    }
    const data = await resp.json();
    // 将 Markdown 转为 HTML（简单处理）
    const html = markdownToHtml(data.guide);
    document.getElementById('assistantContent').innerHTML = html;
    document.getElementById('assistantResult').style.display = 'block';
    btn.disabled = false;
    btn.innerHTML = '🔄 重新生成';
  } catch (e) {
    alert('网络错误：' + e.message);
    btn.disabled = false;
    btn.innerHTML = '🤖 生成准备指南';
  }
}

function closeAssistantResult() {
  document.getElementById('assistantResult').style.display = 'none';
}

function copyAssistantGuide() {
  const content = document.getElementById('assistantContent').innerText;
  navigator.clipboard.writeText(content).then(() => {
    alert('已复制到剪贴板');
  }).catch(() => {
    alert('复制失败，请手动选择复制');
  });
}

function markdownToHtml(md) {
  if (!md) return '';
  let html = md;
  // 标题
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>');
  // 加粗
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // 列表项
  html = html.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
  // 数字列表
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
  // 把连续的 <li> 包裹在 <ul> 中
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');
  // 段落
  html = html.replace(/\n\n/g, '</p><p>');
  html = '<p>' + html + '</p>';
  // 清理空段落
  html = html.replace(/<p>\s*<\/p>/g, '');
  // 清理多余换行
  html = html.replace(/\n/g, '<br>');
  return html;
}