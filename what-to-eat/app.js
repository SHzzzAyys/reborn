const STORAGE_KEY = 'what-to-eat-v1';

const MEALS = [
  { id: 'breakfast', label: '早餐', short: '早' },
  { id: 'lunch', label: '午餐', short: '午' },
  { id: 'dinner', label: '晚餐', short: '晚' }
];

const ALL_MEAL_IDS = MEALS.map(m => m.id);

const DEFAULT_CANDIDATES = [
  { name: '包子豆浆', meals: ['breakfast'] },
  { name: '煎饼果子', meals: ['breakfast'] },
  { name: '皮蛋瘦肉粥', meals: ['breakfast'] },
  { name: '兰州拉面', meals: ['breakfast', 'lunch', 'dinner'] },
  { name: '云吞面', meals: ['breakfast', 'lunch', 'dinner'] },
  { name: '沙县小吃', meals: ['breakfast', 'lunch', 'dinner'] },
  { name: '麦当劳', meals: ['breakfast', 'lunch', 'dinner'] },
  { name: '麻辣烫', meals: ['lunch', 'dinner'] },
  { name: '黄焖鸡米饭', meals: ['lunch', 'dinner'] },
  { name: '日式咖喱', meals: ['lunch', 'dinner'] },
  { name: '寿司', meals: ['lunch', 'dinner'] },
  { name: '披萨', meals: ['lunch', 'dinner'] },
  { name: '螺蛳粉', meals: ['lunch', 'dinner'] },
  { name: '盖浇饭', meals: ['lunch', 'dinner'] },
  { name: '酸菜鱼', meals: ['lunch', 'dinner'] },
  { name: '烤肉饭', meals: ['lunch', 'dinner'] },
  { name: '炒河粉', meals: ['lunch', 'dinner'] },
  { name: '凉皮', meals: ['lunch', 'dinner'] },
  { name: '川菜', meals: ['lunch', 'dinner'] }
];

let state = loadState();
let currentPick = null;
let currentMeal = detectMeal();

function detectMeal() {
  const h = new Date().getHours();
  if (h >= 5 && h < 10) return 'breakfast';
  if (h >= 10 && h < 15) return 'lunch';
  return 'dinner';
}

function mealLabel(id) {
  const m = MEALS.find(x => x.id === id);
  return m ? m.label : id;
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultState();
    const parsed = JSON.parse(raw);
    const merged = Object.assign(defaultState(), parsed);
    merged.candidates = merged.candidates.map(c =>
      Array.isArray(c.meals) && c.meals.length > 0
        ? c
        : Object.assign({}, c, { meals: ALL_MEAL_IDS.slice() })
    );
    merged.history = merged.history.map(h =>
      h.meal ? h : Object.assign({}, h, { meal: 'lunch' })
    );
    return merged;
  } catch (_e) {
    return defaultState();
  }
}

function defaultState() {
  return {
    apiKey: '',
    model: 'claude-opus-4-7',
    candidates: DEFAULT_CANDIDATES.map(c => ({ name: c.name, meals: c.meals.slice() })),
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

function renderMealSelector() {
  document.querySelectorAll('.meal-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.meal === currentMeal);
  });
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
      li.className = 'candidate-item';

      const toggles = document.createElement('div');
      toggles.className = 'meal-toggles';
      MEALS.forEach(meal => {
        const pill = document.createElement('button');
        pill.className = 'meal-pill';
        pill.textContent = meal.short;
        pill.title = `适合${meal.label}`;
        if (c.meals.includes(meal.id)) pill.classList.add('active');
        pill.onclick = () => {
          if (c.meals.includes(meal.id)) {
            if (c.meals.length === 1) return;
            c.meals = c.meals.filter(m => m !== meal.id);
          } else {
            c.meals.push(meal.id);
          }
          saveState();
          pill.classList.toggle('active');
        };
        toggles.appendChild(pill);
      });

      const name = document.createElement('span');
      name.className = 'candidate-name';
      name.textContent = c.name;

      const rm = document.createElement('button');
      rm.textContent = '删除';
      rm.className = 'remove-btn';
      rm.onclick = () => {
        state.candidates.splice(i, 1);
        saveState();
        renderSettings();
      };

      li.appendChild(toggles);
      li.appendChild(name);
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
      left.innerHTML = `${h.name}<span class="history-meta">${mealLabel(h.meal)} · ${date}</span>`;
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

function candidatesForMeal(meal) {
  return state.candidates.filter(c => c.meals.includes(meal));
}

function computeStats(meal) {
  return candidatesForMeal(meal).map(c => {
    const records = state.history.filter(h => h.name === c.name && h.meal === meal);
    return {
      name: c.name,
      up: records.filter(r => r.feedback === 'up').length,
      down: records.filter(r => r.feedback === 'down').length,
      meh: records.filter(r => r.feedback === 'meh').length,
      total: records.length
    };
  });
}

function recentNamesForMeal(meal, n) {
  return state.history.filter(h => h.meal === meal).slice(-n).map(h => h.name);
}

async function decide(mood) {
  if (!state.apiKey) {
    throw new Error('请先在设置中填入 Anthropic API Key');
  }

  const candidates = candidatesForMeal(currentMeal);
  if (candidates.length === 0) {
    throw new Error(`${mealLabel(currentMeal)}的候选清单是空的，去设置里标记或添加`);
  }

  const stats = computeStats(currentMeal);
  const recent = recentNamesForMeal(currentMeal, 5);
  const candidateNames = candidates.map(c => c.name);
  const meal = mealLabel(currentMeal);

  const statsText = stats.map(s => {
    if (s.total === 0) return `- ${s.name}（暂无反馈）`;
    return `- ${s.name}（喜欢 ${s.up}，还行 ${s.meh}，不要 ${s.down}）`;
  }).join('\n');

  const recentText = recent.length > 0 ? recent.join('、') : '无';

  const prompt = `你在帮用户决定今天的【${meal}】吃什么。从候选清单中挑一个最合适的。

用户当前心情/想法：${mood || '（未填写，自由发挥）'}

最近几次${meal}吃过的（尽量避免重复）：${recentText}

${meal}候选与历史反馈：
${statsText}

要求：
- 必须从候选清单中精确选一个名字
- 综合考虑当前心情、用户偏好、近期吃过的
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
    currentPick = {
      name: result.pick,
      reason: result.reason,
      mood,
      ts: Date.now(),
      meal: currentMeal
    };
    document.getElementById('pick').textContent = result.pick;
    document.getElementById('reason').textContent = result.reason;
    resultEl.hidden = false;
    document.querySelectorAll('.fb-btn').forEach(b => b.classList.remove('active'));

    state.history.push({
      name: result.pick,
      feedback: null,
      ts: currentPick.ts,
      mood,
      meal: currentMeal
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

function setMeal(meal) {
  if (currentMeal === meal) return;
  currentMeal = meal;
  currentPick = null;
  renderMealSelector();
  document.getElementById('result').hidden = true;
  document.getElementById('error').hidden = true;
}

document.addEventListener('DOMContentLoaded', () => {
  renderMealSelector();

  document.querySelectorAll('.meal-tab').forEach(tab => {
    tab.addEventListener('click', () => setMeal(tab.dataset.meal));
  });

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
    state.candidates.push({ name, meals: ALL_MEAL_IDS.slice() });
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
