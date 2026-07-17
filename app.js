/* Pharma Guidelines RAG — single-file frontend (no build step). */
"use strict";

const $ = (id) => document.getElementById(id);
let TOKEN = localStorage.getItem("token") || "";
let ROLE = localStorage.getItem("role") || "";
let EMAIL = localStorage.getItem("email") || "";
let currentSession = null;
let streaming = false;

/* ---------- API helper ---------- */
async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (TOKEN) headers["Authorization"] = "Bearer " + TOKEN;
  const r = await fetch(path, { ...opts, headers });
  if (r.status === 401) { logout(); throw new Error("Session expired"); }
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return r.json();
}

/* ---------- Views ---------- */
function show(view) {
  ["view-auth", "view-main", "view-admin"].forEach((v) => $(v).classList.add("hidden"));
  $(view).classList.remove("hidden");
}

function logout() {
  TOKEN = ROLE = EMAIL = "";
  localStorage.clear();
  show("view-auth");
}

/* ---------- Auth ---------- */
let authMode = "login";
$("tab-login").onclick = () => setAuthMode("login");
$("tab-register").onclick = () => setAuthMode("register");
function setAuthMode(m) {
  authMode = m;
  $("tab-login").classList.toggle("active", m === "login");
  $("tab-register").classList.toggle("active", m === "register");
  $("auth-invite").classList.toggle("hidden", m === "login");
  $("auth-submit").textContent = m === "login" ? "Sign in" : "Create account";
}

$("auth-form").onsubmit = async (e) => {
  e.preventDefault();
  $("auth-error").textContent = "";
  const body = { email: $("auth-email").value, password: $("auth-password").value };
  if (authMode === "register") body.invite_code = $("auth-invite").value;
  try {
    const res = await api("/api/auth/" + authMode, { method: "POST", body: JSON.stringify(body) });
    TOKEN = res.access_token; ROLE = res.role; EMAIL = res.email;
    localStorage.setItem("token", TOKEN);
    localStorage.setItem("role", ROLE);
    localStorage.setItem("email", EMAIL);
    enterApp();
  } catch (err) { $("auth-error").textContent = err.message; }
};

async function enterApp() {
  show("view-main");
  $("user-email").textContent = EMAIL;
  $("btn-admin").classList.toggle("hidden", ROLE !== "admin");
  $("messages").innerHTML = welcomeHtml();
  currentSession = null;
  loadSessions();
  loadModels();
}

function welcomeHtml() {
  return `<div class="msg assistant">Ask me anything about the pharmaceutical guideline
  library — or the live web. Use the <b>Source</b> selector to force guidelines-only or
  web-only answers. Citations like [1] link to the exact document and page.</div>`;
}

/* ---------- Models dropdown ---------- */
async function loadModels() {
  try {
    const models = await api("/api/models");
    const sel = $("sel-model");
    sel.innerHTML = '<option value="auto">Auto (rotate free models)</option>';
    for (const m of models) {
      const o = document.createElement("option");
      o.value = m.value; o.textContent = m.label;
      sel.appendChild(o);
    }
  } catch {}
}

/* ---------- Sessions ---------- */
async function loadSessions() {
  try {
    const sessions = await api("/api/chat/sessions");
    const list = $("session-list");
    list.innerHTML = "";
    for (const s of sessions) {
      const div = document.createElement("div");
      div.className = "session-item" + (currentSession === s.id ? " active" : "");
      const title = document.createElement("span");
      title.textContent = s.title;
      const del = document.createElement("span");
      del.className = "del"; del.textContent = "✕";
      del.onclick = async (e) => {
        e.stopPropagation();
        await api("/api/chat/sessions/" + s.id, { method: "DELETE" });
        if (currentSession === s.id) { currentSession = null; $("messages").innerHTML = welcomeHtml(); }
        loadSessions();
      };
      div.append(title, del);
      div.onclick = () => openSession(s.id);
      list.appendChild(div);
    }
  } catch {}
}

async function openSession(id) {
  const s = await api("/api/chat/sessions/" + id);
  currentSession = id;
  const box = $("messages");
  box.innerHTML = "";
  for (const m of s.messages) {
    box.appendChild(renderMsg(m.role, m.content, m.sources, m.model));
  }
  box.scrollTop = box.scrollHeight;
  loadSessions();
}

$("btn-new-chat").onclick = () => {
  currentSession = null;
  $("messages").innerHTML = welcomeHtml();
  loadSessions();
};

