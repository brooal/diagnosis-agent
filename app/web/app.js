const api = {
  threads: "/api/v1/threads",
  thread: (id) => `/api/v1/threads/${encodeURIComponent(id)}`,
  updateThread: (id) => `/api/v1/threads/${encodeURIComponent(id)}`,
  deleteThread: (id) => `/api/v1/threads/${encodeURIComponent(id)}`,
  run: (id) => `/api/v1/runs/${encodeURIComponent(id)}`,
  chat: "/api/v1/agent/chat",
  auto: "/api/v1/agent/auto",
  manualBeam: "/api/v1/auto/beam/diagnose-window",
  autoProbe: "/api/v1/auto/beam/probe",
  autoScheduler: "/api/v1/auto/beam/scheduler",
  autoProgress: "/api/v1/auto/beam/progress",
  startAutoScheduler: "/api/v1/auto/beam/scheduler/start",
  stopAutoScheduler: "/api/v1/auto/beam/scheduler/stop",
  autoReports: "/api/v1/auto/beam/reports",
  autoReport: (id) => `/api/v1/auto/beam/reports/${encodeURIComponent(id)}`,
  deleteAutoReport: (id) => `/api/v1/auto/beam/reports/${encodeURIComponent(id)}`,
  beamSeries: (start, end) => `/api/v1/auto/beam/series?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`,
  latestBeamSeries: "/api/v1/auto/beam/latest-series",
  manualDashboard: "/api/v1/auto/beam/diagnose-dashboard",
};

const state = {
  mode: "auto",
  currentThreadUid: null,
  selectedRunUid: null,
  threads: [],
  currentThreadDetail: null,
  autoReports: [],
  autoScheduler: null,
  autoProgressTimer: null,
  autoLastReportRefreshAt: 0,
  autoLastProgressSignature: "",
  selectedAutoIncidentUid: null,
  openAutoReportMenuUid: null,
  mockAutoReportVisible: true,
  editingThreadUid: null,
};

const MOCK_AUTO_REPORT = {
  incident_uid: "mock_auto_report",
  status: "closed",
  classification: "drop",
  severity: "critical",
  first_seen_at: "2026-05-31T19:44:56+08:00",
  last_seen_at: "2026-05-31T19:45:26+08:00",
  recovered_at: "2026-05-31T19:46:26+08:00",
  primary_cause: {
    cause_type: "quadrupole_power_fault",
    pv: "SR_PS_QM:test:current:ai",
    description: "测试数据：四极铁电源电流异常下降。",
  },
  candidate_causes: [
    {
      cause_type: "quadrupole_power_fault",
      pv: "SR_PS_QM:test:current:ai",
      confidence: 0.88,
      description: "测试数据：四极铁电源电流异常下降。",
    },
  ],
  report: "## 测试诊断报告\n\n这是用于测试弹窗交互的假数据。真实报告会在这里展示完整诊断正文、候选原因和证据。",
  evidence: {
    detect_window: {
      start: "2026-05-31T19:44:26+08:00",
      end: "2026-05-31T19:44:56+08:00",
    },
  },
  report_date: "2026-05-31",
  report_month: "2026-05",
  report_day: "2026-05-31",
  is_mock: true,
};

const els = {
  threadList: document.querySelector("#threadList"),
  appShell: document.querySelector("#appShell"),
  threadCount: document.querySelector("#threadCount"),
  newChatButton: document.querySelector("#newChatButton"),
  refreshThreadsButton: document.querySelector("#refreshThreadsButton"),
  chatTab: document.querySelector("#chatTab"),
  autoTab: document.querySelector("#autoTab"),
  chatPanel: document.querySelector("#chatPanel"),
  autoPanel: document.querySelector("#autoPanel"),
  workspaceTitle: document.querySelector("#workspaceTitle"),
  chatMessages: document.querySelector("#chatMessages"),
  chatForm: document.querySelector("#chatForm"),
  chatInput: document.querySelector("#chatInput"),
  chatRagToggle: document.querySelector("#chatRagToggle"),
  sendChatButton: document.querySelector("#sendChatButton"),
  processDrawer: document.querySelector("#processDrawer"),
  closeDrawerButton: document.querySelector("#closeDrawerButton"),
  drawerTitle: document.querySelector("#drawerTitle"),
  runDetail: document.querySelector("#runDetail"),
  runStatus: document.querySelector("#runStatus"),
  autoSchedulerStatus: document.querySelector("#autoSchedulerStatus"),
  autoSchedulerMeta: document.querySelector("#autoSchedulerMeta"),
  autoProbeForm: document.querySelector("#autoProbeForm"),
  autoProbeLlmToggle: document.querySelector("#autoProbeLlmToggle"),
  autoProbeEmail: document.querySelector("#autoProbeEmail"),
  runAutoProbeButton: document.querySelector("#runAutoProbeButton"),
  autoProbeResult: document.querySelector("#autoProbeResult"),
  autoProgressPanel: document.querySelector("#autoProgressPanel"),
  toggleAutoSchedulerButton: document.querySelector("#toggleAutoSchedulerButton"),
  refreshAutoReportsButton: document.querySelector("#refreshAutoReportsButton"),
  autoReportModal: document.querySelector("#autoReportModal"),
  closeAutoReportModalButton: document.querySelector("#closeAutoReportModalButton"),
  autoBeamChart: document.querySelector("#autoBeamChart"),
  autoReportList: document.querySelector("#autoReportList"),
  autoReportInlineTitle: document.querySelector("#autoReportInlineTitle"),
  autoReportInlineStatus: document.querySelector("#autoReportInlineStatus"),
  autoReportInlineDetail: document.querySelector("#autoReportInlineDetail"),
  manualBeamForm: document.querySelector("#manualBeamForm"),
  manualBeamStart: document.querySelector("#manualBeamStart"),
  manualBeamEnd: document.querySelector("#manualBeamEnd"),
  runManualBeamButton: document.querySelector("#runManualBeamButton"),
  manualBeamResult: document.querySelector("#manualBeamResult"),
  manualBeamChart: document.querySelector("#manualBeamChart"),
  manualStatus: document.querySelector("#manualStatus"),
};

try {
  init();
} catch (error) {
  document.body.insertAdjacentHTML(
    "afterbegin",
    `<div class="frontend-error">前端初始化失败：${escapeHtml(error.message)}</div>`,
  );
  console.error(error);
}

function init() {
  bindEvents();
  renderEmptyChat();
  closeProcessDrawer();
  if (state.mode === "auto") {
    setMode("auto");
  }
  loadThreads();
}

function bindEvents() {
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".thread-menu-wrap")) closeThreadMenus();
    if (!event.target.closest(".report-menu-wrap")) closeAutoReportMenus();
  });
  els.newChatButton.addEventListener("click", () => {
    state.currentThreadUid = null;
    state.selectedRunUid = null;
    state.currentThreadDetail = null;
    renderThreadList();
    renderEmptyChat();
    closeProcessDrawer();
  });
  els.refreshThreadsButton.addEventListener("click", loadThreads);
  els.chatTab.addEventListener("click", () => setMode("chat"));
  els.autoTab.addEventListener("click", () => setMode("auto"));
  els.chatForm.addEventListener("submit", submitChat);
  els.autoProbeForm.addEventListener("submit", submitAutoProbe);
  els.manualBeamForm.addEventListener("submit", submitManualBeamDiagnosis);
  els.toggleAutoSchedulerButton.addEventListener("click", toggleAutoScheduler);
  els.refreshAutoReportsButton.addEventListener("click", loadAutoDashboard);
  els.closeDrawerButton.addEventListener("click", closeProcessDrawer);
  els.closeAutoReportModalButton.addEventListener("click", closeAutoReportModal);
}

function setMode(mode) {
  state.mode = mode;
  els.appShell.classList.toggle("auto-mode", mode === "auto");
  els.chatTab.classList.toggle("active", mode === "chat");
  els.autoTab.classList.toggle("active", mode === "auto");
  els.chatPanel.classList.toggle("active", mode === "chat");
  els.autoPanel.classList.toggle("active", mode === "auto");
  els.workspaceTitle.textContent = mode === "chat" ? "对话诊断" : "自动诊断";
  if (mode === "auto") {
    loadAutoDashboard();
  } else {
    stopAutoProgressPolling();
  }
}

async function loadThreads() {
  try {
    const data = await request(api.threads);
    state.threads = data;
    renderThreadList();
  } catch (error) {
    els.threadList.innerHTML = `<div class="detail-empty">${escapeHtml(error.message)}</div>`;
  }
}

function renderThreadList() {
  els.threadCount.textContent = String(state.threads.length);
  if (!state.threads.length) {
    els.threadList.innerHTML = `<div class="detail-empty">还没有历史对话。</div>`;
    return;
  }
  els.threadList.innerHTML = state.threads.map(renderThreadItem).join("");
  els.threadList.querySelectorAll("[data-thread-select]").forEach((button) => {
    button.addEventListener("click", () => selectThread(button.dataset.thread));
  });
  els.threadList.querySelectorAll("[data-thread-menu]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleThreadMenu(button.dataset.thread);
    });
  });
  els.threadList.querySelectorAll("[data-thread-edit]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      closeThreadMenus();
      editThreadTitle(button.dataset.thread);
    });
  });
  els.threadList.querySelectorAll("[data-thread-delete]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      closeThreadMenus();
      deleteThread(button.dataset.thread);
    });
  });
  els.threadList.querySelectorAll("[data-thread-edit-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      saveThreadTitle(form.dataset.thread);
    });
  });
  els.threadList.querySelectorAll("[data-thread-edit-cancel]").forEach((button) => {
    button.addEventListener("click", () => cancelThreadTitleEdit());
  });
  els.threadList.querySelectorAll("[data-thread-title-input]").forEach((input) => {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") cancelThreadTitleEdit();
    });
  });
}

