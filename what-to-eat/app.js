const STORAGE_KEY = 'what-to-eat-v1';

const DEFAULT_CANDIDATES = [
  '麻辣烫', '兰州拉面', '黄焖鸡米饭', '沙县小吃',
  '日式咖喱', '寿司', '麦当劳', '披萨',
  '螺蛳粉', '盖浇饭', '酸菜鱼', '烤肉饭',
  '炒河粉', '云吞面', '凉皮', '川菜'
];

let state = loadState();
let currentPick = null;

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultState();
    return Object.assign(defaultState(), JSON.parse(raw));
  } catch (_e) {
    return defaultState();
  }
}

function defaultState() {
  return {
    apiKey: '',
    model: 'claude-opus-4-7',
    candidates: DEFAULT_CANDIDATES.map(name => ({ name })),
    history: []
  };
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function showView(name) {
  document.getElementById('main-view').hidden = name !== 'main';
  document.getElementById('settings-view').hidden = name !== 'settings';
  if (name === 'settings') renderSettings();
}

function renderSettings() {
  document.getElementById('api-key').value = state.apiKey;
  document.getElementById('model-select').value = state.model;

  const list = document.getElementById('candidates-list');
  list.innerHTML = '';
  if (state.candidates.length === 0) {
    const li = document.createElement('li');
    li.textContent = '清单是空的，加几个吧';
    li.style.color = '#8a8275';
    list.appendChild(li);
  } else {
    state.candidates.forEach((c, i) => {
      const li = document.createElement('li');
      const span = document.createElement('span');
      span.textContent = c.name;
      const rm = document.createElement('button');
      rm.textContent = '删除';
      rm.className = 'remove-btn';
      rm.onclick = () => {
        state.candidates.splice(i, 1);
        saveState();
        renderSettings();
      };
      li.appendChild(span);
      li.appendChild(rm);
      list.appendChild(li);
    });
  }

  const hist = document.getElementById('history-list');
  hist.innerHTML = '';
  const recent = state.history.slice(-20).reverse();
  if (recent.length === 0) {
    const li = document.createElement('li');
    li.textContent = '还没有记录';
    li.style.color = '#8a8275';
    hist.appendChild(li);
  } else {
    recent.forEach(h => {
      const li = document.createElement('li');
      const date = new Date(h.ts).toLocaleDateString('zh-CN');
      const fbText = h.feedback === 'up' ? '喜欢'
        : h.feedback === 'down' ? '不要'
        : h.feedback === 'meh' ? '还行'
        : '';
      const left = document.createElement('span');
      left.innerHTML = `${h.name}<span class="history-meta">${date}</span>`;
      li.appendChild(left);
      if (fbText) {
        const tag = document.createElement('span');
        tag.className = `fb-label ${h.feedback}`;
        tag.textContent = fbText;
        li.appendChild(tag);
      }
      hist.appendChild(li);
    });
  }
}

function computeStats() {
  return state.candidates.map(c => {
    const records = state.history.filter(h => h.name === c.name);
    return {
      name: c.name,
      up: records.filter(r => r.feedback === 'up').length,
      down: records.filter(r => r.feedback === 'down').length,
      meh: records.filter(r => r.feedback === 'meh').length,
      total: records.length
    };
  });
}

function recentMeals(n) {
  return state.history.slice(-n).map(h => h.name);
}

async function decide(mood) {
  if (!state.apiKey) {
    throw new Error('请先在设置中填入 Anthropic API Key');
  }
  if (state.candidates.length === 0) {
    throw new Error('候选清单是空的，请在设置中添加');
  }

  const stats = computeStats();
  const recent = recentMeals(5);
  const candidateNames = state.candidates.map(c => c.name);

  const statsText = stats.map(s => {
    if (s.total === 0) return `- ${s.name}（暂无反馈）`;
    return `- ${s.name}（喜欢 ${s.up}，还行 ${s.meh}，不要 ${s.down}）`;
  }).join('\n');

  const recentText = recent.length > 0 ? recent.join('、') : '无';

  const prompt = `你在帮用户决定今天吃什么。从候选清单中挑一个最合适的。

用户当前心情/想法：${mood || '（未填写，自由发挥）'}

最近吃过（尽量避免重复，除非真的特别契合）：${recentText}

候选清单与历史反馈：
${statsText}

要求：
- 必须从候选清单中精确选一个名字
- 综合考虑当前心情、用户偏好、近期记录
- 用一句话说明为什么选这个，要有人情味、具体，别套话
- 只返回 JSON，字段为 pick 和 reason`;

  const body = {
    model: state.model,
    max_tokens: 512,
    messages: [{ role: 'user', content: prompt }],
    output_config: {
      format: {
        type: 'json_schema',
        schema: {
          type: 'object',
          properties: {
            pick: { type: 'string', enum: candidateNames },
            reason: { type: 'string' }
          },
          required: ['pick', 'reason'],
          additionalProperties: false
        }
      }
    }
  };

  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-api-key': state.apiKey,
      'anthropic-version': '2023-06-01',
      'anthropic-dangerous-direct-browser-access': 'true'
    },
    body: JSON.stringify(body)
  });

  if (!response.ok) {
    let msg = `HTTP ${response.status}`;
    try {
      const err = await response.json();
      if (err.error && err.error.message) msg = err.error.message;
    } catch (_e) { /* keep default */ }
    throw new Error(`API 调用失败：${msg}`);
  }

  const data = await response.json();
  const textBlock = (data.content || []).find(b => b.type === 'text');
  if (!textBlock) throw new Error('返回内容里没有文本块');

  let parsed;
  try {
    parsed = JSON.parse(textBlock.text);
  } catch (_e) {
    throw new Error('返回的不是合法 JSON：' + textBlock.text);
  }

  if (!candidateNames.includes(parsed.pick)) {
    parsed.pick = candidateNames[0];
    parsed.reason = '(AI 返回的名字不在清单里，自动用了第一个) ' + (parsed.reason || '');
  }

  return parsed;
}

