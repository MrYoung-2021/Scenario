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
const SCENARIO_STATUS_NAMES = {active: '进行中', finalized: '已定稿'};
const DEFAULT_OPTIONS = {
  terrain_types: ['海岛', '沿海', '城市', '山地', '高原', '平原', '丘陵', '森林', '荒漠', '河网', '湖泊'].map((value) => ({value, label: value, builtin: true})),
  seasons: ['春', '夏', '秋', '冬', '雨季', '旱季'],
  operation_contexts: ['演训', '危机', '对抗', '其他'],
  scenario_scales: ['战区/战役', '师旅级', '营级及以下', '自定义'],
  branches: ['陆军', '海军', '空军', '火箭军', '无人系统', '电子对抗', '后勤保障'],
  red_branches: ['陆军', '海军', '空军', '火箭军', '无人系统', '电子对抗', '后勤保障'],
  blue_branches: ['陆军', '海军', '空军', '海军陆战队', '太空军', '无人系统', '电子对抗', '后勤保障'],
  echelons: ['班', '排', '连', '营', '团', '旅', '师', '军', '战区'],
  weapon_categories: [],
};
let scenarioOptions = {...DEFAULT_OPTIONS};
let streamBuffer = '';
let markdownTimer = null;

const ERROR_MESSAGES = {
  INVALID_STEP_INPUT: '输入内容不符合要求，请检查必填项和长度限制',
  PREREQUISITE_NOT_CONFIRMED: '请先确认前置步骤',
  STEP_INPUT_REQUIRED: '请先保存当前步骤输入',
  GENERATION_IN_PROGRESS: '当前步骤正在生成，请稍候',
  GENERATION_FAILED: '生成失败，请稍后重试',
  VERSION_CONFLICT: '内容版本已变化，请刷新后重试',
  LOCATION_SERVICE_UNAVAILABLE: '地点服务暂时不可用',
  LOCATION_PROFILE_UNAVAILABLE: '典型地理气象资料暂时不可用，可继续手动设置气象',
};
const SOURCE_NAMES = {
  standard: '标准知识库', lightrag: 'LightRAG', environment: '环境知识',
  tactics_campaign: '战役战法', tactics_tactical: '战术战法', task: '任务知识',
  formation: '编成知识', weapon: '装备知识', expert: '专家知识', feedback: '反馈知识',
};

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
    profile: null,
    profileState: 'idle',
    timer: null,
    controller: null,
    requestId: 0,
  },
  recommendations: {state: 'idle', data: null, scenarioId: null, message: ''},
  weaponModal: {side: null},

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
    document.getElementById('confirm-weapon-selection').addEventListener('click', confirmWeaponSelection);
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
      scenarioOptions.terrain_types = (scenarioOptions.terrain_types || []).map((item) => (
        typeof item === 'string' ? {value: item, label: item, builtin: true} : item
      ));
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
    if (this.step === 'task') this.loadRecommendations();
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
      if (!response.ok) throw new Error(localizedError(body, '保存失败'));
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
        throw new Error(localizedError(body, '生成前置校验失败'));
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
      if (!response.ok) throw new Error(localizedError(body, '确认失败'));
      this.current = body;
      if (this.step !== 'final') this.step = STEP_ORDER[STEP_ORDER.indexOf(this.step) + 1];
      renderWorkspace();
      scrollWorkspaceToTop();
      if (this.step === 'task') this.loadRecommendations();
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

  async loadRecommendations(force = false) {
    if (!this.current || this.step !== 'task') return;
    const ready = this.current.steps.slice(0, 2).every((item) => item.status === 'confirmed');
    if (!ready) return;
    const state = this.recommendations;
    if (!force && state.scenarioId === this.current.id && ['loading', 'loaded'].includes(state.state)) return;
    state.state = 'loading';
    state.scenarioId = this.current.id;
    state.message = '';
    renderForm();
    try {
      const response = await fetch(`${API}/api/scenarios/${encodeURIComponent(this.current.id)}/tactic-recommendations`, {method: 'POST'});
      const body = await response.json();
      if (!response.ok) throw new Error(localizedError(body));
      state.data = body;
      state.state = 'loaded';
    } catch (error) {
      state.data = null;
      state.state = 'failed';
      state.message = error.message || '推荐加载失败';
    }
    renderForm();
  },
};

