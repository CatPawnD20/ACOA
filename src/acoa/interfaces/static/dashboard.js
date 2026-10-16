"use strict";

const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
const statusNode = document.querySelector("#control-status");

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
    "outreach_per_contact", "tokens_per_task", "seconds_per_task"];
  const decimals = ["currency_per_day", "currency_per_month"];
  const payload = {};
  for (const name of integers) payload[name] = data.get(name) === "" ? null : Number(data.get(name));
  for (const name of decimals) payload[name] = data.get(name) === "" ? null : data.get(name);
  payload.currency = data.get("currency") === "" ? null : data.get("currency").toUpperCase();
  runWithFeedback(button, () => applyControl("/api/controls/limits", payload));
});