function renderThreadItem(thread) {
  const active = thread.thread_uid === state.currentThreadUid ? " active" : "";
  const editing = thread.thread_uid === state.editingThreadUid;
  const title = thread.title || thread.thread_uid;
  const snippet = thread.last_message || "暂无消息";
  const status = thread.last_run_status || thread.status;
  if (editing) {
    return `
      <article class="thread-item${active} editing">
        <form class="thread-edit-form" data-thread-edit-form data-thread="${escapeAttr(thread.thread_uid)}">
          <input data-thread-title-input data-thread="${escapeAttr(thread.thread_uid)}" type="text" value="${escapeAttr(thread.title || "")}" placeholder="输入对话标题" />
          <div class="thread-edit-actions">
            <button class="thread-save-button" type="submit">保存</button>
            <button class="thread-cancel-button" type="button" data-thread-edit-cancel>取消</button>
          </div>
        </form>
      </article>
    `;
  }
  return `
    <article class="thread-item${active}">
      <button class="thread-main" type="button" data-thread-select data-thread="${escapeAttr(thread.thread_uid)}">
        <div class="thread-title">${escapeHtml(title)}</div>
        <div class="thread-snippet">${escapeHtml(snippet)}</div>
        <div class="thread-meta">${escapeHtml(formatTime(thread.updated_at || thread.created_at))} · ${escapeHtml(status)} · ${thread.run_count || 0} runs</div>
      </button>
      <div class="thread-menu-wrap">
        <button class="thread-menu-button" type="button" data-thread-menu data-thread="${escapeAttr(thread.thread_uid)}" aria-label="历史对话操作">...</button>
        <div class="thread-menu" data-thread-menu-panel="${escapeAttr(thread.thread_uid)}" hidden>
          <button type="button" data-thread-edit data-thread="${escapeAttr(thread.thread_uid)}">重命名</button>
          <button class="danger-text" type="button" data-thread-delete data-thread="${escapeAttr(thread.thread_uid)}">删除</button>
        </div>
      </div>
    </article>
  `;
}

function toggleThreadMenu(threadUid) {
  const panel = [...els.threadList.querySelectorAll("[data-thread-menu-panel]")]
    .find((item) => item.dataset.threadMenuPanel === threadUid);
  const willOpen = panel?.hidden;
  closeThreadMenus();
  if (panel && willOpen) panel.hidden = false;
}

function closeThreadMenus() {
  els.threadList.querySelectorAll("[data-thread-menu-panel]").forEach((panel) => {
    panel.hidden = true;
  });
}

async function editThreadTitle(threadUid) {
  state.editingThreadUid = threadUid;
  renderThreadList();
  const input = [...els.threadList.querySelectorAll("[data-thread-title-input]")]
    .find((item) => item.dataset.thread === threadUid);
  if (input) {
    input.focus();
    input.select();
  }
}

function cancelThreadTitleEdit() {
  state.editingThreadUid = null;
  renderThreadList();
}

async function saveThreadTitle(threadUid) {
  const input = [...els.threadList.querySelectorAll("[data-thread-title-input]")]
    .find((item) => item.dataset.thread === threadUid);
  const nextTitle = input?.value.trim() || null;
  try {
    const updated = await request(api.updateThread(threadUid), {
      method: "PATCH",
      body: JSON.stringify({ title: nextTitle }),
    });
    state.threads = state.threads.map((item) => (
      item.thread_uid === threadUid ? { ...item, ...updated } : item
    ));
    state.editingThreadUid = null;
    renderThreadList();
  } catch (error) {
    window.alert(`修改标题失败：${error.message}`);
  }
}

async function deleteThread(threadUid) {
  const thread = state.threads.find((item) => item.thread_uid === threadUid);
  const title = thread?.title || threadUid;
  if (!window.confirm(`确定删除历史对话「${title}」吗？这个操作不可恢复。`)) return;
  try {
    await request(api.deleteThread(threadUid), { method: "DELETE" });
    state.threads = state.threads.filter((item) => item.thread_uid !== threadUid);
    if (state.currentThreadUid === threadUid) {
      state.currentThreadUid = null;
      state.selectedRunUid = null;
      state.currentThreadDetail = null;
      state.editingThreadUid = null;
      renderEmptyChat();
      closeProcessDrawer();
    }
    renderThreadList();
  } catch (error) {
    window.alert(`删除历史对话失败：${error.message}`);
  }
}

async function selectThread(threadUid) {
  state.currentThreadUid = threadUid;
  state.selectedRunUid = null;
  renderThreadList();
  closeProcessDrawer();
  els.chatMessages.innerHTML = `<div class="message system">正在加载历史对话...</div>`;
  try {
    const detail = await request(api.thread(threadUid));
    state.currentThreadDetail = detail;
    renderThread(detail);
  } catch (error) {
    els.chatMessages.innerHTML = `<div class="message system">${escapeHtml(error.message)}</div>`;
  }
}

function renderThread(detail) {
  const runsByTurn = groupRunsByTurn(detail.runs || []);
  const visibleTurnIds = new Set((detail.turns || []).map((turn) => turn.turn_uid));
  const parts = [];
  for (const turn of detail.turns || []) {
    parts.push(renderTurn(turn));
    for (const run of runsByTurn.get(turn.turn_uid) || []) {
      parts.push(renderDiagnosisRunCard(run));
    }
  }
  const orphanRuns = (detail.runs || []).filter((run) => !visibleTurnIds.has(run.turn_uid));
  for (const run of orphanRuns) {
    parts.push(renderDiagnosisRunCard(run));
  }
  els.chatMessages.innerHTML = parts.join("") || `<div class="message system">这个会话还没有消息。</div>`;
  bindRunButtons();
  scrollMessagesToBottom();
}

function groupRunsByTurn(runs) {
  const grouped = new Map();
  for (const run of runs) {
    if (!grouped.has(run.turn_uid)) {
      grouped.set(run.turn_uid, []);
    }
    grouped.get(run.turn_uid).push(run);
  }
  return grouped;
}

function renderTurn(turn) {
  const role = turn.role === "assistant" ? "assistant" : turn.role === "auto" ? "auto" : "user";
  const body = role === "user" ? escapeHtml(turn.content) : renderMarkdown(turn.content);
  return `<div class="message ${role}">${body}</div>`;
}

function renderDiagnosisRunCard(run) {
  const active = run.run_uid === state.selectedRunUid ? " selected" : "";
  const title = buildRunTitle(run);
  const timeRange = formatTimeWindow(run.time_window);
  const answer = run.final_answer ? truncate(run.final_answer, 150) : "诊断尚未生成结论。";
  return `
    <article class="run-card${active}">
      <div class="run-line">
        <div>
          <strong>${escapeHtml(title)}</strong>
          <div class="run-subtitle">${escapeHtml(timeRange || formatTime(run.started_at) || run.run_uid)}</div>
        </div>
        ${statusChip(run.status)}
      </div>
      <div class="run-preview">${escapeHtml(answer)}</div>
      <div class="thread-meta">
        <span>运行时间：${escapeHtml(formatTime(run.started_at))}</span>
        <span>候选原因：${run.candidate_cause_count || 0}</span>
      </div>
      <div class="run-actions">
        <button class="small-button" type="button" data-run="${escapeAttr(run.run_uid)}">查看诊断过程</button>
      </div>
    </article>
  `;
}

function buildRunTitle(run) {
  if (run.trigger_source === "auto") {
    return run.intent || "自动诊断";
  }
  return truncate(run.user_query || "诊断运行", 42);
}

function bindRunButtons() {
  els.chatMessages.querySelectorAll("[data-run]").forEach((button) => {
    button.addEventListener("click", () => selectRun(button.dataset.run));
  });
}

async function selectRun(runUid) {
  state.selectedRunUid = runUid;
  openProcessDrawer();
  renderRunLoading();
  try {
    const detail = await request(api.run(runUid));
    renderStoredRunDetail(detail);
    markSelectedRun();
  } catch (error) {
    renderRunError(error.message);
  }
}

