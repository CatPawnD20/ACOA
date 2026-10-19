"use strict";

let csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
const statusNode = document.querySelector("#control-status");
const refreshStatusNode = document.querySelector("#refresh-status");

function requestId() {
  return crypto.randomUUID();
}

async function applyControl(url, payload = {}) {
  const response = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: {"Content-Type": "application/json", "X-CSRF-Token": csrfToken},
    body: JSON.stringify({request_id: requestId(), ...payload}),
  });
  if (!response.ok) {
    throw new Error(`Control rejected (${response.status}).`);
  }
  window.location.reload();
}

async function runWithFeedback(button, action) {
  button.disabled = true;
  if (statusNode) statusNode.textContent = "Applying control…";
  try {
    await action();
  } catch (error) {
    if (statusNode) statusNode.textContent = error.message;
    button.disabled = false;
  }
}

for (const button of document.querySelectorAll("[data-control-url]")) {
  button.addEventListener("click", () => runWithFeedback(button, () => applyControl(button.dataset.controlUrl)));
}

for (const button of document.querySelectorAll("[data-task-action]")) {
  button.addEventListener("click", () => {
    if (button.dataset.confirm && !window.confirm(button.dataset.confirm)) return;
    runWithFeedback(button, () =>
      applyControl(`/api/tasks/${button.dataset.taskId}/${button.dataset.taskAction}`));
  });
}

document.querySelector("#limits-form")?.addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const data = new FormData(form);
  const integers = ["applications_per_day", "applications_per_week", "outreach_per_company",
    "outreach_per_contact", "tokens_per_task", "seconds_per_task", "progress_stall_timeout"];
  const decimals = ["currency_per_day", "currency_per_month"];
  const payload = {};
  for (const name of integers) payload[name] = data.get(name) === "" ? null : Number(data.get(name));
  for (const name of decimals) payload[name] = data.get(name) === "" ? null : data.get(name);
  payload.currency = data.get("currency") === "" ? null : data.get("currency").toUpperCase();
  payload.paid_services_enabled = data.has("paid_services_enabled");
  runWithFeedback(button, () => applyControl("/api/controls/limits", payload));
});

function words(value) {
  return String(value).replaceAll("_", " ");
}

function replaceList(identifier, items, emptyText, render) {
  const list = document.querySelector(identifier);
  if (!list) return;
  const nodes = items.map(render);
  if (nodes.length === 0) {
    const empty = document.createElement("li");
    empty.className = "empty";
    empty.textContent = emptyText;
    nodes.push(empty);
  }
  list.replaceChildren(...nodes);
}

function stackItem(title, lines, timestamp) {
  const item = document.createElement("li");
  const strong = document.createElement("strong");
  strong.textContent = title;
  item.append(strong);
  for (const line of lines) {
    const span = document.createElement("span");
    span.textContent = line;
    item.append(span);
  }
  if (timestamp) {
    const time = document.createElement("time");
    time.textContent = timestamp;
    item.append(time);
  }
  return item;
}

function auditItem(event) {
  const item = document.createElement("li");
  const time = document.createElement("time");
  const category = document.createElement("strong");
  const summary = document.createElement("span");
  const reference = document.createElement("code");
  time.textContent = event.recorded_at;
  category.textContent = words(event.category);
  summary.textContent = `${words(event.action)} · ${words(event.state)}`;
  reference.textContent = event.reference;
  item.append(time, category, summary, reference);
  return item;
}

function sameIdentifiers(selector, attribute, records, key) {
  const current = new Set([...document.querySelectorAll(selector)].map((node) => node.dataset[attribute]));
  const incoming = new Set(records.map((record) => record[key]));
  return current.size === incoming.size && [...current].every((identifier) => incoming.has(identifier));
}