/* ---------- Rendering ---------- */
function md(text) {
  return DOMPurify.sanitize(marked.parse(text || ""));
}

function renderMsg(role, content, sources, model) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  if (role === "user") { div.textContent = content; return div; }
  div.innerHTML = md(content);
  if (sources && sources.length) div.appendChild(renderSources(sources));
  if (model) {
    const meta = document.createElement("div");
    meta.className = "meta"; meta.textContent = "· " + model;
    div.appendChild(meta);
  }
  return div;
}

function renderSources(sources) {
  const wrap = document.createElement("div");
  wrap.className = "sources";
  for (const s of sources) {
    const chip = document.createElement(s.url ? "a" : "span");
    chip.className = "source-chip " + (s.kind === "doc" ? "doc" : "web");
    chip.textContent = `[${s.n}] ${s.title}`.slice(0, 90);
    if (s.url) { chip.href = s.url; chip.target = "_blank"; chip.rel = "noopener"; }
    chip.title = s.title;
    wrap.appendChild(chip);
  }
  return wrap;
}

/* ---------- Ask (SSE over fetch) ---------- */
$("ask-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("ask-form").requestSubmit(); }
});

$("ask-form").onsubmit = async (e) => {
  e.preventDefault();
  if (streaming) return;
  const q = $("ask-input").value.trim();
  if (!q) return;
  $("ask-input").value = "";
  streaming = true;
  $("ask-btn").disabled = true;

  const box = $("messages");
  box.appendChild(renderMsg("user", q));
  const holder = document.createElement("div");
  holder.className = "msg assistant";
  holder.innerHTML = '<span class="spinner"></span> Searching…';
  box.appendChild(holder);
  box.scrollTop = box.scrollHeight;

  let text = "", sources = [], model = "";
  try {
    const r = await fetch("/api/chat/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer " + TOKEN },
      body: JSON.stringify({
        question: q, session_id: currentSession,
        mode: $("sel-mode").value, model: $("sel-model").value,
        agency: $("sel-agency").value,
      }),
    });
    if (!r.ok) {
      let msg = r.statusText;
      try { msg = (await r.json()).detail || msg; } catch {}
      throw new Error(msg);
    }
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const events = buf.split("\n\n");
      buf = events.pop();
      for (const ev of events) {
        let type = "", data = "";
        for (const line of ev.split("\n")) {
          if (line.startsWith("event:")) type = line.slice(6).trim();
          else if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        if (!type) continue;
        const payload = data ? JSON.parse(data) : null;
        if (type === "session") {
          if (!currentSession) { currentSession = payload.session_id; loadSessions(); }
        } else if (type === "sources") {
          sources = payload;
        } else if (type === "model") {
          model = payload;
        } else if (type === "delta") {
          text += payload;
          holder.innerHTML = md(text);
          box.scrollTop = box.scrollHeight;
        } else if (type === "error") {
          text += `\n\n**Error:** ${payload}`;
          holder.innerHTML = md(text);
        }
      }
    }
    holder.innerHTML = md(text || "_No answer produced._");
    if (sources.length) holder.appendChild(renderSources(sources));
    if (model) {
      const meta = document.createElement("div");
      meta.className = "meta"; meta.textContent = "· " + model;
      holder.appendChild(meta);
    }
  } catch (err) {
    holder.innerHTML = md("**Error:** " + err.message);
  } finally {
    streaming = false;
    $("ask-btn").disabled = false;
    box.scrollTop = box.scrollHeight;
  }
};

/* ---------- Sidebar buttons ---------- */
$("btn-logout").onclick = logout;
$("btn-apikey").onclick = async () => {
  const { api_key } = await api("/api/auth/api-key");
  prompt("Your API key (for MCP clients — send as X-API-Key header):", api_key);
};
$("btn-admin").onclick = () => { show("view-admin"); loadAdminTab("stats"); };
$("btn-back").onclick = () => show("view-main");

/* ---------- Admin ---------- */
document.querySelectorAll("#admin-tabs .tab").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll("#admin-tabs .tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    loadAdminTab(btn.dataset.tab);
  };
});

async function loadAdminTab(tab) {
  const c = $("admin-content");
  c.innerHTML = '<span class="spinner"></span>';
  try {
    if (tab === "stats") await tabStats(c);
    else if (tab === "drives") await tabDrives(c);
    else if (tab === "sync") await tabSync(c);
    else if (tab === "models") await tabModels(c);
    else if (tab === "users") await tabUsers(c);
  } catch (err) {
    c.innerHTML = `<div class="error">${err.message}</div>`;
  }
}

