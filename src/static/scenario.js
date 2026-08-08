const API = '';
const STEP_ORDER = ['background', 'formation', 'task', 'final'];
const STEP_NAMES = {
  background: '背景与环境',
  formation: '兵力编成',
  task: '战术与任务',
  final: '完整定稿',
};
const STATUS_NAMES = {
  empty: '未开始',
  draft: '待生成',
  generating: '生成中',
  generated: '待确认',
  confirmed: '已确认',
  stale: '需重生成',
  failed: '生成失败',
};
const DEFAULT_OPTIONS = {
  terrain_types: ['海岛', '沿海', '城市', '山地', '高原', '平原', '丘陵', '森林', '荒漠', '河网', '湖泊'],
  seasons: ['春', '夏', '秋', '冬', '雨季', '旱季'],
  operation_contexts: ['演训', '危机', '对抗', '其他'],
  scenario_scales: ['战区/战役', '师旅级', '营级及以下', '自定义'],
  branches: ['陆军', '海军', '空军', '火箭军', '无人系统', '电子对抗', '后勤保障'],
  roles: ['进攻', '防御', '机动', '保障', '自定义'],
  levels: ['campaign', 'tactical'],
  action_types: ['进攻', '防御', '机动', '保障', '侦察', '对抗'],
  task_types: ['联合火力打击', '区域防御', '跨区机动', '侦察监视', '要点控制', '综合保障'],
};
let scenarioOptions = {...DEFAULT_OPTIONS};