function scrollWorkspaceToTop() {
  window.scrollTo({top: 0, left: 0, behavior: 'auto'});
  document.documentElement.scrollTop = 0;
  document.body.scrollTop = 0;
}

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
      <span class="project-item-state">${escapeHtml(SCENARIO_STATUS_NAMES[scenario.status] || '进行中')}</span>
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
      if (App.step === 'task') App.loadRecommendations();
    });
  });
}

function renderSummary() {
  const confirmed = App.current.steps.filter((item) => item.status === 'confirmed');
  document.getElementById('summary-content').innerHTML = confirmed.length
    ? confirmed.map((item) => `<div class="summary-block">
        <div class="summary-step">${STEP_NAMES[item.step_type]} · V${item.confirmed_version}</div>
        <div class="summary-text">${renderMarkdown(item.current_output || '已确认，暂无摘要')}</div>
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
  context.innerHTML = confirmed.map((item) => (
    `<section><strong>${STEP_NAMES[item.step_type]}（V${item.confirmed_version}）</strong>${renderMarkdown(item.current_output || '已确认')}</section>`
  )).join('');

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
  const terrainOptions = scenarioOptions.terrain_types.map((item) => item.value);
  return `<div class="form-grid">
    <fieldset class="field full"><legend>地点模式</legend><div class="choice-row">
      ${radioChoice('location_mode', 'terrain_template', '地理类型模板', value.location_mode !== 'exact_location')}
      ${radioChoice('location_mode', 'exact_location', '指定真实地点', value.location_mode === 'exact_location')}
    </div></fieldset>
    <div id="exact-location-fields" class="field full location-search">
      <label for="location-query">地址搜索</label>
      <input id="location-query" name="location_query" maxlength="200" autocomplete="off" value="${escapeAttr(App.locationSearch.query)}" placeholder="输入地点名称">
      <div id="location-selected"></div>
      <div id="location-profile" class="location-profile" aria-live="polite"></div>
      <div id="location-search-status" class="location-search-status" aria-live="polite"></div>
      <div id="location-results" class="location-results" role="listbox" aria-label="地点候选"></div>
    </div>
    <fieldset id="terrain-template-fields" class="field full"><legend>地理类型</legend><div class="choice-row">
      ${withSavedOptions(terrainOptions, value.terrain_types).map((item) => checkChoice('terrain_types', item, value.terrain_types?.includes(item))).join('')}
    </div>${customListControl('custom_terrain_types', value.custom_terrain_types || [], '添加自定义地理类型')}</fieldset>
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
  const builtinWeapons = scenarioOptions.weapon_categories.flatMap((category) => category.elements || []);
  const branches = scenarioOptions[`${side}_branches`] || scenarioOptions.branches;
  const savedBranches = side === 'blue'
    ? (value.branches || []).filter((item) => item !== '火箭军')
    : value.branches;
  const customWeapons = withSavedOptions(
    value.custom_weapons || [],
    (value.weapons || []).filter((item) => !builtinWeapons.includes(item)),
  );
  return `<fieldset class="field full side-field"><legend>${label}编成与装备</legend><div class="form-grid">
    ${selectField(`${side}_echelon`, '编成层级', scenarioOptions.echelons, value.echelon)}
    <fieldset class="field full"><legend>军兵种（多选）</legend><div class="choice-row">
      ${withSavedOptions(branches, savedBranches).map((item) => checkChoice(`${side}_branches`, item, savedBranches?.includes(item))).join('')}
    </div></fieldset>
    ${inputField(`${side}_approximate_scale`, '大致规模', value.approximate_scale, 200, '可留空，由大模型生成；例如：约 3,000 人')}
    <fieldset class="field full weapon-selector"><legend>武器装备（多选）</legend>${weaponSelectionSummary(side, value.weapons || [], customWeapons)}</fieldset>
    ${inputField(`${side}_initial_deployment`, '初始部署方式', value.initial_deployment, 500, '可留空，由大模型生成；例如：沿主要通道梯次部署')}
    ${inputField(`${side}_reserve_requirements`, '预备队要求', value.reserve_requirements, 500, '可留空，由大模型生成；例如：保留一个机动营')}
    <div class="field full">${inputField(`${side}_support_requirements`, '保障要求', value.support_requirements, 500, '可留空，由大模型生成；例如：加强工程与卫勤保障').replace(/^<div class="field">|<\/div>$/g, '')}</div>
    <div class="field full"><label for="${side}_custom_requirements">其他要求 <span class="form-hint">最多 1,000 字</span></label><textarea id="${side}_custom_requirements" name="${side}_custom_requirements" maxlength="1000">${escapeHtml(value.custom_requirements || '')}</textarea></div>
  </div></fieldset>`;
}

function taskForm(value) {
  const recommendation = App.recommendations;
  const data = recommendation.data || {};
  return `<div class="form-grid">
    <div class="field full recommendation-status ${recommendation.state}">${recommendationStatus(recommendation)}</div>
    ${objectiveField('red_objective', '红方目标', value.red_objective || {}, data.red_objectives || [])}
    ${objectiveField('blue_objective', '蓝方目标', value.blue_objective || {}, data.blue_objectives || [])}
    ${tacticField('campaign_tactics', '战役战法', value.campaign_tactics || {}, data.campaign_tactics || [])}
    ${tacticField('tactical_tactics', '战术战法', value.tactical_tactics || {}, data.tactical_tactics || [])}
    ${inputField('trigger_conditions', '触发条件', (value.trigger_conditions || []).join('、'), 500, '可留空，由大模型生成；多个条件用顿号分隔')}
    ${inputField('termination_conditions', '终止条件', (value.termination_conditions || []).join('、'), 500, '可留空，由大模型生成；多个条件用顿号分隔')}
    ${inputField('coordination_focus', '协同重点', (value.coordination_focus || []).join('、'), 500, '可留空，由大模型生成；多个条件用顿号分隔')}
    ${inputField('constraints', '限制条件', (value.constraints || []).join('、'), 500, '可留空，由大模型生成；多个条件用顿号分隔')}
    <div class="field full"><label for="custom_requirements">其他要求 <span class="form-hint">最多 1,000 字</span></label><textarea id="custom_requirements" name="custom_requirements" maxlength="1000">${escapeHtml(value.custom_requirements || '')}</textarea></div>
  </div>`;
}

function weaponSelectionSummary(side, selected, customWeapons) {
  const values = uniqueValues([...(selected || []), ...(customWeapons || [])]);
  const names = values.length ? values.map((item) => `<span>${escapeHtml(item)}</span>`).join('') : '<span class="muted">尚未选择装备</span>';
  return `<div class="weapon-summary" data-weapon-summary="${escapeAttr(side)}">
    <div class="weapon-summary-toolbar"><button type="button" class="outline-button weapon-open" data-weapon-side="${escapeAttr(side)}">选择装备</button><strong data-weapon-count="${escapeAttr(side)}">已选择 ${values.length} 项</strong></div>
    <div class="weapon-summary-list" data-weapon-names="${escapeAttr(side)}">${names}</div>
    <div class="weapon-hidden-state" data-weapon-state="${escapeAttr(side)}">
      ${(selected || []).map((item) => `<input type="checkbox" class="weapon-hidden-checkbox" name="${escapeAttr(side)}_weapons" value="${escapeAttr(item)}" checked>`).join('')}
      ${(customWeapons || []).map((item) => `<input type="hidden" name="${escapeAttr(side)}_custom_weapons" value="${escapeAttr(item)}">`).join('')}
    </div>
  </div>`;
}

function weaponCategoryFields(selected) {
  if (!scenarioOptions.weapon_categories.length) return '<div class="form-hint">暂无系统装备选项，可直接添加自定义装备。</div>';
  return scenarioOptions.weapon_categories.map((category) => `<div class="weapon-category"><div class="form-hint">${escapeHtml(category.name)}</div><div class="choice-row weapon-option-row">
    ${(category.elements || []).map((item) => `<label class="choice weapon-option"><input type="checkbox" class="weapon-modal-option" value="${escapeAttr(item)}" ${selected.includes(item) ? 'checked' : ''}>${escapeHtml(item)}</label>`).join('')}
  </div></div>`).join('');
}

function openWeaponModal(side) {
  const state = document.querySelector(`[data-weapon-state="${CSS.escape(side)}"]`);
  if (!state) return;
  const selected = [...state.querySelectorAll(`input[name="${side}_weapons"]:checked`)].map((input) => input.value);
  const custom = [...state.querySelectorAll(`input[name="${side}_custom_weapons"]`)].map((input) => input.value);
  App.weaponModal.side = side;
  document.getElementById('weapon-modal-title').textContent = `${side === 'red' ? '红方' : '蓝方'}武器装备`;
  document.getElementById('weapon-modal-content').innerHTML = `${weaponCategoryFields(selected)}
    <div class="weapon-modal-custom"><label for="weapon-modal-custom-input">自定义武器装备</label><div id="weapon-modal-custom-items" class="custom-items">${custom.map((item) => weaponCustomItem(item)).join('')}</div><div class="custom-add-row"><input id="weapon-modal-custom-input" class="custom-add-input" maxlength="200" placeholder="添加自定义武器装备"><button type="button" id="weapon-modal-custom-add" class="outline-button">添加</button></div></div>`;
  bindWeaponCustomControls();
  App.openModal('weapon-modal');
}

function weaponCustomItem(value) {
  return `<span class="custom-item weapon-custom-item" data-value="${escapeAttr(value)}">${escapeHtml(value)}<button type="button" class="custom-remove weapon-custom-remove" aria-label="删除 ${escapeAttr(value)}">×</button></span>`;
}

function bindWeaponCustomControls() {
  const add = document.getElementById('weapon-modal-custom-add');
  const input = document.getElementById('weapon-modal-custom-input');
  if (!add || !input) return;
  const addCustom = () => {
    const value = input.value.trim();
    const items = document.getElementById('weapon-modal-custom-items');
    const current = [...items.querySelectorAll('.weapon-custom-item')].map((item) => item.dataset.value);
    if (!value || current.length >= 50 || current.some((item) => item.toLowerCase() === value.toLowerCase())) return;
    items.insertAdjacentHTML('beforeend', weaponCustomItem(value));
    input.value = '';
    bindWeaponCustomRemovers();
  };
  add.onclick = addCustom;
  input.onkeydown = (event) => {
    if (event.key === 'Enter') { event.preventDefault(); addCustom(); }
  };
  bindWeaponCustomRemovers();
}

function bindWeaponCustomRemovers() {
  document.querySelectorAll('.weapon-custom-remove').forEach((button) => {
    button.onclick = () => button.closest('.weapon-custom-item').remove();
  });
}

function confirmWeaponSelection() {
  const side = App.weaponModal.side;
  if (!side) return;
  const state = document.querySelector(`[data-weapon-state="${CSS.escape(side)}"]`);
  const options = [...document.querySelectorAll('.weapon-modal-option:checked')].map((input) => input.value);
  const custom = [...document.querySelectorAll('#weapon-modal-custom-items .weapon-custom-item')].map((item) => item.dataset.value);
  if (!state) return;
  state.innerHTML = `${options.map((item) => `<input type="checkbox" class="weapon-hidden-checkbox" name="${escapeAttr(side)}_weapons" value="${escapeAttr(item)}" checked>`).join('')}${custom.map((item) => `<input type="hidden" name="${escapeAttr(side)}_custom_weapons" value="${escapeAttr(item)}">`).join('')}`;
  updateWeaponSummary(side, [...options, ...custom]);
  document.getElementById('weapon-modal').classList.add('hidden');
}

function updateWeaponSummary(side, values) {
  const unique = uniqueValues(values);
  const names = document.querySelector(`[data-weapon-names="${CSS.escape(side)}"]`);
  const count = document.querySelector(`[data-weapon-count="${CSS.escape(side)}"]`);
  if (count) count.textContent = `已选择 ${unique.length} 项`;
  if (names) names.innerHTML = unique.length ? unique.map((item) => `<span>${escapeHtml(item)}</span>`).join('') : '<span class="muted">尚未选择装备</span>';
}

function recommendationStatus(value) {
  if (value.state === 'loading') return '正在加载战法推荐<span class="loading-dots"><i></i><i></i><i></i></span>';
  if (value.state === 'failed') return `${escapeHtml(value.message || '推荐加载失败')}，仍可使用自定义输入。`;
  if (value.state === 'loaded') {
    const count = Object.values(value.data || {}).filter(Array.isArray).reduce((sum, items) => sum + items.length, 0);
    return count ? `已加载 ${count} 条推荐` : '暂无匹配推荐，可使用自定义输入。';
  }
  return '确认背景与编成后加载推荐。';
}

function objectiveField(name, label, value, recommendations) {
  const selected = value.selected || [];
  const options = mergeRecommendationOptions(recommendations, selected);
  return `<fieldset class="field task-objective"><legend>${label}</legend><div class="recommendation-list">
    ${options.map((item) => recommendationChoice(`${name}_selected`, item, selected.includes(item.label))).join('')}
  </div><label for="${name}_custom" class="form-hint">自定义目标</label><textarea id="${name}_custom" name="${name}_custom" maxlength="1000" placeholder="可输入自定义目标">${escapeHtml(value.custom || '')}</textarea></fieldset>`;
}

function tacticField(name, label, value, recommendations) {
  const selected = value.selected || [];
  const options = mergeRecommendationOptions(recommendations, selected);
  return `<fieldset class="field full tactic-group"><legend>${label}（多选）</legend><div class="recommendation-list">
    ${options.map((item) => recommendationChoice(`${name}_selected`, item, selected.includes(item.label))).join('')}
  </div>${customListControl(`${name}_custom`, value.custom || [], `添加自定义${label}`)}</fieldset>`;
}

function mergeRecommendationOptions(recommendations, saved) {
  const mapped = recommendations.map((item) => ({...item, recommended: true}));
  saved.forEach((label) => {
    if (!mapped.some((item) => item.label === label)) mapped.push({label, content: '此前保存的选择', source: '历史选择', recommended: false});
  });
  return mapped;
}

function recommendationChoice(name, item, checked) {
  return `<label class="recommendation ${item.recommended ? 'recommended' : 'saved'}" title="来源：${escapeAttr(item.source || '未知')}"><input type="checkbox" name="${name}" value="${escapeAttr(item.label)}" ${checked ? 'checked' : ''}><span class="recommendation-body"><strong class="recommendation-name">${escapeHtml(item.label)}</strong><span class="recommendation-content">${escapeHtml(item.content || '暂无内容说明')}</span><small class="recommendation-source">${escapeHtml(item.source || '')}</small></span></label>`;
}

function customListControl(name, values, placeholder) {
  return `<div class="custom-list-control" data-name="${escapeAttr(name)}"><div class="custom-items">${uniqueValues(values).map((value) => `<span class="custom-item" data-value="${escapeAttr(value)}">${escapeHtml(value)}<button type="button" class="custom-remove" aria-label="删除 ${escapeAttr(value)}">×</button></span>`).join('')}</div><div class="custom-add-row"><input class="custom-add-input" maxlength="200" placeholder="${escapeAttr(placeholder)}"><button type="button" class="outline-button custom-add">添加</button></div></div>`;
}

function bindDynamicFormControls() {
  document.querySelectorAll('.weapon-open').forEach((button) => {
    button.onclick = () => openWeaponModal(button.dataset.weaponSide);
  });
  document.querySelectorAll('.custom-list-control').forEach((control) => {
    const add = () => {
      const input = control.querySelector('.custom-add-input');
      const value = input.value.trim();
      if (!value) return;
      const current = customListValues(control.dataset.name);
      if (current.length >= 50 || current.some((item) => item.toLowerCase() === value.toLowerCase())) {
        input.value = '';
        return;
      }
      control.querySelector('.custom-items').insertAdjacentHTML('beforeend', `<span class="custom-item" data-value="${escapeAttr(value)}">${escapeHtml(value)}<button type="button" class="custom-remove" aria-label="删除 ${escapeAttr(value)}">×</button></span>`);
      input.value = '';
      bindCustomRemovers(control);
    };
    control.querySelector('.custom-add')?.addEventListener('click', add);
    control.querySelector('.custom-add-input')?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') { event.preventDefault(); add(); }
    });
    bindCustomRemovers(control);
  });
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
  App.locationSearch.profile = selected ? input.location_profile || null : null;
  App.locationSearch.profileState = App.locationSearch.profile ? 'loaded' : 'idle';
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
  const profile = document.getElementById('location-profile');
  if (!selectedContainer || !status || !results || !profile) return;
  const search = App.locationSearch;
  selectedContainer.innerHTML = search.selected ? `<div class="location-selected">
    <div><strong>${escapeHtml(search.selected.display_name)}</strong><span>${escapeHtml(locationMeta(search.selected))}</span></div>
    <button type="button" class="icon-button location-clear" title="清除地点" aria-label="清除地点">×</button>
  </div>` : '';
  selectedContainer.querySelector('.location-clear')?.addEventListener('click', clearSelectedLocation);
  profile.innerHTML = renderLocationProfile(search);
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