async function tabStats(c) {
  const s = await api("/api/admin/stats");
  c.innerHTML = `
    <div class="cards">
      <div class="card"><div class="big">${s.documents.indexed}</div><div class="label">documents indexed (of ${s.documents.total})</div></div>
      <div class="card"><div class="big">${s.pages.toLocaleString()}</div><div class="label">pages</div></div>
      <div class="card"><div class="big">${s.chunks.toLocaleString()}</div><div class="label">chunks</div></div>
      <div class="card"><div class="big">${s.vector_store.row_count.toLocaleString()}</div><div class="label">vectors (${s.vector_store.status})</div></div>
      <div class="card"><div class="big">${s.users}</div><div class="label">users</div></div>
      <div class="card"><div class="big">${s.documents.needs_ocr}</div><div class="label">need OCR</div></div>
      <div class="card"><div class="big">${s.documents.errors}</div><div class="label">errors</div></div>
    </div>
    <h3>LLM providers</h3>
    <table><tr><th>Provider</th><th>Configured</th><th>Used today</th><th>Daily budget</th><th>Status</th></tr>
    ${s.providers.map((p) => `<tr><td>${p.provider}</td>
      <td>${p.configured ? "✓" : "—"}</td><td>${p.used_today}</td><td>${p.daily_budget}</td>
      <td><span class="badge ${p.cooling_down ? "bad" : "ok"}">${p.cooling_down ? "cooling down" : "ready"}</span></td></tr>`).join("")}
    </table>
    <p style="margin-top:16px"><button id="btn-clear-cache">Clear answer cache</button></p>`;
  $("btn-clear-cache").onclick = async () => {
    await api("/api/admin/cache/clear", { method: "POST" });
    alert("Cache cleared");
  };
}

async function tabDrives(c) {
  const drives = await api("/api/admin/drives");
  c.innerHTML = `
    <div class="row-form">
      <input id="d-name" placeholder="Name (e.g. FDA Guidelines)">
      <input id="d-folder" placeholder="Google Drive folder ID" style="min-width:280px">
      <input id="d-agency" placeholder="Default agency (optional)">
      <button class="primary" id="d-add">Add drive</button>
    </div>
    <p class="muted">Share each folder with the service account email, then add its folder ID here.</p>
    <table><tr><th>Name</th><th>Folder ID</th><th>Agency</th><th>Last synced</th><th>Active</th><th></th></tr>
    ${drives.map((d) => `<tr><td>${d.name}</td><td><code>${d.folder_id}</code></td>
      <td>${d.default_agency || "—"}</td><td>${d.last_synced || "never"}</td>
      <td><span class="badge ${d.is_active ? "ok" : "bad"}">${d.is_active ? "active" : "off"}</span></td>
      <td><button data-toggle="${d.id}">Toggle</button> <button data-del="${d.id}">Delete</button></td></tr>`).join("")}
    </table>`;
  $("d-add").onclick = async () => {
    await api("/api/admin/drives", { method: "POST", body: JSON.stringify({
      name: $("d-name").value, folder_id: $("d-folder").value,
      default_agency: $("d-agency").value }) });
    loadAdminTab("drives");
  };
  c.querySelectorAll("[data-toggle]").forEach((b) => b.onclick = async () => {
    await api("/api/admin/drives/" + b.dataset.toggle, { method: "PATCH" });
    loadAdminTab("drives");
  });
  c.querySelectorAll("[data-del]").forEach((b) => b.onclick = async () => {
    if (confirm("Delete this drive config? (Indexed chunks stay until next sync)"))
      { await api("/api/admin/drives/" + b.dataset.del, { method: "DELETE" }); loadAdminTab("drives"); }
  });
}