const App = {
  scenarios: [],
  current: null,
  step: 'background',
  generating: false,
  page: 'workspace',
  locationSearch: {
    query: '',
    selected: null,
    candidates: [],
    state: 'idle',
    message: '',
    timer: null,
    controller: null,
    requestId: 0,
  },

  async init() {
    this.bind();
    await Promise.all([this.checkHealth(), this.loadOptions()]);
    await this.loadScenarios();
    await KnowledgeApp.init();
  },

  bind() {
    document.querySelectorAll('.top-tab').forEach((button) => {
      button.addEventListener('click', () => this.switchPage(button.dataset.page));
    });
    document.getElementById('new-project').addEventListener('click', () => this.openModal('project-modal'));
    document.getElementById('empty-new-project').addEventListener('click', () => this.openModal('project-modal'));
    document.getElementById('empty-create').addEventListener('click', () => this.openModal('project-modal'));
    document.getElementById('create-project').addEventListener('click', () => this.createScenario());
    document.getElementById('delete-current').addEventListener('click', () => this.openModal('delete-modal'));
    document.getElementById('confirm-delete').addEventListener('click', () => this.deleteCurrent());
    document.getElementById('save-input').addEventListener('click', () => this.saveInput());
    document.getElementById('generate-step').addEventListener('click', () => this.generate('generate'));
    document.getElementById('confirm-step').addEventListener('click', () => this.confirm());
    document.getElementById('revise-step').addEventListener('click', () => this.openModal('revision-modal'));
    document.getElementById('submit-revision').addEventListener('click', () => this.submitRevision());
    document.getElementById('project-title').addEventListener('keydown', (event) => {
      if (event.key === 'Enter') this.createScenario();
    });
    document.querySelectorAll('[data-close-modal]').forEach((button) => {
      button.addEventListener('click', () => button.closest('.modal').classList.add('hidden'));
    });
    document.querySelectorAll('.modal').forEach((modal) => {
      modal.addEventListener('click', (event) => {
        if (event.target === modal) modal.classList.add('hidden');
      });
    });
  },

  async checkHealth() {
    try {
      const response = await fetch(`${API}/api/health`);
      if (!response.ok) throw new Error();
    } catch {
      document.getElementById('health-status').innerHTML = '<span class="status-dot offline"></span>服务不可用';
    }
  },

  async loadOptions() {
    try {
      const response = await fetch(`${API}/api/scenario-options`);
      if (!response.ok) throw new Error();
      const loaded = await response.json();
      scenarioOptions = {...DEFAULT_OPTIONS, ...loaded};
    } catch {
      scenarioOptions = {...DEFAULT_OPTIONS};
    }
  },

  async loadScenarios(selectId = null) {
    try {
      const response = await fetch(`${API}/api/scenarios`);
      if (!response.ok) throw new Error();
      this.scenarios = await response.json();
    } catch {
      this.scenarios = [];
      toast('项目列表加载失败', 'error');
    }
    renderProjectList(this.scenarios, selectId || this.current?.id);
    document.getElementById('project-empty').classList.toggle('hidden', this.scenarios.length > 0);
    if (this.scenarios.length === 0) {
      this.current = null;
      showEmptyWorkspace();
      return;
    }
    const id = selectId || this.current?.id || this.scenarios[0].id;
    await this.selectScenario(id);
  },

  async selectScenario(id) {
    try {
      const response = await fetch(`${API}/api/scenarios/${encodeURIComponent(id)}`);
      if (!response.ok) throw new Error();
      this.current = await response.json();
    } catch {
      toast('项目读取失败', 'error');
      return;
    }
    renderProjectList(this.scenarios, id);
    showScenarioWorkspace();
    const available = this.current.steps
      .filter((item) => item.status !== 'empty' || Object.keys(item.input || {}).length)
      .map((item) => item.step_type);
    if (!available.includes(this.step)) this.step = this.current.current_step || 'background';
    renderWorkspace();
  },

  switchPage(page) {
    this.page = page;
    document.querySelectorAll('.top-tab').forEach((button) => {
      button.classList.toggle('active', button.dataset.page === page);
    });
    document.getElementById('workspace-page').classList.toggle('hidden', page !== 'workspace');
    document.getElementById('knowledge-page').classList.toggle('hidden', page !== 'knowledge');
    if (page === 'knowledge') KnowledgeApp.loadBases();
  },

  openModal(id) {
    const modal = document.getElementById(id);
    modal.classList.remove('hidden');
    const field = modal.querySelector('input, textarea, select');
    if (field) setTimeout(() => field.focus(), 0);
  },

  async createScenario() {
    const title = document.getElementById('project-title').value.trim();
    if (!title) {
      toast('请输入项目名称', 'error');
      return;
    }
    try {
      const response = await fetch(`${API}/api/scenarios`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({title}),
      });
      if (!response.ok) throw new Error();
      const scenario = await response.json();
      document.getElementById('project-modal').classList.add('hidden');
      document.getElementById('project-title').value = '';
      this.step = 'background';
      await this.loadScenarios(scenario.id);
      toast('项目已创建', 'success');
    } catch {
      toast('项目创建失败', 'error');
    }
  },

  async deleteCurrent() {
    if (!this.current) return;
    try {
      const response = await fetch(`${API}/api/scenarios/${encodeURIComponent(this.current.id)}`, {method: 'DELETE'});
      if (!response.ok) throw new Error();
      document.getElementById('delete-modal').classList.add('hidden');
      this.current = null;
      await this.loadScenarios();
      toast('项目已删除', 'success');
    } catch {
      toast('项目删除失败', 'error');
    }
  },

  async saveInput({silent = false} = {}) {
    if (!this.current || this.step === 'final') return false;
    const data = readForm(this.step);
    if (!data) return false;
    try {
      const response = await fetch(`${API}/api/scenarios/${this.current.id}/steps/${this.step}/input`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({input: data}),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error?.message || validationMessage(body) || '保存失败');
      this.current = body;
      renderWorkspace();
      if (!silent) toast('输入已保存', 'success');
      return true;
    } catch (error) {
      toast(error.message, 'error');
      return false;
    }
  },

  async generate(mode, extra = {}) {
    if (!this.current || this.generating) return;
    const stepBefore = this.step;
    if (stepBefore !== 'final' && !(await this.saveInput({silent: true}))) return;
    const record = this.current.steps.find((item) => item.step_type === stepBefore) || {};
    if (mode === 'generate' && record.current_version) mode = 'regenerate';
    const payload = {
      mode,
      request_id: `${this.current.id}-${stepBefore}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      ...extra,
    };
    this.generating = true;
    renderWorkspace();
    clearResult();
    try {
      const url = stepBefore === 'final'
        ? `${API}/api/scenarios/${this.current.id}/finalize`
        : `${API}/api/scenarios/${this.current.id}/steps/${stepBefore}/generate`;
      const response = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const body = await response.json();
        throw new Error(body.error?.message || '生成前置校验失败');
      }
      await consumeNdjson(response, handleEvent);
      const refreshed = await fetch(`${API}/api/scenarios/${this.current.id}`);
      if (refreshed.ok) this.current = await refreshed.json();
    } catch (error) {
      showResultError(error.message);
      toast('生成未完成，已有结果已保留', 'error');
      const refreshed = await fetch(`${API}/api/scenarios/${this.current.id}`);
      if (refreshed.ok) this.current = await refreshed.json();
    } finally {
      this.generating = false;
      renderWorkspace();
    }
  },

  async confirm() {
    const record = this.current?.steps.find((item) => item.step_type === this.step);
    if (!record?.current_version) return;
    try {
      const response = await fetch(`${API}/api/scenarios/${this.current.id}/steps/${this.step}/confirm`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({version: record.current_version}),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error?.message || '确认失败');
      this.current = body;
      if (this.step !== 'final') this.step = STEP_ORDER[STEP_ORDER.indexOf(this.step) + 1];
      renderWorkspace();
      toast('步骤已确认', 'success');
    } catch (error) {
      toast(error.message, 'error');
    }
  },

  async submitRevision() {
    const instruction = document.getElementById('revision-text').value.trim();
    const record = this.current?.steps.find((item) => item.step_type === this.step);
    if (!instruction || !record?.current_version) {
      toast('请填写修改意见', 'error');
      return;
    }
    document.getElementById('revision-modal').classList.add('hidden');
    document.getElementById('revision-text').value = '';
    await this.generate('revise', {
      base_version: record.current_version,
      revision_instruction: instruction,
    });
  },
};

function showEmptyWorkspace() {
  document.getElementById('workspace-empty').classList.remove('hidden');
  document.getElementById('scenario-workspace').classList.add('hidden');
}

function showScenarioWorkspace() {
  document.getElementById('workspace-empty').classList.add('hidden');
  document.getElementById('scenario-workspace').classList.remove('hidden');
}

function renderProjectList(items, activeId) {
  const list = document.getElementById('project-list');
  list.innerHTML = items.map((scenario) => `
    <button class="project-item ${scenario.id === activeId ? 'active' : ''}" data-id="${escapeAttr(scenario.id)}">
      <span class="project-item-title">${escapeHtml(scenario.title)}</span>
      <span class="project-item-state">${escapeHtml(scenario.status || 'active')}</span>
    </button>`).join('');
  list.querySelectorAll('.project-item').forEach((button) => {
    button.addEventListener('click', () => App.selectScenario(button.dataset.id));
  });
}

function renderWorkspace() {
  if (!App.current) return;
  document.getElementById('scenario-title').textContent = App.current.title;
  renderStepper();
  renderSummary();
  renderForm();
  renderResult();
}

function renderStepper() {
  const container = document.getElementById('stepper');
  container.innerHTML = STEP_ORDER.map((step, index) => {
    const record = App.current.steps.find((item) => item.step_type === step) || {};
    const open = index === 0
      || App.current.steps.slice(0, index).every((item) => item.status === 'confirmed')
      || record.status !== 'empty';
    return `<button class="step-tab ${step === App.step ? 'active' : ''}" data-step="${step}" ${open && !App.generating ? '' : 'disabled'}>
      <span class="step-tab-index">0${index + 1}</span>
      <span class="step-tab-name">${STEP_NAMES[step]}</span>
      <span class="step-tab-state">${STATUS_NAMES[record.status] || '未开始'}</span>
    </button>`;
  }).join('');
  container.querySelectorAll('.step-tab').forEach((button) => {
    button.addEventListener('click', () => {
      App.step = button.dataset.step;
      renderWorkspace();
    });
  });
}

function renderSummary() {
  const confirmed = App.current.steps.filter((item) => item.status === 'confirmed');
  document.getElementById('summary-content').innerHTML = confirmed.length
    ? confirmed.map((item) => `<div class="summary-block">
        <div class="summary-step">${STEP_NAMES[item.step_type]} · V${item.confirmed_version}</div>
        <div class="summary-text">${escapeHtml(item.current_output || '已确认，暂无摘要')}</div>
      </div>`).join('')
    : '<span class="muted">确认步骤后显示摘要。</span>';
}

function renderForm() {
  const record = App.current.steps.find((item) => item.step_type === App.step) || {};
  document.getElementById('step-title').textContent = STEP_NAMES[App.step];
  document.getElementById('step-kicker').textContent = `STEP ${STEP_ORDER.indexOf(App.step) + 1}`;
  const badge = document.getElementById('step-status');
  badge.textContent = STATUS_NAMES[record.status] || '未开始';
  badge.className = `state-badge ${record.status || ''}`;

  const confirmed = App.current.steps.filter((item) => (
    item.status === 'confirmed' && STEP_ORDER.indexOf(item.step_type) < STEP_ORDER.indexOf(App.step)
  ));
  const context = document.getElementById('confirmed-context');
  context.classList.toggle('hidden', !confirmed.length);
  context.textContent = confirmed.map((item) => (
    `${STEP_NAMES[item.step_type]}（V${item.confirmed_version}）：\n${item.current_output || '已确认'}`
  )).join('\n\n');

  const form = document.getElementById('step-form');
  if (App.step === 'background') {
    syncLocationSearch(record.input || {});
    form.innerHTML = backgroundForm(record.input || {});
  } else {
    cancelLocationSearch();
    if (App.step === 'formation') form.innerHTML = formationForm(record.input || {});
    else if (App.step === 'task') form.innerHTML = taskForm(record.input || {});
    else form.innerHTML = '<div class="form-hint">前三个阶段确认后，生成完整定稿。</div>';
  }
  bindDynamicFormControls();

  document.getElementById('save-input').disabled = App.generating || App.step === 'final';
  const finalReady = App.current.steps.slice(0, 3).every((item) => item.status === 'confirmed');
  document.getElementById('generate-step').disabled = App.generating || (App.step === 'final' && !finalReady);
  document.getElementById('generate-step').textContent = App.step === 'final'
    ? '生成最终定稿'
    : record.current_version ? '重新生成草案' : '生成草案';
  document.getElementById('confirm-step').disabled = App.generating || record.status !== 'generated' || !record.current_version;
  document.getElementById('revise-step').disabled = App.generating || !record.current_version;
}

function backgroundForm(value) {
  const weather = value.weather || {};
  return `<div class="form-grid">
    <fieldset class="field full"><legend>地点模式</legend><div class="choice-row">
      ${radioChoice('location_mode', 'terrain_template', '地理类型模板', value.location_mode !== 'exact_location')}
      ${radioChoice('location_mode', 'exact_location', '指定真实地点', value.location_mode === 'exact_location')}
    </div></fieldset>
    <div id="exact-location-fields" class="field full location-search">
      <label for="location-query">地址搜索</label>
      <input id="location-query" name="location_query" maxlength="200" autocomplete="off" value="${escapeAttr(App.locationSearch.query)}" placeholder="输入地点名称">
      <div id="location-selected"></div>
      <div id="location-search-status" class="location-search-status" aria-live="polite"></div>
      <div id="location-results" class="location-results" role="listbox" aria-label="地点候选"></div>
    </div>
    <fieldset id="terrain-template-fields" class="field full"><legend>地理类型</legend><div class="choice-row">
      ${withSavedOptions(scenarioOptions.terrain_types, value.terrain_types).map((item) => checkChoice('terrain_types', item, value.terrain_types?.includes(item))).join('')}
    </div></fieldset>
    ${selectField('season', '季节', scenarioOptions.seasons, value.season)}
    ${selectField('operation_context', '行动背景', scenarioOptions.operation_contexts, value.operation_context)}
    ${inputField('time_condition', '时间条件', value.time_condition, 100, '日期、月份、昼夜条件或不指定')}
    ${selectField('weather_mode', '气象模式', ['inferred', 'manual'], value.weather_mode, {'inferred': '根据地点/地理类型推定', 'manual': '手动设置'})}
    <div id="manual-weather" class="field full manual-weather"><div class="subsection-title">手动气象</div><div class="form-grid">
      ${inputField('weather_temperature', '温度范围', weather.temperature, 100, '例如：-5°C 至 3°C')}
      ${inputField('weather_precipitation', '降水', weather.precipitation, 100, '例如：小雪')}
      ${inputField('weather_wind', '风况', weather.wind, 100, '例如：西北风 4-5 级')}
      ${inputField('weather_visibility', '能见度', weather.visibility, 100, '例如：2-5 千米')}
      <div class="field full">${inputField('weather_special', '特殊天气', weather.special, 200, '例如：局地结冰').replace(/^<div class="field">|<\/div>$/g, '')}</div>
    </div></div>
    <div class="field full"><label for="custom_requirements">其他要求 <span class="form-hint">最多 1,000 字</span></label><textarea id="custom_requirements" name="custom_requirements" maxlength="1000">${escapeHtml(value.custom_requirements || '')}</textarea></div>
  </div>`;
}

function formationForm(value) {
  return `${selectField('scenario_scale', '想定规模', scenarioOptions.scenario_scales, value.scenario_scale)}
    ${sideForm('red', '红方', value.red || {})}
    ${sideForm('blue', '蓝方', value.blue || {})}`;
}

function sideForm(side, label, value) {
  return `<fieldset class="field full side-field"><legend>${label}编成与装备</legend><div class="form-grid">
    ${selectField(`${side}_role`, '角色', scenarioOptions.roles, value.role)}
    ${inputField(`${side}_echelon`, '编成层级', value.echelon, 100, '例如：合成旅')}
    <fieldset class="field full"><legend>军兵种（多选）</legend><div class="choice-row">
      ${withSavedOptions(scenarioOptions.branches, value.branches).map((item) => checkChoice(`${side}_branches`, item, value.branches?.includes(item))).join('')}
    </div></fieldset>
    ${inputField(`${side}_approximate_scale`, '大致规模', value.approximate_scale, 200, '可留空，由知识库提供建议')}
    ${inputField(`${side}_weapons`, '武器装备', (value.weapons || []).join('、'), 500, '用顿号分隔，未指定由知识库建议')}
    ${inputField(`${side}_initial_deployment`, '初始部署方式', value.initial_deployment, 500)}
    ${inputField(`${side}_reserve_requirements`, '预备队要求', value.reserve_requirements, 500)}
    <div class="field full">${inputField(`${side}_support_requirements`, '保障要求', value.support_requirements, 500).replace(/^<div class="field">|<\/div>$/g, '')}</div>
    <div class="field full"><label for="${side}_custom_requirements">其他要求 <span class="form-hint">最多 1,000 字</span></label><textarea id="${side}_custom_requirements" name="${side}_custom_requirements" maxlength="1000">${escapeHtml(value.custom_requirements || '')}</textarea></div>
  </div></fieldset>`;
}

function taskForm(value) {
  return `<div class="form-grid">
    <fieldset class="field full"><legend>任务层级</legend><div class="choice-row">
      ${radioChoice('level', 'campaign', '战役级', value.level !== 'tactical')}
      ${radioChoice('level', 'tactical', '战术级', value.level === 'tactical')}
    </div></fieldset>
    <div class="field"><label for="red_objective">红方目标</label><textarea id="red_objective" name="red_objective" maxlength="1000">${escapeHtml(value.red_objective || '')}</textarea></div>
    <div class="field"><label for="blue_objective">蓝方目标</label><textarea id="blue_objective" name="blue_objective" maxlength="1000">${escapeHtml(value.blue_objective || '')}</textarea></div>
    <fieldset class="field full"><legend>行动类型（多选）</legend><div class="choice-row">
      ${withSavedOptions(scenarioOptions.action_types, value.action_types).map((item) => checkChoice('action_types', item, value.action_types?.includes(item))).join('')}
    </div></fieldset>
    <fieldset class="field full"><legend>任务类型（多选）</legend><div class="choice-row">
      ${withSavedOptions(scenarioOptions.task_types, value.task_types).map((item) => checkChoice('task_types', item, value.task_types?.includes(item))).join('')}
    </div></fieldset>
    <div class="field full"><label for="phase_template">阶段模板</label><textarea id="phase_template" name="phase_template" maxlength="500">${escapeHtml(value.phase_template || '')}</textarea></div>
    ${inputField('trigger_conditions', '触发条件', (value.trigger_conditions || []).join('、'), 500, '多个条件用顿号分隔')}
    ${inputField('termination_conditions', '终止条件', (value.termination_conditions || []).join('、'), 500, '多个条件用顿号分隔')}
    ${inputField('coordination_focus', '协同重点', (value.coordination_focus || []).join('、'), 500, '多个重点用顿号分隔')}
    ${inputField('constraints', '限制条件', (value.constraints || []).join('、'), 500, '多个条件用顿号分隔')}
    <div class="field full"><label for="custom_requirements">其他要求 <span class="form-hint">最多 1,000 字</span></label><textarea id="custom_requirements" name="custom_requirements" maxlength="1000">${escapeHtml(value.custom_requirements || '')}</textarea></div>
  </div>`;
}

function bindDynamicFormControls() {
  const weatherMode = document.querySelector('[name=weather_mode]');
  if (weatherMode) {
    const updateWeather = () => {
      document.getElementById('manual-weather').classList.toggle('hidden', weatherMode.value !== 'manual');
    };
    weatherMode.addEventListener('change', updateWeather);
    updateWeather();
  }
  const locationModes = document.querySelectorAll('[name=location_mode]');
  if (locationModes.length) {
    const updateLocationMode = () => {
      const exact = checkedValue(document.getElementById('step-form'), 'location_mode') === 'exact_location';
      document.getElementById('exact-location-fields').classList.toggle('hidden', !exact);
      document.getElementById('terrain-template-fields').classList.toggle('hidden', exact);
    };
    locationModes.forEach((input) => input.addEventListener('change', updateLocationMode));
    document.getElementById('location-query').addEventListener('input', onLocationQueryInput);
    updateLocationMode();
    renderLocationSearch();
  }
}

function syncLocationSearch(input) {
  cancelLocationSearch();
  const selected = input.location_mode === 'exact_location' ? input.location || null : null;
  App.locationSearch.query = selected?.display_name || '';
  App.locationSearch.selected = selected;
  App.locationSearch.candidates = [];
  App.locationSearch.state = selected ? 'selected' : 'idle';
  App.locationSearch.message = '';
}

function cancelLocationSearch() {
  const search = App.locationSearch;
  if (search.timer) clearTimeout(search.timer);
  if (search.controller) search.controller.abort();
  search.timer = null;
  search.controller = null;
  search.requestId += 1;
}

function onLocationQueryInput(event) {
  const search = App.locationSearch;
  cancelLocationSearch();
  search.query = event.target.value;
  if (search.selected && search.query !== search.selected.display_name) search.selected = null;
  search.candidates = [];
  const query = search.query.trim();
  if (query.length < 2) {
    search.state = query ? 'short' : 'idle';
    search.message = query ? '搜索词至少需要 2 个字符' : '';
    renderLocationSearch();
    return;
  }
  search.state = 'debouncing';
  search.message = '';
  const requestId = search.requestId;
  search.timer = setTimeout(() => searchLocations(query, requestId), 500);
  renderLocationSearch();
}

async function searchLocations(query, requestId) {
  const search = App.locationSearch;
  if (requestId !== search.requestId) return;
  search.state = 'loading';
  search.message = '正在搜索地点...';
  search.controller = new AbortController();
  renderLocationSearch();
  try {
    const response = await fetch(`${API}/api/locations/search?q=${encodeURIComponent(query)}`, {
      signal: search.controller.signal,
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error?.message || '地址服务不可用');
    if (requestId !== search.requestId) return;
    search.candidates = body;
    search.state = body.length ? 'results' : 'empty';
    search.message = body.length ? '' : '未找到匹配地点';
  } catch (error) {
    if (error.name === 'AbortError' || requestId !== search.requestId) return;
    search.candidates = [];
    search.state = 'error';
    search.message = error.message || '地址服务不可用';
  } finally {
    if (requestId === search.requestId) search.controller = null;
    renderLocationSearch();
  }
}

function renderLocationSearch() {
  const selectedContainer = document.getElementById('location-selected');
  const status = document.getElementById('location-search-status');
  const results = document.getElementById('location-results');
  if (!selectedContainer || !status || !results) return;
  const search = App.locationSearch;
  selectedContainer.innerHTML = search.selected ? `<div class="location-selected">
    <div><strong>${escapeHtml(search.selected.display_name)}</strong><span>${escapeHtml(locationMeta(search.selected))}</span></div>
    <button type="button" class="icon-button location-clear" title="清除地点" aria-label="清除地点">×</button>
  </div>` : '';
  selectedContainer.querySelector('.location-clear')?.addEventListener('click', clearSelectedLocation);
  status.textContent = search.message;
  status.className = `location-search-status ${search.state === 'error' ? 'error' : ''}`;
  results.innerHTML = search.state === 'results' ? search.candidates.map((location, index) => `
    <button type="button" class="location-result" data-index="${index}" role="option">
      <strong>${escapeHtml(location.display_name)}</strong>
      <span>${escapeHtml(locationMeta(location))}</span>
    </button>`).join('') : '';
  results.querySelectorAll('.location-result').forEach((button) => {
    button.addEventListener('click', () => selectLocation(Number(button.dataset.index)));
  });
}

function selectLocation(index) {
  const location = App.locationSearch.candidates[index];
  if (!location) return;
  cancelLocationSearch();
  App.locationSearch.selected = location;
  App.locationSearch.query = location.display_name;
  App.locationSearch.candidates = [];
  App.locationSearch.state = 'selected';
  App.locationSearch.message = '';
  document.getElementById('location-query').value = location.display_name;
  renderLocationSearch();
}

function clearSelectedLocation() {
  cancelLocationSearch();
  App.locationSearch.selected = null;
  App.locationSearch.query = '';
  App.locationSearch.candidates = [];
  App.locationSearch.state = 'idle';
  App.locationSearch.message = '';
  document.getElementById('location-query').value = '';
  document.getElementById('location-query').focus();
  renderLocationSearch();
}

function locationMeta(location) {
  const regions = [location.country, location.admin1, location.admin2].filter(Boolean);
  const coordinates = `${Number(location.latitude).toFixed(4)}, ${Number(location.longitude).toFixed(4)}`;
  return [...new Set(regions)].join(' · ') + `${regions.length ? ' · ' : ''}${coordinates}`;
}

function readForm(step) {
  const form = document.getElementById('step-form');
  if (step === 'background') {
    const locationMode = checkedValue(form, 'location_mode');
    let terrainTypes = checkedValues(form, 'terrain_types');
    let location = null;
    if (locationMode === 'exact_location' && !App.locationSearch.selected) {
      toast('请从地址搜索结果中选择一个地点', 'error');
      return null;
    }
    if (locationMode === 'exact_location') {
      location = App.locationSearch.selected;
      terrainTypes = [];
    } else if (!terrainTypes.length) {
      toast('请至少选择一种地理类型', 'error');
      return null;
    }
    const weatherMode = fieldValue(form, 'weather_mode');
    let weather = null;
    if (weatherMode === 'manual') {
      weather = compactObject({
        temperature: fieldValue(form, 'weather_temperature'),
        precipitation: fieldValue(form, 'weather_precipitation'),
        wind: fieldValue(form, 'weather_wind'),
        visibility: fieldValue(form, 'weather_visibility'),
        special: fieldValue(form, 'weather_special'),
      });
      if (!Object.keys(weather).length) {
        toast('手动气象模式下请至少填写一项气象条件', 'error');
        return null;
      }
    }
    return {
      location_mode: locationMode,
      location,
      terrain_types: terrainTypes,
      season: fieldValue(form, 'season'),
      weather_mode: weatherMode,
      weather,
      time_condition: fieldValue(form, 'time_condition') || null,
      operation_context: fieldValue(form, 'operation_context'),
      custom_requirements: fieldValue(form, 'custom_requirements'),
    };
  }
  if (step === 'formation') {
    const readSide = (side, label) => {
      const branches = checkedValues(form, `${side}_branches`);
      const echelon = fieldValue(form, `${side}_echelon`);
      if (!branches.length || !echelon) {
        toast(`请填写${label}编成层级并至少选择一个军兵种`, 'error');
        return null;
      }
      return {
        role: fieldValue(form, `${side}_role`),
        branches,
        echelon,
        approximate_scale: fieldValue(form, `${side}_approximate_scale`) || null,
        weapons: splitList(fieldValue(form, `${side}_weapons`)),
        initial_deployment: fieldValue(form, `${side}_initial_deployment`) || null,
        reserve_requirements: fieldValue(form, `${side}_reserve_requirements`) || null,
        support_requirements: fieldValue(form, `${side}_support_requirements`) || null,
        custom_requirements: fieldValue(form, `${side}_custom_requirements`),
      };
    };
    const red = readSide('red', '红方');
    if (!red) return null;
    const blue = readSide('blue', '蓝方');
    if (!blue) return null;
    return {scenario_scale: fieldValue(form, 'scenario_scale'), red, blue};
  }
  const redObjective = fieldValue(form, 'red_objective');
  const blueObjective = fieldValue(form, 'blue_objective');
  const actionTypes = checkedValues(form, 'action_types');
  const taskTypes = checkedValues(form, 'task_types');
  if (!redObjective || !blueObjective || !actionTypes.length || !taskTypes.length) {
    toast('请填写双方目标，并至少选择一种行动类型和任务类型', 'error');
    return null;
  }
  return {
    level: checkedValue(form, 'level'),
    red_objective: redObjective,
    blue_objective: blueObjective,
    action_types: actionTypes,
    task_types: taskTypes,
    phase_template: fieldValue(form, 'phase_template') || null,
    trigger_conditions: splitList(fieldValue(form, 'trigger_conditions')),
    termination_conditions: splitList(fieldValue(form, 'termination_conditions')),
    coordination_focus: splitList(fieldValue(form, 'coordination_focus')),
    constraints: splitList(fieldValue(form, 'constraints')),
    custom_requirements: fieldValue(form, 'custom_requirements'),
  };
}

function renderResult() {
  const record = App.current.steps.find((item) => item.step_type === App.step) || {};
  if (record.status !== 'failed') document.getElementById('result-error').classList.add('hidden');
  document.getElementById('result-version').textContent = record.current_version ? `V${record.current_version}` : '';
  const output = document.getElementById('result-output');
  if (record.current_output) output.textContent = record.current_output;
  else if (!App.generating) output.innerHTML = '<span class="muted">填写表单后可直接保存或生成草案。</span>';
  document.getElementById('result-sources').innerHTML = (record.current_sources || []).map((source) => (
    `<span class="source-pill">${escapeHtml(source.backend || 'source')} · ${escapeHtml(source.category || 'knowledge')} · ${escapeHtml(source.id || '')}</span>`
  )).join('');
  if (!App.generating) document.getElementById('result-progress').classList.add('hidden');
}

function clearResult() {
  document.getElementById('result-output').textContent = '';
  document.getElementById('result-sources').innerHTML = '';
  document.getElementById('result-error').classList.add('hidden');
  document.getElementById('result-progress').classList.add('hidden');
}

function handleEvent(event) {
  if (event.type === 'progress') {
    const progress = document.getElementById('result-progress');
    progress.textContent = event.message || '正在生成';
    progress.classList.remove('hidden');
  } else if (event.type === 'source') {
    const source = document.createElement('span');
    source.className = 'source-pill';
    source.textContent = `${event.source.backend || 'source'} · ${event.source.category || 'knowledge'} · ${event.source.id || ''}`;
    document.getElementById('result-sources').appendChild(source);
  } else if (event.type === 'content') {
    document.getElementById('result-output').textContent += event.delta || '';
  } else if (event.type === 'error') {
    showResultError(event.message || '生成失败');
  } else if (event.type === 'done') {
    document.getElementById('result-version').textContent = `V${event.version}`;
    document.getElementById('result-progress').classList.add('hidden');
  }
}

async function consumeNdjson(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, {stream: true});
    const lines = buffer.split('\n');
    buffer = lines.pop();
    for (const line of lines) {
      if (line.trim()) onEvent(JSON.parse(line));
    }
  }
  buffer += decoder.decode();
  if (buffer.trim()) onEvent(JSON.parse(buffer));
}

function showResultError(message) {
  const error = document.getElementById('result-error');
  error.textContent = message;
  error.classList.remove('hidden');
}

const KnowledgeApp = {
  bases: [],
  selected: null,
  entries: [],
  pendingDelete: null,

  async init() {
    document.getElementById('refresh-kb').addEventListener('click', () => this.loadBases());
    document.getElementById('add-knowledge').addEventListener('click', () => this.openCreate());
    document.getElementById('submit-knowledge').addEventListener('click', () => this.create());
    document.getElementById('confirm-knowledge-delete').addEventListener('click', () => this.confirmRemove());
    await this.loadBases();
  },

  async loadBases() {
    try {
      const response = await fetch(`${API}/api/get_knowledge_bases`);
      if (!response.ok) throw new Error();
      this.bases = await response.json();
      if (!this.bases.some((item) => item.kb_id === this.selected)) this.selected = null;
    } catch {
      this.bases = [];
      this.selected = null;
      toast('知识库列表加载失败', 'error');
    }
    renderKbBases(this.bases, this.selected);
    if (this.selected) await this.loadEntries();
    else {
      this.entries = [];
      renderKnowledgeEntries();
    }
  },

  async select(id) {
    this.selected = id;
    renderKbBases(this.bases, id);
    await this.loadEntries();
  },

  async loadEntries() {
    if (!this.selected) return;
    document.getElementById('knowledge-list').innerHTML = '<div class="empty-state">正在加载...</div>';
    try {
      const response = await fetch(`${API}/api/get_knowledge?kb_id=${encodeURIComponent(this.selected)}`);
      if (!response.ok) throw new Error();
      this.entries = await response.json();
      renderKnowledgeEntries();
    } catch {
      this.entries = [];
      renderKnowledgeEntries();
      toast('知识条目加载失败', 'error');
    }
  },

  openCreate() {
    if (!this.bases.length) {
      toast('当前没有可用知识库', 'error');
      return;
    }
    const select = document.getElementById('knowledge-base-select');
    select.innerHTML = this.bases.map((base) => (
      `<option value="${escapeAttr(base.kb_id)}" ${base.kb_id === this.selected ? 'selected' : ''}>${escapeHtml(base.name)}</option>`
    )).join('');
    document.getElementById('knowledge-content').value = '';
    App.openModal('knowledge-modal');
  },

  async create() {
    const kbId = document.getElementById('knowledge-base-select').value;
    const content = document.getElementById('knowledge-content').value.trim();
    if (!kbId || !content) {
      toast('请选择知识库并填写知识内容', 'error');
      return;
    }
    const button = document.getElementById('submit-knowledge');
    button.disabled = true;
    try {
      const response = await fetch(`${API}/api/add_knowledge`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({kb_id: kbId, content}),
      });
      if (!response.ok) throw new Error();
      document.getElementById('knowledge-modal').classList.add('hidden');
      this.selected = kbId;
      renderKbBases(this.bases, kbId);
      await this.loadEntries();
      toast('知识已添加', 'success');
    } catch {
      toast('知识添加失败', 'error');
    } finally {
      button.disabled = false;
    }
  },

  async remove(id) {
    this.pendingDelete = id;
    App.openModal('knowledge-delete-modal');
  },

  async confirmRemove() {
    if (!this.pendingDelete) return;
    const id = this.pendingDelete;
    try {
      const response = await fetch(`${API}/api/delete_knowledge?k_id=${encodeURIComponent(id)}`, {method: 'DELETE'});
      const body = await response.json();
      if (!response.ok || !body.success) throw new Error();
      document.getElementById('knowledge-delete-modal').classList.add('hidden');
      this.pendingDelete = null;
      await this.loadEntries();
      toast('知识已删除', 'success');
    } catch {
      toast('知识删除失败', 'error');
    }
  },
};

function renderKbBases(items, activeId) {
  const list = document.getElementById('kb-list');
  list.innerHTML = items.length
    ? items.map((base) => `<button class="kb-item ${base.kb_id === activeId ? 'active' : ''}" data-id="${escapeAttr(base.kb_id)}">${escapeHtml(base.name)}</button>`).join('')
    : '<div class="empty-sidebar">暂无知识集合</div>';
  list.querySelectorAll('.kb-item').forEach((button) => {
    button.addEventListener('click', () => KnowledgeApp.select(button.dataset.id));
  });
}

function renderKnowledgeEntries() {
  const container = document.getElementById('knowledge-list');
  document.getElementById('kb-count').textContent = KnowledgeApp.selected ? `${KnowledgeApp.entries.length} 条` : '';
  if (!KnowledgeApp.selected) {
    container.innerHTML = '<div class="empty-state">选择左侧知识集合查看内容。</div>';
    return;
  }
  if (!KnowledgeApp.entries.length) {
    container.innerHTML = '<div class="empty-state">该知识集合暂无条目。</div>';
    return;
  }
  const base = KnowledgeApp.bases.find((item) => item.kb_id === KnowledgeApp.selected);
  container.innerHTML = KnowledgeApp.entries.map((entry) => `<article class="knowledge-card">
    <div class="knowledge-card-body"><div class="knowledge-card-content">${escapeHtml(entry.content)}</div>
    <div class="knowledge-card-meta">来源：${escapeHtml(base?.name || entry.kb_id)} · ${escapeHtml(entry.k_id)}</div></div>
    <button class="danger-button knowledge-delete" data-id="${escapeAttr(entry.k_id)}" title="删除知识">删除</button>
  </article>`).join('');
  container.querySelectorAll('.knowledge-delete').forEach((button) => {
    button.addEventListener('click', () => KnowledgeApp.remove(button.dataset.id));
  });
}

function selectField(name, label, options, selectedValue, labels = {}) {
  const availableOptions = withSavedOptions(options, selectedValue ? [selectedValue] : []);
  return `<div class="field"><label for="${name}">${label}</label><select id="${name}" name="${name}">
    ${availableOptions.map((option) => `<option value="${escapeAttr(option)}" ${option === selectedValue ? 'selected' : ''}>${escapeHtml(labels[option] || option)}</option>`).join('')}
  </select></div>`;
}

function withSavedOptions(options, saved = []) {
  return [...new Set([...(options || []), ...(saved || [])].filter(Boolean))];
}

function inputField(name, label, value = '', maxLength = 500, placeholder = '') {
  return `<div class="field"><label for="${name}">${label}</label><input id="${name}" name="${name}" maxlength="${maxLength}" value="${escapeAttr(value || '')}" placeholder="${escapeAttr(placeholder)}"></div>`;
}

function radioChoice(name, value, label, checked) {
  return `<label class="choice"><input type="radio" name="${name}" value="${escapeAttr(value)}" ${checked ? 'checked' : ''}>${escapeHtml(label)}</label>`;
}

function checkChoice(name, value, checked) {
  return `<label class="choice"><input type="checkbox" name="${name}" value="${escapeAttr(value)}" ${checked ? 'checked' : ''}>${escapeHtml(value)}</label>`;
}

function fieldValue(form, name) {
  return form.querySelector(`[name="${name}"]`)?.value.trim() || '';
}

function checkedValue(form, name) {
  return form.querySelector(`[name="${name}"]:checked`)?.value || '';
}

function checkedValues(form, name) {
  return [...form.querySelectorAll(`[name="${name}"]:checked`)].map((item) => item.value);
}

function splitList(value) {
  return value.split(/[、,，;；\n]/).map((item) => item.trim()).filter(Boolean);
}

function compactObject(value) {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item));
}

function validationMessage(body) {
  const detail = body?.detail;
  return Array.isArray(detail) ? detail.map((item) => item.msg).filter(Boolean).join('；') : '';
}

function escapeHtml(value) {
  const element = document.createElement('div');
  element.textContent = value ?? '';
  return element.innerHTML;
}

function escapeAttr(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function toast(message, type = 'info') {
  const element = document.createElement('div');
  element.className = `toast ${type}`;
  element.textContent = message;
  document.getElementById('toast-container').appendChild(element);
  setTimeout(() => element.remove(), 3200);
}

document.addEventListener('DOMContentLoaded', () => App.init());