async function selectLocation(index) {
  const location = App.locationSearch.candidates[index];
  if (!location) return;
  cancelLocationSearch();
  App.locationSearch.selected = location;
  App.locationSearch.query = location.display_name;
  App.locationSearch.candidates = [];
  App.locationSearch.state = 'selected';
  App.locationSearch.message = '';
  App.locationSearch.profile = null;
  App.locationSearch.profileState = 'loading';
  document.getElementById('location-query').value = location.display_name;
  renderLocationSearch();
  try {
    const season = fieldValue(document.getElementById('step-form'), 'season');
    const response = await fetch(`${API}/api/locations/profile`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({location, season: season || null}),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(localizedError(body));
    if (App.locationSearch.selected?.place_id !== location.place_id) return;
    App.locationSearch.profile = body;
    App.locationSearch.profileState = 'loaded';
  } catch (error) {
    if (App.locationSearch.selected?.place_id !== location.place_id) return;
    App.locationSearch.profileState = 'failed';
    App.locationSearch.message = error.message || '典型资料加载失败，可手动设置气象';
  }
  renderLocationSearch();
}

function clearSelectedLocation() {
  cancelLocationSearch();
  App.locationSearch.selected = null;
  App.locationSearch.query = '';
  App.locationSearch.candidates = [];
  App.locationSearch.state = 'idle';
  App.locationSearch.message = '';
  App.locationSearch.profile = null;
  App.locationSearch.profileState = 'idle';
  document.getElementById('location-query').value = '';
  document.getElementById('location-query').focus();
  renderLocationSearch();
}

function locationMeta(location) {
  const regions = [location.country, location.admin1, location.admin2].filter(Boolean);
  if (location.address && !regions.includes(location.address)) regions.push(location.address);
  const coordinates = `${Number(location.latitude).toFixed(4)}, ${Number(location.longitude).toFixed(4)}`;
  return [...new Set(regions)].join(' · ') + `${regions.length ? ' · ' : ''}${coordinates}`;
}

function renderLocationProfile(search) {
  if (!search.selected) return '';
  if (search.profileState === 'loading') return '<div class="profile-status">正在加载典型地理气象资料<span class="loading-dots"><i></i><i></i><i></i></span></div>';
  if (search.profileState === 'failed') return '<div class="profile-status error">资料加载失败，可继续保存地点并手动设置气象。</div>';
  if (!search.profile) return '';
  const geography = search.profile.geography || {};
  const climate = search.profile.climate || {};
  return `<div class="location-profile-card"><div><strong>典型地理</strong><p>${escapeHtml(geography.terrain || '暂无资料')}</p></div><div><strong>典型气象</strong><p>${escapeHtml(climate.seasonal_temperature || '暂无资料')}</p></div><small>${escapeHtml(search.profile.notice || '典型值')} · 来源：${escapeHtml(search.profile.source || '环境知识库')}</small></div>`;
}

function readForm(step) {
  const form = document.getElementById('step-form');
  if (step === 'background') {
    const locationMode = checkedValue(form, 'location_mode');
    let terrainTypes = checkedValues(form, 'terrain_types');
    let customTerrainTypes = customListValues('custom_terrain_types');
    let location = null;
    if (locationMode === 'exact_location' && !App.locationSearch.selected) {
      toast('请从地址搜索结果中选择一个地点', 'error');
      return null;
    }
    if (locationMode === 'exact_location') {
      location = App.locationSearch.selected;
      terrainTypes = [];
      customTerrainTypes = [];
    } else if (!terrainTypes.length && !customTerrainTypes.length) {
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
      location_profile: location ? App.locationSearch.profile : null,
      terrain_types: terrainTypes,
      custom_terrain_types: customTerrainTypes,
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
        branches,
        echelon,
        approximate_scale: fieldValue(form, `${side}_approximate_scale`) || null,
        weapons: checkedValues(form, `${side}_weapons`),
        custom_weapons: hiddenValues(form, `${side}_custom_weapons`),
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
  const redObjective = {selected: checkedValues(form, 'red_objective_selected'), custom: fieldValue(form, 'red_objective_custom')};
  const blueObjective = {selected: checkedValues(form, 'blue_objective_selected'), custom: fieldValue(form, 'blue_objective_custom')};
  const campaignTactics = {selected: checkedValues(form, 'campaign_tactics_selected'), custom: customListValues('campaign_tactics_custom')};
  const tacticalTactics = {selected: checkedValues(form, 'tactical_tactics_selected'), custom: customListValues('tactical_tactics_custom')};
  if ((!redObjective.selected.length && !redObjective.custom) || (!blueObjective.selected.length && !blueObjective.custom)) {
    toast('红蓝双方目标均需选择推荐项或填写自定义目标', 'error');
    return null;
  }
  if (![campaignTactics, tacticalTactics].some((item) => item.selected.length || item.custom.length)) {
    toast('请至少选择或添加一种战役战法或战术战法', 'error');
    return null;
  }
  return {
    red_objective: redObjective,
    blue_objective: blueObjective,
    campaign_tactics: campaignTactics,
    tactical_tactics: tacticalTactics,
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
  if (record.current_output) {
    streamBuffer = record.current_output;
    output.innerHTML = renderMarkdown(record.current_output);
  }
  else if (!App.generating) output.innerHTML = '<span class="muted">填写表单后可直接保存或生成草案。</span>';
  document.getElementById('result-sources').innerHTML = (record.current_sources || []).map((source) => (
    `<span class="source-pill">${escapeHtml(sourceName(source.backend))} · ${escapeHtml(sourceName(source.category))} · ${escapeHtml(source.id || '')}</span>`
  )).join('');
  if (!App.generating) document.getElementById('result-progress').classList.add('hidden');
}

function clearResult() {
  streamBuffer = '';
  document.getElementById('result-output').innerHTML = '';
  document.getElementById('result-sources').innerHTML = '';
  document.getElementById('result-error').classList.add('hidden');
  document.getElementById('result-progress').classList.add('hidden');
}

function handleEvent(event) {
  if (event.type === 'progress') {
    const progress = document.getElementById('result-progress');
    progress.innerHTML = `${escapeHtml(event.message || '正在生成')}<span class="loading-dots"><i></i><i></i><i></i></span>`;
    progress.classList.remove('hidden');
  } else if (event.type === 'source') {
    const source = document.createElement('span');
    source.className = 'source-pill';
    source.textContent = `${sourceName(event.source.backend)} · ${sourceName(event.source.category)} · ${event.source.id || ''}`;
    document.getElementById('result-sources').appendChild(source);
  } else if (event.type === 'content') {
    streamBuffer += event.delta || '';
    scheduleMarkdownRender();
  } else if (event.type === 'error') {
    showResultError(ERROR_MESSAGES[event.code] || '生成失败，请稍后重试');
  } else if (event.type === 'done') {
    document.getElementById('result-version').textContent = `V${event.version}`;
    document.getElementById('result-progress').classList.add('hidden');
    flushMarkdownRender();
  }
}

function scheduleMarkdownRender() {
  if (markdownTimer) return;
  markdownTimer = setTimeout(flushMarkdownRender, 60);
}

function flushMarkdownRender() {
  if (markdownTimer) clearTimeout(markdownTimer);
  markdownTimer = null;
  const output = document.getElementById('result-output');
  output.innerHTML = renderMarkdown(streamBuffer);
  output.scrollTop = output.scrollHeight;
}

function renderMarkdown(text) {
  if (!window.marked || !window.DOMPurify) return escapeHtml(text).replace(/\n/g, '<br>');
  const parsed = window.marked.parse(String(text || ''), {gfm: true, breaks: true});
  return window.DOMPurify.sanitize(parsed, {
    USE_PROFILES: {html: true},
    FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'form'],
    FORBID_ATTR: ['style', 'onerror', 'onload', 'onclick'],
  });
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
  deduplication: {enabled: true, threshold: 0.95},

  async init() {
    document.getElementById('refresh-kb').addEventListener('click', () => this.loadBases());
    document.getElementById('toggle-deduplication').addEventListener('click', () => this.toggleDeduplication());
    document.getElementById('add-knowledge').addEventListener('click', () => this.openCreate());
    document.getElementById('submit-knowledge').addEventListener('click', () => this.create());
    document.getElementById('confirm-knowledge-delete').addEventListener('click', () => this.confirmRemove());
    await Promise.all([this.loadBases(), this.loadDeduplication()]);
  },

  async loadDeduplication() {
    try {
      const response = await fetch(`${API}/api/knowledge_deduplication`);
      if (response.ok) this.deduplication = await response.json();
    } catch {}
    this.renderDeduplication();
  },

  async toggleDeduplication() {
    try {
      const response = await fetch(`${API}/api/knowledge_deduplication/toggle`, {method: 'POST'});
      if (!response.ok) throw new Error();
      this.deduplication = await response.json();
      this.renderDeduplication();
      toast(this.deduplication.enabled ? '相似度检查已开启' : '相似度检查已关闭', 'success');
    } catch { toast('相似度检查开关更新失败', 'error'); }
  },

  renderDeduplication() {
    const button = document.getElementById('toggle-deduplication');
    if (!button) return;
    button.textContent = `相似度检查：${this.deduplication.enabled ? '开启' : '关闭'}`;
    button.title = `阈值 ${Number(this.deduplication.threshold || 0.95).toFixed(2)}`;
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
    document.getElementById('knowledge-level').value = 'general';
    document.getElementById('knowledge-source').value = 'manual';
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
        body: JSON.stringify({
          kb_id: kbId,
          content,
          level: document.getElementById('knowledge-level').value,
          source: document.getElementById('knowledge-source').value.trim() || 'manual',
        }),
      });
      if (!response.ok) throw new Error();
      const body = await response.json();
      document.getElementById('knowledge-modal').classList.add('hidden');
      this.selected = kbId;
      renderKbBases(this.bases, kbId);
      await this.loadEntries();
      if (body.duplicate) {
        toast(body.similarity_warning ? '检测到完全相同的知识，相似度 100.0%，未重复添加' : '相同知识已存在，未重复添加', 'error');
      } else {
        toast(body.similarity_warning ? `知识已添加，检测到高相似度 ${(Number(body.similarity_score) * 100).toFixed(1)}%，请人工审核` : '知识已添加', body.similarity_warning ? 'error' : 'success');
      }
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

  async approve(id) {
    try {
      const response = await fetch(`${API}/api/knowledge/${encodeURIComponent(id)}/approve`, {method: 'POST'});
      if (!response.ok) throw new Error();
      await this.loadEntries();
      toast('知识已审核通过', 'success');
    } catch {
      toast('知识审核失败', 'error');
    }
  },

  async confirmRemove() {
    if (!this.pendingDelete) return;
    const id = this.pendingDelete;
    try {
      const response = await fetch(`${API}/api/delete_knowledge?k_id=${encodeURIComponent(id)}&kb_id=${encodeURIComponent(this.selected)}`, {method: 'DELETE'});
      const body = await response.json();
      if (!response.ok || !body.success) throw new Error();
      document.getElementById('knowledge-delete-modal').classList.add('hidden');
      this.pendingDelete = null;
      await this.loadEntries();
      if (this.entries.some((entry) => entry.k_id === id)) throw new Error('删除后条目仍然存在');
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
  const title = document.getElementById('knowledge-title');
  const selected = items.find((item) => item.kb_id === activeId);
  if (title) title.textContent = selected ? selected.name : '选择知识库';
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
    <div class="knowledge-card-meta">来源：${escapeHtml(entry.source || base?.name || entry.kb_id)} · 层级：${escapeHtml(entry.level || 'general')} · ${escapeHtml(entry.k_id)}</div>
    <div class="knowledge-card-review ${entry.verified ? 'approved' : ''}">${entry.verified ? '已审核' : '待审核'}</div>${entry.similarity_warning ? `<div class="knowledge-similarity-warning">高相似度提醒：${(Number(entry.similarity_score) * 100).toFixed(1)}%<br>最相似知识：${escapeHtml(entry.similar_content || '')}</div>` : ''}</div>
    <div class="knowledge-card-actions">${entry.verified ? '' : `<button class="outline-button knowledge-approve" data-id="${escapeAttr(entry.k_id)}" title="审核通过">审核通过</button>`}<button class="danger-button knowledge-delete" data-id="${escapeAttr(entry.k_id)}" title="删除知识">删除</button></div>
  </article>`).join('');
  container.querySelectorAll('.knowledge-delete').forEach((button) => {
    button.addEventListener('click', () => KnowledgeApp.remove(button.dataset.id));
  });
  container.querySelectorAll('.knowledge-approve').forEach((button) => {
    button.addEventListener('click', () => KnowledgeApp.approve(button.dataset.id));
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

function hiddenValues(form, name) {
  return [...form.querySelectorAll(`input[type="hidden"][name="${name}"]`)].map((item) => item.value);
}

function splitList(value) {
  return value.split(/[、,，;；\n]/).map((item) => item.trim()).filter(Boolean);
}

function uniqueValues(values) {
  return [...new Map((values || []).filter(Boolean).map((value) => [String(value).trim().toLowerCase(), String(value).trim()])).values()];
}

function bindCustomRemovers(control) {
  control.querySelectorAll('.custom-remove').forEach((button) => {
    button.onclick = () => button.closest('.custom-item').remove();
  });
}

function customListValues(name) {
  const control = document.querySelector(`.custom-list-control[data-name="${CSS.escape(name)}"]`);
  return control ? uniqueValues([...control.querySelectorAll('.custom-item')].map((item) => item.dataset.value)) : [];
}

function compactObject(value) {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item));
}

function validationMessage(body) {
  const detail = body?.detail;
  return Array.isArray(detail) ? detail.map((item) => item.msg).filter(Boolean).join('；') : '';
}

function localizedError(body, fallback = '操作失败，请稍后重试') {
  const code = body?.error?.code;
  return ERROR_MESSAGES[code] || validationMessage(body) || fallback;
}

function sourceName(value) {
  return SOURCE_NAMES[value] || (value ? String(value) : '知识来源');
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