function updateSnapshot(snapshot) {
  if (!sameIdentifiers("[data-application-row]", "applicationRow", snapshot.applications, "application_id") ||
      !sameIdentifiers("[data-company-row]", "companyRow", snapshot.companies, "company_id") ||
      !sameIdentifiers("[data-task-row]", "taskRow", snapshot.tasks, "task_id")) {
    window.location.reload();
    return;
  }
  document.querySelector("#snapshot-time").textContent = snapshot.generated_at;
  for (const node of document.querySelectorAll("[data-metric]")) {
    node.textContent = snapshot.performance[node.dataset.metric];
  }
  for (const node of document.querySelectorAll("[data-performance]")) {
    node.textContent = snapshot.performance[node.dataset.performance];
  }
  document.querySelector('[data-authority="revision"]').textContent = snapshot.authority.revision;
  document.querySelector('[data-authority="paused"]').textContent = snapshot.authority.paused ? "paused" : "running";
  document.querySelector('[data-authority="dry_run"]').textContent = snapshot.authority.dry_run ? "dry run" : "live capable";
  document.querySelector('[data-authority="external_actions"]').textContent =
    `external actions ${snapshot.authority.external_actions_enabled ? "enabled" : "disabled"}`;
  for (const application of snapshot.applications) {
    const row = document.querySelector(`[data-application-row="${application.application_id}"]`);
    row.querySelector("[data-application-state]").textContent = words(application.state);
    row.querySelector("[data-submission-state]").textContent = words(application.submission_state);
  }
  for (const company of snapshot.companies) {
    const counts = document.querySelector(`[data-company-row="${company.company_id}"] [data-company-counts]`);
    counts.textContent = `${company.open_application_count} open / ${company.application_count} total`;
  }
  replaceList("#waiting-list", snapshot.waiting_items, "No tasks need a decision.", (item) =>
    stackItem(words(item.task_kind), [`Question ${item.question_id}`], item.waiting_since));
  replaceList("#cost-list", snapshot.costs, "No recorded cost.", (item) =>
    stackItem(`${item.currency} ${item.consumed}`, [
      `${item.reserved} reserved`, `${item.unsettled_count} unsettled`,
    ]));
  for (const task of snapshot.tasks) {
    const row = document.querySelector(`[data-task-row="${task.task_id}"]`);
    const state = row.querySelector("[data-task-state]");
    if (state.textContent !== words(task.state) && row.querySelector("[data-task-action]")) {
      window.location.reload();
      return;
    }
    state.textContent = words(task.state);
    row.querySelector("[data-task-attempts]").textContent = task.attempt_count;
    row.querySelector("[data-task-next]").textContent = task.next_run_at;
    row.querySelector("[data-task-updated]").textContent = task.updated_at;
  }
  replaceList("#notification-list", snapshot.notifications, "No important notifications.", (item) =>
    stackItem(words(item.kind), [`${item.urgency} · ${item.state} · ${item.application_reference}`], item.created_at));
  replaceList("#daily-report-list", snapshot.daily_reports, "No closed daily reports.", (item) =>
    stackItem(`${item.window_start.slice(0, 10)} → ${item.window_end.slice(0, 10)}`, [
      `${item.incoming_count} incoming · ${item.classified_count} classified · ${item.immediate_count} immediate`,
      `${item.reply_draft_count} reply drafts · ${item.followup_draft_count} follow-up drafts`,
    ]));
  replaceList("#audit-list", snapshot.audit_events, "No audit activity.", auditItem);
}

let refreshRunning = false;
async function refreshDashboard() {
  if (refreshRunning || document.hidden) return;
  refreshRunning = true;
  try {
    const response = await fetch(`/api/dashboard${window.location.search}`, {
      credentials: "same-origin",
      cache: "no-store",
      headers: {"Accept": "application/json"},
    });
    if (!response.ok) throw new Error(`Refresh failed (${response.status}).`);
    csrfToken = response.headers.get("X-CSRF-Token") || csrfToken;
    updateSnapshot(await response.json());
    if (refreshStatusNode) refreshStatusNode.textContent = "· live";
  } catch (error) {
    if (refreshStatusNode) refreshStatusNode.textContent = `· ${error.message}`;
  } finally {
    refreshRunning = false;
  }
}

window.setInterval(refreshDashboard, 15000);