async function submitChat(event) {
  event.preventDefault();
  const text = els.chatInput.value.trim();
  if (!text) return;
  setLoading(true);
  appendMessage("user", text);
  els.chatInput.value = "";
  closeProcessDrawer();

  try {
    const payload = {
      user_query: text,
      thread_uid: state.currentThreadUid,
      enable_rag: els.chatRagToggle.checked,
      rag_limit: 5,
      rag_include_system_design: els.chatRagToggle.checked,
    };
    if (!payload.thread_uid) delete payload.thread_uid;
    const response = await request(api.chat, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.currentThreadUid = response.thread_uid;
    appendMessage(
      response.status === "failed" ? "system" : "assistant",
      response.final_answer || response.error || "诊断完成。",
    );
    appendLiveRunCard(response, text);
    await loadThreads();
  } catch (error) {
    appendMessage("system", error.message);
  } finally {
    setLoading(false);
  }
}

async function submitManualBeamDiagnosis(event) {
  event.preventDefault();
  setManualLoading(true);
  setStatus(els.manualStatus, "running", "诊断中");
  els.manualBeamResult.innerHTML = `<div class="detail-empty">正在执行手动束流诊断...</div>`;

  try {
    const payload = {
      time_window: {
        start: els.manualBeamStart.value.trim(),
        end: els.manualBeamEnd.value.trim(),
      },
    };
    const response = await request(api.manualDashboard, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    renderManualDashboard(response);
  } catch (error) {
    setStatus(els.manualStatus, "failed");
    els.manualBeamResult.innerHTML = `<div class="detail-empty">${escapeHtml(error.message)}</div>`;
    els.manualBeamChart.innerHTML = `<div class="detail-empty">${escapeHtml(error.message)}</div>`;
  } finally {
    setManualLoading(false);
  }
}

function renderEmptyChat() {
  els.chatMessages.innerHTML = `
    <div class="message system">
      输入自然语言即可开始诊断。一个对话可以包含多次诊断，每次诊断会作为独立运行卡片展示。
    </div>
  `;
}

function appendMessage(role, content) {
  const body = role === "user" ? escapeHtml(content) : renderMarkdown(content);
  els.chatMessages.insertAdjacentHTML(
    "beforeend",
    `<div class="message ${role}">${body}</div>`,
  );
  scrollMessagesToBottom();
}

function appendLiveRunCard(response, userQuery) {
  const run = {
    run_uid: response.run_uid,
    case_uid: response.case_uid,
    turn_uid: response.turn_uid,
    status: response.status,
    trigger_source: "chat",
    user_query: userQuery,
    time_window: null,
    started_at: new Date().toISOString(),
    final_answer: response.final_answer,
    candidate_cause_count: (response.candidate_causes || []).length,
  };
  els.chatMessages.insertAdjacentHTML("beforeend", renderDiagnosisRunCard(run));
  bindRunButtons();
  scrollMessagesToBottom();
}

function renderStoredRunDetail(detail) {
  const run = detail.run || {};
  const caseInfo = detail.case || {};
  const title = buildRunTitle({
    ...run,
    user_query: caseInfo.intent || run.final_answer,
    intent: caseInfo.intent,
    time_window: caseInfo.time_window,
  });
  els.drawerTitle.textContent = title || "诊断过程";
  setStatus(els.runStatus, run.status || caseInfo.status || "completed");
  els.runDetail.innerHTML = `
    ${renderRunOverview(detail)}
    ${renderAnswer(run.final_answer || caseInfo.final_answer || "无最终结论。")}
    ${renderCandidateCauses(caseInfo.candidate_causes || [])}
    ${renderReadableTimeline(detail)}
    ${renderSkillCalls(detail.skill_calls || [])}
    ${renderToolCalls(detail.tool_calls || [])}
  `;
}

function renderRunOverview(detail) {
  const run = detail.run || {};
  const caseInfo = detail.case || {};
  const fields = [
    ["运行编号", run.run_uid],
    ["问题时间", formatTimeWindow(caseInfo.time_window)],
    ["运行时间", formatTime(run.started_at)],
    ["完成时间", formatTime(run.finished_at)],
    ["触发方式", run.trigger_source],
    ["状态", run.status],
  ];
  return `
    <section class="process-card">
      <h4>运行摘要</h4>
      <div class="info-grid">
        ${fields
          .filter(([, value]) => value)
          .map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`)
          .join("")}
      </div>
    </section>
  `;
}

function renderReadableTimeline(detail) {
  const steps = buildStepRounds(detail);
  if (!steps.length) return "";
  return `
    <section class="process-card">
      <h4>过程时间线</h4>
      <div class="step-list">
        ${steps.map(renderStepRound).join("")}
      </div>
    </section>
  `;
}

function buildStepRounds(detail) {
  const rounds = new Map();
  for (const item of detail.items || []) {
    const event = normalizeTimelineEvent(item);
    if (!event) continue;
    const key = event.stepKey;
    if (!rounds.has(key)) {
      rounds.set(key, {
        stepKey: key,
        stepLabel: event.stepLabel,
        planned: null,
        execution: [],
        observation: [],
        final: null,
        failed: null,
      });
    }
    const round = rounds.get(key);
    if (event.kind === "planned") round.planned = event;
    if (event.kind === "execution") round.execution.push(event);
    if (event.kind === "observation") round.observation.push(event);
    if (event.kind === "final") round.final = event;
    if (event.kind === "failed") round.failed = event;
  }
  return [...rounds.values()].sort((left, right) => {
    if (left.stepKey === "final") return 1;
    if (right.stepKey === "final") return -1;
    return Number(left.stepKey) - Number(right.stepKey);
  });
}

function normalizeTimelineEvent(item) {
  const content = item.content || {};
  const step = typeof content.step === "number" ? content.step : null;
  const stepKey = step === null ? "final" : String(step);
  const stepLabel = step === null ? "最终结论" : `Step ${step}`;
  if (item.item_type === "react_action_planned") {
    const action = content.action || {};
    return {
      kind: "planned",
      stepKey,
      stepLabel,
      title: action.name ? `${action.type}: ${action.name}` : action.type || "finish",
      text: content.thought || action.reason,
      action,
      payload: content,
    };
  }
  if (item.item_type === "react_finished") {
    const action = content.action || {};
    return {
      kind: "planned",
      stepKey,
      stepLabel,
      title: "finish",
      text: content.thought || action.reason,
      action,
      payload: content,
    };
  }
  if (item.item_type === "skill_called") {
    return {
      kind: "execution",
      stepKey,
      stepLabel,
      type: "Skill",
      title: content.name || "skill",
      text: content.summary || content.error,
      ok: content.ok,
      payload: content,
    };
  }
  if (item.item_type === "tool_called") {
    return {
      kind: "execution",
      stepKey,
      stepLabel,
      type: "Tool",
      title: content.name || "tool",
      text: content.summary || content.error,
      ok: content.ok,
      payload: content,
    };
  }
  if (item.item_type === "observation_added") {
    return {
      kind: "observation",
      stepKey,
      stepLabel,
      type: "Observation",
      title: content.source_name || content.source_type || "observation",
      text: content.summary || content.error,
      payload: content,
    };
  }
  if (item.item_type === "final_answer") {
    return {
      kind: "final",
      stepKey: "final",
      stepLabel: "最终结论",
      title: "最终诊断结论",
      text: content.final_answer,
      payload: content,
    };
  }
  if (item.item_type === "step_failed" || item.item_type === "react_planning_failed") {
    return {
      kind: "failed",
      stepKey,
      stepLabel,
      title: "执行失败",
      text: content.error,
      payload: content,
    };
  }
  return null;
}

function renderStepRound(round) {
  const title = round.planned?.title || round.final?.title || round.failed?.title || "诊断轮次";
  const result = round.failed ? "failed" : round.final ? "completed" : round.execution.some((item) => item.ok === false) ? "failed" : "completed";
  return `
    <details class="step-round">
      <summary>
        <span>${escapeHtml(round.stepLabel)}</span>
        <strong>${escapeHtml(title)}</strong>
        ${statusChip(result)}
      </summary>
      <div class="round-body">
        ${round.planned ? renderRoundBlock("规划", round.planned.text, round.planned.action, round.planned.payload) : ""}
        ${round.execution.map((event) => renderRoundBlock(event.type, event.text, { name: event.title, ok: event.ok }, event.payload)).join("")}
        ${round.observation.map((event) => renderRoundBlock("观测", event.text, { name: event.title }, event.payload)).join("")}
        ${round.failed ? renderRoundBlock("失败", round.failed.text, null, round.failed.payload) : ""}
        ${round.final ? renderRoundBlock("结论", round.final.text, null, round.final.payload) : ""}
      </div>
    </details>
  `;
}

function renderRoundBlock(label, text, meta, payload) {
  return `
    <div class="round-block">
      <div class="round-block-title">
        <span>${escapeHtml(label)}</span>
        ${meta?.name ? `<strong>${escapeHtml(meta.name)}</strong>` : ""}
      </div>
      ${text ? `<div class="markdown-body">${renderMarkdown(text)}</div>` : ""}
      ${payload ? renderJsonDetails("展开参数与原始证据", payload) : ""}
    </div>
  `;
}

function renderSkillCalls(calls) {
  if (!calls.length) return "";
  return `
    <section class="process-card">
      <h4>Skill 调用结果</h4>
      <div class="skill-result-list">
        ${calls.map(renderSkillCall).join("")}
      </div>
    </section>
  `;
}

function renderSkillCall(call) {
  const candidates = call.candidate_causes || [];
  return `
    <article class="skill-result">
      <div class="skill-result-head">
        <div>
          <strong>${escapeHtml(call.skill_name)}</strong>
          <div class="candidate-meta">Step ${escapeHtml(call.step)} · ${escapeHtml(formatTime(call.created_at))}</div>
        </div>
        ${statusChip(call.ok ? "completed" : "failed", call.ok ? "ok" : "failed")}
      </div>
      <div class="markdown-body">${renderMarkdown(call.summary || call.error || "无摘要")}</div>
      ${candidates.length ? renderMiniCandidateList(candidates) : ""}
      ${renderJsonDetails("展开 Skill 参数和证据", {
        arguments: call.arguments,
        evidence: call.evidence,
        candidate_causes: call.candidate_causes,
      })}
    </article>
  `;
}

function renderToolCalls(calls) {
  if (!calls.length) return "";
  return `
    <section class="process-card">
      <h4>Tool 调用</h4>
      <div class="tool-list">
        ${calls
          .map(
            (call) => `
              <div class="tool-item">
                <div>
                  <strong>${escapeHtml(call.tool_name)}</strong>
                  <div class="markdown-body">${renderMarkdown(call.output_summary || call.error || "无摘要")}</div>
                </div>
                ${statusChip(call.ok ? "completed" : "failed", call.ok ? "ok" : "failed")}
                ${renderJsonDetails("查看调用参数", call.arguments)}
              </div>
            `,
          )
          .join("")}
      </div>
    </section>
  `;
}

async function loadAutoDashboard() {
  await Promise.all([loadAutoSchedulerStatus(), loadAutoProgress(), loadAutoReports()]);
}

async function loadAutoSchedulerStatus() {
  try {
    const status = await request(api.autoScheduler);
    state.autoScheduler = status;
    renderAutoScheduler(status);
  } catch (error) {
    setStatus(els.autoSchedulerStatus, "failed");
    els.autoSchedulerMeta.textContent = error.message;
  }
}

function renderAutoScheduler(status) {
  state.autoScheduler = status;
  setStatus(
    els.autoSchedulerStatus,
    status.running ? "running" : "neutral",
    status.running ? "运行中" : "已停止",
  );
  const executionText = status.require_operation_schedule ? "仅 Operation 日自动运行" : "不限制运行计划";
  const startedText = status.started_at ? formatTime(status.started_at) : "尚未启动";
  els.autoSchedulerMeta.innerHTML = `
    <div class="monitor-summary-card ${status.running ? "running" : "stopped"}">
      <div class="monitor-summary-main">
        <div>
          <strong>${escapeHtml(status.running ? "自动诊断正在运行" : "自动诊断已停止")}</strong>
          <span>监测 PV：${escapeHtml(status.beam_channel)}</span>
        </div>
        ${statusChip(status.running ? "running" : "neutral", status.running ? "运行中" : "已停止")}
      </div>
      <div class="monitor-facts">
        <div><span>检查节奏</span><strong>每 ${escapeHtml(status.interval_seconds)}s 检查最近 ${escapeHtml(status.detect_window_seconds)}s</strong></div>
        <div><span>运行条件</span><strong>${escapeHtml(executionText)}</strong></div>
        <div><span>数据源</span><strong>${escapeHtml(status.data_source_backend || "http")}</strong></div>
        <div><span>启动时间</span><strong>${escapeHtml(startedText)}</strong></div>
      </div>
      ${status.last_error ? `<div class="monitor-error">最近错误：${escapeHtml(status.last_error)}</div>` : ""}
    </div>
  `;
  els.toggleAutoSchedulerButton.textContent = status.running ? "停止自动诊断" : "启动自动诊断";
  els.toggleAutoSchedulerButton.classList.toggle("danger-action", status.running);
}

async function toggleAutoScheduler() {
  if (state.autoScheduler?.running) {
    await stopAutoScheduler();
  } else {
    await startAutoScheduler();
  }
}

async function startAutoScheduler() {
  setSchedulerButtonsLoading(true);
  try {
    renderAutoScheduler(await request(api.startAutoScheduler, { method: "POST" }));
    await loadAutoProgress();
    await loadAutoReports({ quiet: true });
  } catch (error) {
    setStatus(els.autoSchedulerStatus, "failed");
    els.autoSchedulerMeta.textContent = error.message;
  } finally {
    setSchedulerButtonsLoading(false);
  }
}

async function stopAutoScheduler() {
  setSchedulerButtonsLoading(true);
  try {
    renderAutoScheduler(await request(api.stopAutoScheduler, { method: "POST" }));
    await loadAutoProgress();
  } catch (error) {
    setStatus(els.autoSchedulerStatus, "failed");
    els.autoSchedulerMeta.textContent = error.message;
  } finally {
    setSchedulerButtonsLoading(false);
  }
}

function setSchedulerButtonsLoading(value) {
  if (!value && state.autoScheduler) {
    els.toggleAutoSchedulerButton.disabled = false;
    els.refreshAutoReportsButton.disabled = false;
    return;
  }
  els.toggleAutoSchedulerButton.disabled = true;
  els.refreshAutoReportsButton.disabled = value;
}

async function submitAutoProbe(event) {
  event.preventDefault();
  setAutoProbeLoading(true);
  els.autoProbeResult.innerHTML = `<div class="detail-empty">正在运行自动束流诊断测试...</div>`;
  try {
    const payload = await request(api.autoProbe, {
      method: "POST",
      body: JSON.stringify({
        use_llm_summary: els.autoProbeLlmToggle.checked,
        email_to: els.autoProbeEmail.value.trim() || null,
      }),
    });
    renderAutoProbeResult(payload);
  } catch (error) {
    els.autoProbeResult.innerHTML = `<div class="detail-empty">${escapeHtml(error.message)}</div>`;
  } finally {
    setAutoProbeLoading(false);
  }
}

function setAutoProbeLoading(value) {
  els.runAutoProbeButton.disabled = value;
  els.autoProbeForm.classList.toggle("loading", value);
}


function stopAutoProgressPolling() {
  if (!state.autoProgressTimer) return;
  window.clearTimeout(state.autoProgressTimer);
  state.autoProgressTimer = null;
}

function scheduleAutoProgressPolling(payload = null) {
  stopAutoProgressPolling();
  if (state.mode !== "auto") return;
  const scheduler = payload?.scheduler || state.autoScheduler;
  const activeCount = (payload?.active_runs || []).length;
  if (!scheduler?.running && activeCount === 0) return;
  const intervalSeconds = Number(scheduler?.interval_seconds || 30);
  const delay = activeCount > 0 ? 2000 : Math.max(5000, Math.min(intervalSeconds * 1000, 15000));
  state.autoProgressTimer = window.setTimeout(() => {
    state.autoProgressTimer = null;
    loadAutoProgress({ quiet: true });
  }, delay);
}

async function loadAutoProgress({ quiet = false } = {}) {
  let payload = null;
  if (!quiet && els.autoProgressPanel) {
    els.autoProgressPanel.innerHTML = `<div class="detail-empty">正在读取自动诊断进度...</div>`;
  }
  try {
    payload = await request(api.autoProgress);
    if (payload.scheduler) {
      state.autoScheduler = payload.scheduler;
      renderAutoScheduler(payload.scheduler);
    }
    renderAutoProgress(payload);
    maybeRefreshAutoReports(payload);
  } catch (error) {
    if (!quiet) {
      els.autoProgressPanel.innerHTML = `<div class="detail-empty">${escapeHtml(error.message)}</div>`;
    }
  } finally {
    scheduleAutoProgressPolling(payload);
  }
}

function renderAutoProgress(payload) {
  const active = payload.active_runs || [];
  const recent = (payload.recent_runs || []).filter((row) => row.finished_at).slice(0, 3);
  if (!active.length && !recent.length && !payload.current_schedule) {
    els.autoProgressPanel.innerHTML = `
      <div class="progress-empty">
        <strong>暂无运行记录</strong>
        <span>启动自动诊断后，这里会显示供光计划检查、证据查询、故障判断和报告生成等阶段。</span>
      </div>
    `;
    return;
  }
  const latestRecent = recent[0] || null;
  els.autoProgressPanel.innerHTML = `
    <div class="progress-layout">
      ${active.length ? renderActiveProgress(active) : renderIdleProgress(latestRecent, payload.scheduler, payload.current_schedule)}
      ${renderProgressContext(payload.scheduler, payload.current_schedule)}
    </div>
    ${recent.length ? renderRecentProgress(recent) : ""}
  `;
}

function renderActiveProgress(activeRuns) {
  return `
    <div class="progress-group">
      <div class="progress-group-title">当前诊断 · ${activeRuns.length}</div>
      ${activeRuns.map(renderProgressCard).join("")}
    </div>
  `;
}

function renderIdleProgress(latestRecent, scheduler, currentSchedule) {
  if (latestRecent?.stage === "skipped_non_operation") {
    const schedule = latestRecent.schedule || {};
    return `
      <div class="progress-card schedule-skip">
        <div class="progress-topline">
          <strong>今日不执行自动诊断</strong>
          ${statusChip("skipped", "已跳过")}
        </div>
        <div class="progress-summary">
          ${escapeHtml(latestRecent.summary || `今日计划为 ${schedule.status_cn || schedule.status || "非 Operation"}，不进行诊断。`)}
        </div>
        <div class="progress-meta">
          <span>日期：${escapeHtml(schedule.date || "未知")}</span>
          <span>状态：${escapeHtml(schedule.status_cn || schedule.status || "非 Operation")}</span>
        </div>
      </div>
    `;
  }
  if (currentSchedule && currentSchedule.status !== "Operation" && scheduler?.require_operation_schedule) {
    return `
      <div class="progress-card schedule-skip">
        <div class="progress-topline">
          <strong>今日不是 Operation</strong>
          ${statusChip("skipped", "不会诊断")}
        </div>
        <div class="progress-summary">
          ${escapeHtml(currentSchedule.error || `今日计划为 ${currentSchedule.status_cn || currentSchedule.status}，自动束流诊断会跳过。`)}
        </div>
        <div class="progress-meta">
          <span>日期：${escapeHtml(currentSchedule.date || "未知")}</span>
          <span>状态：${escapeHtml(currentSchedule.status_cn || currentSchedule.status || "未知")}</span>
        </div>
      </div>
    `;
  }
  const runningText = scheduler?.running ? "等待下一轮 30s 自动诊断。" : "自动诊断已停止。";
  return `
    <div class="progress-card idle">
      <div class="progress-topline">
        <strong>${escapeHtml(runningText)}</strong>
        ${statusChip(scheduler?.running ? "running" : "neutral", scheduler?.running ? "等待中" : "已停止")}
      </div>
      ${latestRecent ? `<div class="progress-summary">最近一次：${escapeHtml(latestRecent.summary || latestRecent.stage)}</div>` : ""}
    </div>
  `;
}

function renderProgressContext(scheduler, currentSchedule) {
  const scheduleText = currentSchedule
    ? `${currentSchedule.date || ""} · ${currentSchedule.status_cn || currentSchedule.status || "未知"}`
    : "供光计划未读取";
  return `
    <aside class="progress-context">
      <div><span>束流 PV</span><strong>${escapeHtml(scheduler?.beam_channel || "RNG:BEAM:CURR")}</strong></div>
      <div><span>今日计划</span><strong>${escapeHtml(scheduleText)}</strong></div>
      <div><span>数据来源</span><strong>${escapeHtml(scheduler?.data_source_backend || "http")}</strong></div>
    </aside>
  `;
}

function renderRecentProgress(rows) {
  return `
    <div class="progress-group">
      <div class="progress-group-title">最近完成 · ${rows.length}</div>
      <div class="progress-mini-list">
        ${rows.map(renderProgressMini).join("")}
      </div>
    </div>
  `;
}

function renderProgressCard(row) {
  return `
    <article class="progress-card">
      <div class="progress-topline">
        <strong>${escapeHtml(stageLabel(row.stage))}</strong>
        ${statusChip(row.status || "running", actionLabel(row.action || row.status))}
      </div>
      <div class="progress-summary">${escapeHtml(row.summary || "")}</div>
      <div class="progress-bar"><span style="width:${progressStagePercent(row.stage)}%"></span></div>
      <div class="progress-meta">
        <span>窗口：${escapeHtml(formatTimeWindow(row.detect_window))}</span>
        <span>已用时：${escapeHtml(formatDuration(row.elapsed_seconds))}</span>
      </div>
    </article>
  `;
}

function renderProgressMini(row) {
  return `
    <div class="progress-mini ${escapeAttr(row.status || "neutral")}">
      <strong>${escapeHtml(stageLabel(row.stage))}</strong>
      <span>${escapeHtml(row.summary || "")}</span>
      <em>${escapeHtml(formatTime(row.finished_at || row.updated_at || row.started_at))} · ${escapeHtml(formatDuration(row.elapsed_seconds))}</em>
    </div>
  `;
}

function stageLabel(stage) {
  const labels = {
    schedule_check: "检查供光计划",
    skipped_non_operation: "非 Operation，跳过",
    skipped_previous_running: "上一轮仍在运行",
    fetch_evidence: "查询束流与 PV 证据",
    classify: "判定束流状态",
    summarize: "生成诊断报告",
    notify: "记录通知",
    incident_update: "更新故障事件",
    completed: "完成本轮诊断",
    error: "诊断异常",
    schedule_error: "供光计划异常",
  };
  return labels[stage] || stage || "自动诊断";
}

function actionLabel(action) {
  const labels = {
    running: "运行中",
    skipped: "已跳过",
    normal: "正常",
    recovered: "已恢复",
    new_incident: "新故障",
    updated_incident: "持续故障",
    error: "异常",
    completed: "完成",
    failed: "失败",
  };
  return labels[action] || action || "状态";
}

function progressStagePercent(stage) {
  const values = {
    schedule_check: 12,
    fetch_evidence: 38,
    classify: 58,
    summarize: 76,
    notify: 88,
    incident_update: 88,
    completed: 100,
    skipped_non_operation: 100,
    error: 100,
    schedule_error: 100,
  };
  return values[stage] || 24;
}

function renderAutoProbeResult(payload) {
  const fault = payload.fault_info || {};
  const beamInfo = payload.beam_info || {};
  const beam = beamInfo.evidence || {};
  const series = beamInfo.series || {};
  const email = payload.email || {};
  const faultLabel = fault.fault_present
    ? `${fault.classification || "fault"} · ${fault.severity || "unknown"}`
    : "未发现明确故障";
  const cause = fault.primary_cause?.pv || fault.primary_cause?.cause_type || "暂无主原因";
  els.autoProbeResult.innerHTML = `
    <section class="probe-card">
      <div class="probe-head">
        <div>
          <strong>${escapeHtml(faultLabel)}</strong>
          <span>${escapeHtml(payload.detect_window?.start || "")} 至 ${escapeHtml(payload.detect_window?.end || "")}</span>
        </div>
        ${statusChip(payload.status === "ok" ? (fault.fault_present ? "failed" : "completed") : "failed", payload.diagnosis_status || payload.status)}
      </div>
      <div class="summary-metrics compact-metrics">
        <div><span>束流样本</span><strong>${escapeHtml(series.sample_count ?? beam.sample_count ?? 0)}</strong></div>
        <div><span>最小值</span><strong>${formatNumber(beam.min ?? series.summary?.min)}</strong></div>
        <div><span>中位数</span><strong>${formatNumber(beam.median ?? series.summary?.median)}</strong></div>
        <div><span>主原因</span><strong>${escapeHtml(cause)}</strong></div>
      </div>
      <div class="markdown-body">${renderMarkdown(payload.report || payload.summary || "无诊断结果。")}</div>
      <div class="candidate-meta">
        邮件：${escapeHtml(email.requested ? `${email.status}${email.sent ? " / sent" : ""}` : "未请求发送")}
        ${email.error ? ` · ${escapeHtml(email.error)}` : ""}
        ${email.hint ? ` · ${escapeHtml(email.hint)}` : ""}
      </div>
      ${renderJsonDetails("查看故障信息和束流信息", {
        fault_info: payload.fault_info,
        beam_info: payload.beam_info,
        mode_info: payload.mode_info,
        alarm_info: payload.alarm_info,
        quadrupole_power: payload.quadrupole_power,
        email: payload.email,
        data_source: payload.data_source,
      })}
    </section>
  `;
}

function maybeRefreshAutoReports(payload) {
  const activeCount = (payload.active_runs || []).length;
  const recent = payload.recent_runs || [];
  const signature = recent
    .slice(0, 3)
    .map((row) => `${row.run_uid}:${row.action}:${row.stage}:${row.finished_at || row.updated_at || ""}`)
    .join("|");
  const now = Date.now();
  const schedulerRunning = payload.scheduler?.running;
  const significantChange = signature && signature !== state.autoLastProgressSignature;
  const due = schedulerRunning && now - state.autoLastReportRefreshAt > 30000;
  state.autoLastProgressSignature = signature;
  if (activeCount === 0 && (significantChange || due)) {
    loadAutoReports({ quiet: true });
  }
}

async function loadAutoReports({ quiet = false } = {}) {
  if (!quiet) {
    els.autoReportList.innerHTML = `<div class="detail-empty">正在加载自动诊断报告...</div>`;
  }
  try {
    const data = await request(api.autoReports);
    state.autoLastReportRefreshAt = Date.now();
    state.autoReports = data.reports || [];
    if (data.scheduler) renderAutoScheduler(data.scheduler);
    renderAutoReportList(state.autoReports);
    if (
      state.selectedAutoIncidentUid
      && !state.autoReports.some((report) => report.incident_uid === state.selectedAutoIncidentUid)
    ) {
      clearSelectedAutoReport();
    }
  } catch (error) {
    if (!quiet) {
      els.autoReportList.innerHTML = `<div class="detail-empty">${escapeHtml(error.message)}</div>`;
    }
  }
}

function renderAutoReportList(reports) {
  if (!reports.length) {
    if (!state.mockAutoReportVisible) {
      els.autoReportList.innerHTML = `<div class="detail-empty">暂无故障报告。后台自动诊断只有在发现束流故障后才会生成报告。</div>`;
      return;
    }
    reports = [MOCK_AUTO_REPORT];
  }
  const grouped = groupReportsByYearMonthDay(reports);
  let yearIndex = 0;
  els.autoReportList.innerHTML = [...grouped.entries()]
    .map(([year, months]) => {
      const open = shouldOpenReportGroup(months) || yearIndex === 0;
      yearIndex += 1;
      return `
      <details class="report-year" ${open ? "open" : ""}>
        <summary>${escapeHtml(formatReportYear(year))}</summary>
        ${[...months.entries()].map(([month, days], index) => renderReportMonth(month, days, open && index === 0)).join("")}
      </details>
    `;
    })
    .join("");
  els.autoReportList.querySelectorAll("[data-incident]").forEach((button) => {
    button.addEventListener("click", () => openAutoReport(button.dataset.incident));
  });
  els.autoReportList.querySelectorAll("[data-report-menu]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleAutoReportMenu(button.dataset.incident);
    });
  });
  els.autoReportList.querySelectorAll("[data-report-delete]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      closeAutoReportMenus();
      deleteAutoReport(button.dataset.incident);
    });
  });
}

function renderReportMonth(month, days, defaultOpen = false) {
  const open = shouldOpenReportGroup(days) || defaultOpen;
  return `
    <details class="report-month" ${open ? "open" : ""}>
      <summary>${escapeHtml(formatReportMonth(month))}</summary>
      ${[...days.entries()].map(([day, items], index) => renderReportDay(day, items, open && index === 0)).join("")}
    </details>
  `;
}

function renderReportDay(day, reports, defaultOpen = false) {
  const open = reports.some((report) => report.incident_uid === state.selectedAutoIncidentUid) || defaultOpen;
  return `
    <details class="report-day" ${open ? "open" : ""}>
      <summary>${escapeHtml(formatReportDay(day))} · ${reports.length}</summary>
      <div class="report-list">
        ${reports.map(renderReportItem).join("")}
      </div>
    </details>
  `;
}

function renderReportItem(report) {
  const title = `${report.classification || "fault"} · ${report.severity || "unknown"}`;
  const cause = report.primary_cause?.pv || report.primary_cause?.cause_type || "未定位主原因";
  const active = report.incident_uid === state.selectedAutoIncidentUid ? " active" : "";
  return `
    <article class="report-item${active}">
      <button class="report-main" type="button" data-incident="${escapeAttr(report.incident_uid)}">
        <div class="report-title-row">
          <strong>${escapeHtml(title)}</strong>
          ${statusChip(report.status || "completed", reportStatusLabel(report.status))}
        </div>
        <div class="report-time">${escapeHtml(formatTime(report.first_seen_at))}</div>
        <div class="report-cause">${escapeHtml(cause)}</div>
      </button>
      <div class="report-menu-wrap">
        <button class="report-menu-button" type="button" data-report-menu data-incident="${escapeAttr(report.incident_uid)}" aria-label="诊断报告操作">...</button>
        <div class="report-menu" data-report-menu-panel="${escapeAttr(report.incident_uid)}" hidden>
          <button class="danger-text" type="button" data-report-delete data-incident="${escapeAttr(report.incident_uid)}">删除</button>
        </div>
      </div>
    </article>
  `;
}

function toggleAutoReportMenu(incidentUid) {
  const panel = [...els.autoReportList.querySelectorAll("[data-report-menu-panel]")]
    .find((item) => item.dataset.reportMenuPanel === incidentUid);
  const willOpen = panel?.hidden;
  closeAutoReportMenus();
  if (panel && willOpen) {
    panel.hidden = false;
    state.openAutoReportMenuUid = incidentUid;
  }
}

function closeAutoReportMenus() {
  els.autoReportList.querySelectorAll("[data-report-menu-panel]").forEach((panel) => {
    panel.hidden = true;
  });
  state.openAutoReportMenuUid = null;
}

async function deleteAutoReport(incidentUid) {
  if (incidentUid === MOCK_AUTO_REPORT.incident_uid) {
    state.mockAutoReportVisible = false;
    if (state.selectedAutoIncidentUid === incidentUid) closeAutoReportModal();
    renderAutoReportList(state.autoReports);
    return;
  }
  const report = state.autoReports.find((item) => item.incident_uid === incidentUid);
  const title = report ? `${report.classification || "fault"} · ${formatTime(report.first_seen_at)}` : incidentUid;
  if (!window.confirm(`确定删除诊断报告「${title}」吗？这个操作不可恢复。`)) return;
  try {
    await request(api.deleteAutoReport(incidentUid), { method: "DELETE" });
    state.autoReports = state.autoReports.filter((item) => item.incident_uid !== incidentUid);
    if (state.selectedAutoIncidentUid === incidentUid) {
      closeAutoReportModal();
    }
    renderAutoReportList(state.autoReports);
  } catch (error) {
    window.alert(`删除诊断报告失败：${error.message}`);
  }
}

function reportStatusLabel(status) {
  const labels = {
    active: "持续中",
    closed: "已恢复确认",
    completed: "完成",
    failed: "失败",
  };
  return labels[status] || status || "状态";
}

function groupReportsByYearMonthDay(reports) {
  const grouped = new Map();
  for (const report of reports) {
    const day = report.report_day || datePart(report.first_seen_at) || "未知日期";
    const month = report.report_month || monthPart(day) || "未知月份";
    const year = yearPart(month) || yearPart(day) || "未知年份";
    if (!grouped.has(year)) grouped.set(year, new Map());
    const months = grouped.get(year);
    if (!months.has(month)) months.set(month, new Map());
    const days = months.get(month);
    if (!days.has(day)) days.set(day, []);
    days.get(day).push(report);
  }
  return grouped;
}

function countReportsInYear(months) {
  return [...months.values()].reduce((sum, days) => sum + countReports(days), 0);
}

function countReports(days) {
  return [...days.values()].reduce((sum, items) => sum + items.length, 0);
}

function shouldOpenReportGroup(group) {
  for (const value of group.values()) {
    if (Array.isArray(value)) {
      if (value.some((report) => report.incident_uid === state.selectedAutoIncidentUid)) return true;
    } else if (shouldOpenReportGroup(value)) {
      return true;
    }
  }
  return false;
}

function datePart(value) {
  if (!value) return "";
  const text = String(value);
  const match = text.match(/\d{4}-\d{2}-\d{2}/);
  return match ? match[0] : "";
}

function monthPart(value) {
  if (!value) return "";
  const text = String(value);
  const match = text.match(/\d{4}-\d{2}/);
  return match ? match[0] : "";
}

function yearPart(value) {
  if (!value) return "";
  const text = String(value);
  const match = text.match(/\d{4}/);
  return match ? match[0] : "";
}

function formatReportYear(year) {
  return /^\d{4}$/.test(year) ? `${year} 年` : year;
}

function formatReportMonth(month) {
  const match = String(month).match(/^(\d{4})-(\d{2})$/);
  return match ? `${match[2]} 月` : month;
}

function formatReportDay(day) {
  const match = String(day).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return match ? `${match[2]} 月 ${match[3]} 日` : day;
}

async function openAutoReport(incidentUid) {
  state.selectedAutoIncidentUid = incidentUid;
  markSelectedAutoReport();
  openAutoReportModal();
  els.autoReportInlineTitle.textContent = "自动诊断报告";
  setStatus(els.autoReportInlineStatus, "running", "加载中");
  els.autoReportInlineDetail.innerHTML = `<div class="detail-empty">正在加载报告详情...</div>`;
  els.autoBeamChart.innerHTML = `<div class="detail-empty">正在等待报告时间窗口...</div>`;
  if (incidentUid === MOCK_AUTO_REPORT.incident_uid) {
    const detail = { report: MOCK_AUTO_REPORT, notifications: [] };
    renderAutoReportDetail(detail);
    renderBeamChart(els.autoBeamChart, mockBeamSeries(), "测试报告对应束流曲线");
    return;
  }
  try {
    const detail = await request(api.autoReport(incidentUid));
    renderAutoReportDetail(detail);
    const window = getReportBeamWindow(detail.report || {});
    if (window) {
      try {
        await loadBeamChart(
          els.autoBeamChart,
          window.start,
          window.end,
          "报告对应束流曲线",
        );
      } catch (chartError) {
        els.autoBeamChart.innerHTML = `<div class="detail-empty">报告已加载，但束流曲线获取失败：${escapeHtml(chartError.message)}</div>`;
      }
    } else {
      els.autoBeamChart.innerHTML = `<div class="detail-empty">该报告没有可用于读取束流曲线的时间窗口。</div>`;
    }
  } catch (error) {
    setStatus(els.autoReportInlineStatus, "failed");
    els.autoReportInlineDetail.innerHTML = `<div class="detail-empty">${escapeHtml(error.message)}</div>`;
    els.autoBeamChart.innerHTML = `<div class="detail-empty">${escapeHtml(error.message)}</div>`;
  }
}

function renderAutoReportDetail(detail) {
  const report = detail.report || {};
  els.autoReportInlineTitle.textContent = `${report.classification || "束流故障"} · ${formatTime(report.first_seen_at)}`;
  setStatus(els.autoReportInlineStatus, report.status || "completed", reportStatusLabel(report.status));
  els.autoReportInlineDetail.innerHTML = `
    ${renderReportOverview(report)}
    ${renderAnswer(report.report || "无报告正文。")}
    ${renderCandidateCauses(report.candidate_causes || [])}
    <div class="selected-report-actions">
      ${renderJsonDetails("展开诊断证据", report.evidence || {})}
      ${renderJsonDetails("展开通知记录", detail.notifications || [])}
    </div>
  `;
}

function clearSelectedAutoReport() {
  state.selectedAutoIncidentUid = null;
  els.autoReportInlineTitle.textContent = "选中报告";
  setStatus(els.autoReportInlineStatus, "neutral", "未选择");
  els.autoReportInlineDetail.innerHTML = `<div class="detail-empty">从左侧历史报告中选择一条记录后，这里会展示报告摘要、诊断结论和候选原因。</div>`;
  els.autoBeamChart.innerHTML = `<div class="detail-empty">选择报告后，会实时获取该报告时间范围内的束流曲线。</div>`;
  markSelectedAutoReport();
}

function openAutoReportModal() {
  els.autoReportModal.hidden = false;
}

function closeAutoReportModal() {
  els.autoReportModal.hidden = true;
  clearSelectedAutoReport();
}

function markSelectedAutoReport() {
  document.querySelectorAll(".report-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.incident === state.selectedAutoIncidentUid);
  });
}

function getReportBeamWindow(report) {
  const evidenceWindow = report.evidence?.detect_window;
  if (evidenceWindow?.start && evidenceWindow?.end) return evidenceWindow;
  if (report.first_seen_at && report.last_seen_at) {
    return { start: report.first_seen_at, end: report.last_seen_at };
  }
  return null;
}

function mockBeamSeries() {
  const samples = [
    ["2026-05-31T19:44:26+08:00", 498.4],
    ["2026-05-31T19:44:31+08:00", 497.8],
    ["2026-05-31T19:44:36+08:00", 420.2],
    ["2026-05-31T19:44:41+08:00", 130.7],
    ["2026-05-31T19:44:46+08:00", 38.5],
    ["2026-05-31T19:44:51+08:00", 30.2],
    ["2026-05-31T19:44:56+08:00", 28.9],
  ].map(([time, value]) => ({ time, value, nanosecs: 0 }));
  return {
    window: MOCK_AUTO_REPORT.evidence.detect_window,
    sample_count: samples.length,
    returned_count: samples.length,
    downsampled: false,
    summary: {
      min: 28.9,
      max: 498.4,
      median: 130.7,
      normal_range: [495, 501],
      decay_range: [490, 503],
      absolute_low_threshold: 100,
    },
    samples,
  };
}

function renderReportOverview(report) {
  const fields = [
    ["报告编号", report.incident_uid],
    ["状态", reportStatusLabel(report.status)],
    ["分类", report.classification],
    ["严重程度", report.severity],
    ["首次发现", formatTime(report.first_seen_at)],
    ["最近发现", formatTime(report.last_seen_at)],
    ["恢复确认时间", formatTime(report.recovered_at)],
  ];
  return `
    <section class="process-card">
      <h4>报告摘要</h4>
      <div class="info-grid">
        ${fields
          .filter(([, value]) => value)
          .map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`)
          .join("")}
      </div>
    </section>
  `;
}

function renderManualBeamResult(response) {
  setStatus(els.manualStatus, response.status === "failed" ? "failed" : response.diagnosis_status === "fault" ? "completed" : "neutral", response.diagnosis_status || response.status);
  const event = response.event || null;
  const evidence = response.evidence || {};
  els.manualBeamResult.innerHTML = `
    ${renderAnswer(response.final_answer || response.summary || response.error || "无诊断结果。")}
    ${renderManualMetrics(response, event, evidence)}
    ${event ? renderCandidateCauses(event.candidate_causes || []) : ""}
    ${renderJsonDetails("展开完整诊断结果", response)}
  `;
}

function renderManualDashboard(payload) {
  const diagnosis = payload.diagnosis || {};
  const event = diagnosis.event || null;
  const kpi = payload.kpi || {};
  const classification = event?.classification || diagnosis.diagnosis_status || "normal";
  const isDrop = classification === "drop";
  const isDecay = classification === "decay";
  setStatus(
    els.manualStatus,
    diagnosis.status === "failed" ? "failed" : diagnosis.diagnosis_status === "fault" ? "completed" : "neutral",
    diagnosis.diagnosis_status || diagnosis.status,
  );
  const tabButtons = [];
  const panels = [];
  if (isDrop) {
    tabButtons.push(`<button class="sub-tab active" type="button" data-subtab="beam">掉束</button>`);
    panels.push(`
      <section class="manual-subpanel" data-panel="beam">
        ${renderManualKpis(kpi)}
        ${renderDropCausePanel(event, payload.quadrupole_power || {})}
      </section>
    `);
  } else if (isDecay) {
    tabButtons.push(`<button class="sub-tab active" type="button" data-subtab="decay">Decay 原因</button>`);
    panels.push(`
      <section class="manual-subpanel" data-panel="decay">
        ${renderManualKpis(kpi)}
        ${renderDecayPvTables(payload.decay || {})}
      </section>
    `);
  } else {
    tabButtons.push(`<button class="sub-tab active" type="button" data-subtab="normal">束流状态</button>`);
    panels.push(`
      <section class="manual-subpanel" data-panel="normal">
        ${renderManualKpis(kpi)}
        <div class="detail-empty">该时间范围内未发现明确 drop 或 decay。</div>
      </section>
    `);
  }
  tabButtons.push(`<button class="sub-tab" type="button" data-subtab="report">LLM 诊断总结</button>`);
  panels.push(`
    <section class="manual-subpanel hidden" data-panel="report">
      ${renderAnswer(diagnosis.final_answer || diagnosis.summary || diagnosis.error || "无诊断结果。")}
      ${event ? renderCandidateCauses(event.candidate_causes || []) : ""}
      ${renderJsonDetails("展开完整诊断结果", diagnosis)}
    </section>
  `);
  els.manualBeamResult.innerHTML = `
    <div class="nsrl-tabs">
      ${tabButtons.join("")}
    </div>
    ${panels.join("")}
  `;
  renderBeamChart(els.manualBeamChart, payload.beam_series, "手动诊断束流强度");
  bindManualSubtabs();
}

function renderDropCausePanel(event, power) {
  return `
    ${event ? renderCandidateCauses(event.candidate_causes || []) : ""}
    ${renderQuadrupoleFaultTable(power)}
  `;
}

function renderManualKpis(kpi) {
  return `
    <div class="summary-metrics">
      <div class="metric"><span>束流样本点数</span><strong>${escapeHtml(kpi.beam_sample_count ?? 0)}</strong></div>
      <div class="metric"><span>故障判定</span><strong class="${kpi.fault_present ? "warn" : "ok"}">${kpi.fault_present ? "是" : "否"}</strong></div>
      <div class="metric"><span>故障类型</span><strong>${escapeHtml(kpi.classification || "normal")}</strong></div>
      <div class="metric"><span>报警 PV</span><strong>${escapeHtml(kpi.active_alarm_count ?? 0)}</strong></div>
      <div class="metric"><span>四极铁异常</span><strong>${escapeHtml(kpi.quadrupole_fault_count ?? 0)}</strong></div>
      <div class="metric"><span>数据源</span><strong>${escapeHtml(kpi.data_source_backend || "unknown")}</strong></div>
    </div>
  `;
}

function renderQuadrupoleFaultTable(power) {
  const faults = power.power_faults || [];
  return `
    <section class="process-card">
      <h4>四极铁电源异常候选</h4>
      <div class="table-wrap compact-table">
        <table>
          <thead><tr><th>PV</th><th>时间</th><th>前值</th><th>当前值</th><th>类型</th></tr></thead>
          <tbody>
            ${
              faults.length
                ? faults
                    .map(
                      (item) => `
                        <tr>
                          <td>${escapeHtml(item.channel_name)}</td>
                          <td>${escapeHtml(formatTime(item.fault_time))}</td>
                          <td>${escapeHtml(formatNumber(item.prev_val))}</td>
                          <td>${escapeHtml(formatNumber(item.curr_val))}</td>
                          <td>${escapeHtml(item.fault_type)}</td>
                        </tr>
                      `,
                    )
                    .join("")
                : `<tr><td colspan="5">未发现四极铁电源异常下降。</td></tr>`
            }
          </tbody>
        </table>
      </div>
      ${renderJsonDetails("展开四极铁诊断原始结果", power)}
    </section>
  `;
}

function renderDecayPvTables(decay) {
  const mode = decay.mode || {};
  const alarms = decay.alarm_samples || [];
  const active = decay.active_alarms || [];
  return `
    <section class="process-card">
      <h4>MODE 通道变化</h4>
      <div class="table-wrap compact-table">
        <table>
          <thead><tr><th>PV</th><th>值</th><th>时间</th></tr></thead>
          <tbody>
            ${
              (mode.zero_times || []).concat(mode.one_times || []).length
                ? (mode.zero_times || [])
                    .concat(mode.one_times || [])
                    .map((item) => `<tr><td>${escapeHtml(mode.pv)}</td><td>${escapeHtml(item.value)}</td><td>${escapeHtml(formatTime(item.time))}</td></tr>`)
                    .join("")
                : `<tr><td colspan="3">该时间范围内未查询到 MODE 变化。</td></tr>`
            }
          </tbody>
        </table>
      </div>
    </section>
    <section class="process-card">
      <h4>13 个 Decay 相关 PV</h4>
      <div class="table-wrap compact-table">
        <table>
          <thead><tr><th>PV</th><th>值</th><th>含义</th><th>时间</th></tr></thead>
          <tbody>
            ${
              alarms.length
                ? alarms
                    .map(
                      (item) => `
                        <tr>
                          <td>${escapeHtml(item.pv)}</td>
                          <td>${escapeHtml(item.value)}</td>
                          <td>${escapeHtml(item.meaning || "")}</td>
                          <td>${escapeHtml(formatTime(item.time))}</td>
                        </tr>
                      `,
                    )
                    .join("")
                : `<tr><td colspan="4">该时间范围内未查询到 Decay 报警 PV 变化。</td></tr>`
            }
          </tbody>
        </table>
      </div>
      ${active.length ? renderMiniCandidateList(active) : ""}
    </section>
  `;
}

function bindManualSubtabs() {
  const tabs = els.manualBeamResult.querySelectorAll("[data-subtab]");
  const panels = els.manualBeamResult.querySelectorAll("[data-panel]");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((item) => item.classList.remove("active"));
      tab.classList.add("active");
      panels.forEach((panel) => panel.classList.toggle("hidden", panel.dataset.panel !== tab.dataset.subtab));
    });
  });
}