async function tabSync(c) {
  const jobs = await api("/api/admin/sync/jobs");
  c.innerHTML = `
    <p><button class="primary" id="btn-sync">Run delta sync now</button>
    <span class="muted">Picks up new/changed/deleted files in all active drives.
    Bulk-load the initial 500k pages with the ingest CLI on your computer.</span></p>
    <table><tr><th>ID</th><th>Status</th><th>Stats</th><th>Started</th><th></th></tr>
    ${jobs.map((j) => `<tr><td>${j.id}</td>
      <td><span class="badge ${j.status === "done" ? "ok" : j.status === "error" ? "bad" : ""}">${j.status}</span></td>
      <td class="muted">${JSON.stringify(j.stats)}</td><td>${j.started_at}</td>
      <td><button data-log="${j.id}">Log</button></td></tr>`).join("")}
    </table><div id="job-log"></div>`;
  $("btn-sync").onclick = async () => {
    try { await api("/api/admin/sync", { method: "POST" }); } catch (e) { alert(e.message); }
    setTimeout(() => loadAdminTab("sync"), 800);
  };
  c.querySelectorAll("[data-log]").forEach((b) => b.onclick = async () => {
    const j = await api("/api/admin/sync/jobs/" + b.dataset.log);
    $("job-log").innerHTML = `<h4>Job ${j.id} log</h4><pre class="log">${j.log || "(empty)"}</pre>`;
  });
}

async function tabModels(c) {
  const models = await api("/api/admin/models");
  c.innerHTML = `
    <p><button class="primary" id="btn-refresh-models">↻ Refresh free models from all providers</button>
    <span class="muted">Queries every configured provider's live catalog. New free models appear here; toggle which ones users can pick.</span></p>
    <div id="refresh-result"></div>
    <table><tr><th>Provider</th><th>Model</th><th>Context</th><th>Active</th></tr>
    ${models.map((m) => `<tr><td>${m.provider}</td>
      <td>${m.display_name || m.model_id}<br><code class="muted">${m.model_id}</code></td>
      <td>${m.context_length ? m.context_length.toLocaleString() : "?"}</td>
      <td><input type="checkbox" data-model="${m.id}" ${m.is_active ? "checked" : ""}></td></tr>`).join("")}
    </table>`;
  $("btn-refresh-models").onclick = async () => {
    $("refresh-result").innerHTML = '<span class="spinner"></span> Querying providers…';
    const r = await api("/api/admin/models/refresh", { method: "POST" });
    $("refresh-result").innerHTML = `<p class="muted">Added ${r.added}, updated ${r.updated}.
      ${Object.entries(r.providers).map(([k, v]) => `${k}: ${v}`).join(" · ")}</p>`;
    setTimeout(() => loadAdminTab("models"), 1500);
  };
  c.querySelectorAll("[data-model]").forEach((cb) => cb.onchange = async () => {
    await api("/api/admin/models/" + cb.dataset.model, {
      method: "PATCH", body: JSON.stringify({ is_active: cb.checked }) });
  });
}

async function tabUsers(c) {
  const users = await api("/api/admin/users");
  c.innerHTML = `
    <table><tr><th>Email</th><th>Role</th><th>Active</th><th>Joined</th><th></th></tr>
    ${users.map((u) => `<tr><td>${u.email}</td><td>${u.role}</td>
      <td><span class="badge ${u.is_active ? "ok" : "bad"}">${u.is_active ? "yes" : "no"}</span></td>
      <td class="muted">${u.created_at.slice(0, 10)}</td>
      <td><button data-role="${u.id}" data-newrole="${u.role === "admin" ? "user" : "admin"}">
        Make ${u.role === "admin" ? "user" : "admin"}</button>
      <button data-active="${u.id}" data-newactive="${!u.is_active}">
        ${u.is_active ? "Disable" : "Enable"}</button>
      <button data-del="${u.id}" data-email="${u.email}">Delete</button></td></tr>`).join("")}
    </table>`;
  c.querySelectorAll("[data-role]").forEach((b) => b.onclick = async () => {
    try {
      await api("/api/admin/users/" + b.dataset.role, {
        method: "PATCH", body: JSON.stringify({ role: b.dataset.newrole }) });
      loadAdminTab("users");
    } catch (e) { alert(e.message); }
  });
  c.querySelectorAll("[data-del]").forEach((b) => b.onclick = async () => {
    if (!confirm(`Delete user ${b.dataset.email}? This also removes their chat history and cannot be undone.`)) return;
    try {
      await api("/api/admin/users/" + b.dataset.del, { method: "DELETE" });
      loadAdminTab("users");
    } catch (e) { alert(e.message); }
  });
  c.querySelectorAll("[data-active]").forEach((b) => b.onclick = async () => {
    await api("/api/admin/users/" + b.dataset.active, {
      method: "PATCH", body: JSON.stringify({ is_active: b.dataset.newactive === "true" }) });
    loadAdminTab("users");
  });
}

/* ---------- boot ---------- */
if (TOKEN) {
  api("/api/auth/me").then(enterApp).catch(logout);
} else {
  show("view-auth");
}