async function handleDecide() {
  const btn = document.getElementById('decide-btn');
  const rerollBtn = document.getElementById('reroll');
  const errEl = document.getElementById('error');
  const resultEl = document.getElementById('result');
  const mood = document.getElementById('mood-input').value.trim();

  errEl.hidden = true;
  btn.disabled = true;
  rerollBtn.disabled = true;
  const originalText = btn.textContent;
  btn.textContent = '思考中...';

  try {
    const result = await decide(mood);
    currentPick = { name: result.pick, reason: result.reason, mood, ts: Date.now() };
    document.getElementById('pick').textContent = result.pick;
    document.getElementById('reason').textContent = result.reason;
    resultEl.hidden = false;
    document.querySelectorAll('.fb-btn').forEach(b => b.classList.remove('active'));

    state.history.push({
      name: result.pick,
      feedback: null,
      ts: currentPick.ts,
      mood
    });
    if (state.history.length > 200) {
      state.history = state.history.slice(-200);
    }
    saveState();
  } catch (e) {
    errEl.textContent = e.message;
    errEl.hidden = false;
  } finally {
    btn.disabled = false;
    rerollBtn.disabled = false;
    btn.textContent = originalText;
  }
}

function handleFeedback(fb) {
  if (!currentPick) return;
  for (let i = state.history.length - 1; i >= 0; i--) {
    if (state.history[i].ts === currentPick.ts) {
      state.history[i].feedback = fb;
      break;
    }
  }
  saveState();
  document.querySelectorAll('.fb-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.fb === fb);
  });
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('decide-btn').addEventListener('click', handleDecide);
  document.getElementById('reroll').addEventListener('click', handleDecide);
  document.getElementById('settings-btn').addEventListener('click', () => showView('settings'));
  document.getElementById('back-btn').addEventListener('click', () => showView('main'));

  document.querySelectorAll('.fb-btn').forEach(b => {
    b.addEventListener('click', () => handleFeedback(b.dataset.fb));
  });

  document.getElementById('api-key').addEventListener('change', (e) => {
    state.apiKey = e.target.value.trim();
    saveState();
  });

  document.getElementById('model-select').addEventListener('change', (e) => {
    state.model = e.target.value;
    saveState();
  });

  document.getElementById('add-btn').addEventListener('click', () => {
    const input = document.getElementById('new-candidate');
    const name = input.value.trim();
    if (!name) return;
    if (state.candidates.some(c => c.name === name)) {
      input.value = '';
      return;
    }
    state.candidates.push({ name });
    saveState();
    input.value = '';
    renderSettings();
  });

  document.getElementById('new-candidate').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') document.getElementById('add-btn').click();
  });

  document.getElementById('clear-history').addEventListener('click', () => {
    if (confirm('确定清空所有历史记录？候选清单不会被删除。')) {
      state.history = [];
      saveState();
      renderSettings();
    }
  });

  if (!state.apiKey) {
    showView('settings');
  }
});