function renderManualMetrics(response, event, evidence) {
  const beam = evidence.beam || {};
  const alarms = evidence.alarms || {};
  const power = evidence.quadrupole_power || {};
  const metrics = [
    ["诊断状态", response.diagnosis_status || response.status],
    ["束流中位数", beam.median !== undefined ? Number(beam.median).toFixed(3) : ""],
    ["束流最小值", beam.min !== undefined ? Number(beam.min).toFixed(3) : ""],
    ["MODE=0", evidence.mode?.has_zero ? "是" : "否"],
    ["报警数量", alarms.active_count ?? 0],
    ["四极铁异常", power.power_fault_count ?? 0],
  ];
  return `
    <section class="process-card">
      <h4>${escapeHtml(event ? `${event.classification} 证据` : "窗口证据")}</h4>
      <div class="summary-metrics">
        ${metrics
          .map(([label, value]) => `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`)
          .join("")}
      </div>
    </section>
  `;
}

async function loadBeamChart(container, start, end, title) {
  if (!container) return;
  container.innerHTML = `<div class="detail-empty">正在读取束流曲线...</div>`;
  const data = await request(api.beamSeries(start, end));
  renderBeamChart(container, data, title);
}

function renderBeamChart(container, data, title) {
  if (!container) return;
  const samples = data?.samples || [];
  if (!samples.length) {
    container.innerHTML = `<div class="detail-empty">该时间范围内没有查询到束流数据。</div>`;
    return;
  }
  const values = samples.map((item) => Number(item.value)).filter((value) => Number.isFinite(value));
  const summary = data.summary || {};
  const minValue = Math.min(...values, Number(summary.normal_range?.[0] ?? 495), Number(summary.absolute_low_threshold ?? 100));
  const maxValue = Math.max(...values, Number(summary.normal_range?.[1] ?? 501));
  const padded = padRange(minValue, maxValue);
  const width = 860;
  const height = 220;
  const pad = { left: 52, right: 18, top: 16, bottom: 34 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const xFor = (index) => pad.left + (samples.length === 1 ? 0 : (index / (samples.length - 1)) * plotWidth);
  const yFor = (value) => pad.top + ((padded.max - value) / (padded.max - padded.min || 1)) * plotHeight;
  const points = samples.map((item, index) => `${xFor(index).toFixed(2)},${yFor(Number(item.value)).toFixed(2)}`);
  const area = `${pad.left},${height - pad.bottom} ${points.join(" ")} ${pad.left + plotWidth},${height - pad.bottom}`;
  const normalLow = summary.normal_range?.[0];
  const normalHigh = summary.normal_range?.[1];
  container.innerHTML = `
    <div class="chart-wrap">
      <div class="chart-head">
        <div>
          <strong>${escapeHtml(title)}</strong>
          <div class="chart-meta">${escapeHtml(formatTimeWindow(data.window))} · ${data.sample_count || 0} 点${data.downsampled ? ` · 显示 ${data.returned_count}` : ""}</div>
        </div>
        <div class="chart-meta">min ${formatNumber(summary.min)} · median ${formatNumber(summary.median)} · max ${formatNumber(summary.max)}</div>
      </div>
      <svg class="beam-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="束流强度曲线">
        <line class="beam-axis" x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}"></line>
        <line class="beam-axis" x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}"></line>
        ${normalLow !== undefined ? `<line class="beam-threshold" x1="${pad.left}" y1="${yFor(Number(normalLow)).toFixed(2)}" x2="${width - pad.right}" y2="${yFor(Number(normalLow)).toFixed(2)}"></line>` : ""}
        ${normalHigh !== undefined ? `<line class="beam-threshold" x1="${pad.left}" y1="${yFor(Number(normalHigh)).toFixed(2)}" x2="${width - pad.right}" y2="${yFor(Number(normalHigh)).toFixed(2)}"></line>` : ""}
        <text class="beam-label" x="8" y="${yFor(padded.max).toFixed(2)}">${escapeHtml(formatNumber(padded.max))}</text>
        <text class="beam-label" x="8" y="${yFor(padded.min).toFixed(2)}">${escapeHtml(formatNumber(padded.min))}</text>
        <polygon class="beam-area" points="${area}"></polygon>
        <polyline class="beam-line" points="${points.join(" ")}"></polyline>
        <text class="beam-label" x="${pad.left}" y="${height - 10}">${escapeHtml(formatTime(samples[0]?.time))}</text>
        <text class="beam-label" text-anchor="end" x="${width - pad.right}" y="${height - 10}">${escapeHtml(formatTime(samples[samples.length - 1]?.time))}</text>
      </svg>
    </div>
  `;
}

function padRange(minValue, maxValue) {
  if (!Number.isFinite(minValue) || !Number.isFinite(maxValue)) {
    return { min: 0, max: 1 };
  }
  if (minValue === maxValue) {
    return { min: minValue - 1, max: maxValue + 1 };
  }
  const pad = (maxValue - minValue) * 0.08;
  return { min: minValue - pad, max: maxValue + pad };
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return number.toFixed(Math.abs(number) >= 100 ? 2 : 3);
}

function renderRunLoading() {
  setStatus(els.runStatus, "running", "加载中");
  els.drawerTitle.textContent = "诊断过程";
  els.runDetail.innerHTML = `<div class="detail-empty">正在加载运行详情...</div>`;
}

function renderRunError(message) {
  setStatus(els.runStatus, "failed");
  els.runDetail.innerHTML = `<div class="detail-empty">${escapeHtml(message)}</div>`;
}

function openProcessDrawer() {
  els.processDrawer.classList.add("open");
  els.processDrawer.setAttribute("aria-hidden", "false");
}

function closeProcessDrawer() {
  state.selectedRunUid = null;
  els.processDrawer.classList.remove("open");
  els.processDrawer.setAttribute("aria-hidden", "true");
  setStatus(els.runStatus, "neutral", "未选择");
  els.drawerTitle.textContent = "诊断过程";
  els.runDetail.innerHTML = `<div class="detail-empty">点击某次诊断运行后查看过程。</div>`;
  markSelectedRun();
}

function markSelectedRun() {
  document.querySelectorAll(".run-card").forEach((card) => card.classList.remove("selected"));
  if (!state.selectedRunUid) return;
  document.querySelectorAll(`[data-run="${cssEscape(state.selectedRunUid)}"]`).forEach((button) => {
    button.closest(".run-card")?.classList.add("selected");
  });
}

function renderAnswer(text) {
  return `<section class="answer-block markdown-body">${renderMarkdown(text)}</section>`;
}

function renderCandidateCauses(candidates) {
  if (!candidates.length) return "";
  return `
    <section class="process-card">
      <h4>候选原因</h4>
      <div class="candidate-list">
        ${candidates.map(renderCandidate).join("")}
      </div>
    </section>
  `;
}

function renderCandidate(item) {
  const title = item.description || item.cause_type || "候选原因";
  const meta = [
    item.pv,
    item.time,
    item.confidence !== undefined ? `confidence=${item.confidence}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return `
    <div class="candidate">
      <div class="candidate-title">${escapeHtml(title)}</div>
      <div class="candidate-meta">${escapeHtml(meta)}</div>
    </div>
  `;
}

function renderMiniCandidateList(candidates) {
  return `
    <div class="mini-candidates">
      ${candidates
        .map(
          (item) => `
            <div class="mini-candidate">
              <strong>${escapeHtml(item.description || item.cause_type || "候选原因")}</strong>
              <span>${escapeHtml([item.pv, item.time, item.confidence !== undefined ? `confidence=${item.confidence}` : null].filter(Boolean).join(" · "))}</span>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderJsonDetails(label, data) {
  return `
    <details class="json-details">
      <summary>${escapeHtml(label)}</summary>
      <pre class="json-block">${escapeHtml(JSON.stringify(data, null, 2))}</pre>
    </details>
  `;
}

function statusChip(status, label = null) {
  const normalized = status || "neutral";
  return `<span class="status-chip ${escapeAttr(normalized)}">${escapeHtml(label || normalized)}</span>`;
}

function setStatus(element, status, label) {
  const normalized = status || "neutral";
  element.className = `status-chip ${normalized}`;
  element.textContent = label || normalized;
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const message = data?.detail || data?.message || response.statusText;
    throw new Error(message);
  }
  return data;
}

function parseJsonField(value, label) {
  try {
    return value.trim() ? JSON.parse(value) : {};
  } catch (error) {
    throw new Error(`${label} 不是合法 JSON`);
  }
}

function setLoading(value) {
  els.sendChatButton.disabled = value;
  els.chatForm.classList.toggle("loading", value);
  els.sendChatButton.textContent = value ? "诊断中..." : "发送诊断";
}

function setManualLoading(value) {
  els.runManualBeamButton.disabled = value;
  els.manualBeamForm.classList.toggle("loading", value);
  els.runManualBeamButton.textContent = value ? "诊断中..." : "运行手动诊断";
}

function scrollMessagesToBottom() {
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

function formatTime(value) {
  if (!value) return "";
  return String(value).replace("T", " ").slice(0, 19);
}

function formatTimeWindow(timeWindow) {
  if (!timeWindow) return "";
  const start = formatTime(timeWindow.start);
  const end = formatTime(timeWindow.end);
  return start && end ? `${start} 至 ${end}` : "";
}

function formatDuration(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds)) return "";
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}m ${rest}s`;
}

function truncate(value, maxLength) {
  const text = String(value || "");
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
}

function renderMarkdown(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";

  const lines = text.split(/\r?\n/);
  const html = [];
  let listType = null;

  const closeList = () => {
    if (listType) {
      html.push(`</${listType}>`);
      listType = null;
    }
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    if (!line.trim()) {
      closeList();
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      closeList();
      const level = Math.min(heading[1].length + 2, 5);
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      if (listType !== "ul") {
        closeList();
        listType = "ul";
        html.push("<ul>");
      }
      html.push(`<li>${renderInlineMarkdown(bullet[1])}</li>`);
      continue;
    }

    const numbered = line.match(/^\d+\.\s+(.+)$/);
    if (numbered) {
      if (listType !== "ol") {
        closeList();
        listType = "ol";
        html.push("<ol>");
      }
      html.push(`<li>${renderInlineMarkdown(numbered[1])}</li>`);
      continue;
    }

    closeList();
    html.push(`<p>${renderInlineMarkdown(line)}</p>`);
  }
  closeList();
  return html.join("");
}

function renderInlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

function cssEscape(value) {
  if (window.CSS?.escape) return window.CSS.escape(value);
  return String(value).replaceAll('"', '\\"');
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}
