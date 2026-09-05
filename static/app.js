let TOKEN = localStorage.getItem("panel_token") || "";
let ACCOUNTS = [];

// ---------------- 登录 ----------------
async function doLogin() {
  const username = document.getElementById("username").value;
  const pw = document.getElementById("pw").value;
  const res = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password: pw }),
  });
  if (!res.ok) {
    document.getElementById("login-err").innerText = "账号或密码错误";
    return;
  }
  const data = await res.json();
  TOKEN = data.token;
  localStorage.setItem("panel_token", TOKEN);
  showApp();
}

function logout() {
  localStorage.removeItem("panel_token");
  TOKEN = "";
  document.getElementById("app-view").classList.add("hidden");
  document.getElementById("login-view").classList.remove("hidden");
}

function showApp() {
  document.getElementById("login-view").classList.add("hidden");
  document.getElementById("app-view").classList.remove("hidden");
  loadAccounts();
}

window.onload = () => {
  if (TOKEN) showApp();

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.add("hidden"));
      btn.classList.add("active");
      document.getElementById("tab-" + btn.dataset.tab).classList.remove("hidden");
      if (btn.dataset.tab === "bm") loadCredentials();
      if (btn.dataset.tab === "manage") fillManageBMSelect();
    });
  });
};

// ---------------- 通用请求 ----------------
async function api(path, options = {}) {
  options.headers = Object.assign({}, options.headers, { "Authorization": "Bearer " + TOKEN });
  const res = await fetch(path, options);
  if (res.status === 401) {
    logout();
    throw new Error("未授权，请重新登录");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail ? JSON.stringify(data.detail) : "请求失败");
  }
  return data;
}

async function apiJSON(path, body, method = "POST") {
  return api(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function money(cents, currency) {
  if (cents === undefined || cents === null) return "-";
  const v = Number(cents) / 100;
  return `${v.toFixed(2)} ${currency || ""}`;
}

// ---------------- 账户总览 ----------------
async function loadAccounts() {
  const tbody = document.getElementById("accounts-tbody");
  tbody.innerHTML = "<tr><td colspan='9'>加载中...</td></tr>";
  try {
    const res = await api("/api/accounts");
    ACCOUNTS = res.data || [];
    tbody.innerHTML = "";
    ACCOUNTS.forEach((a) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${a.bm_label || "-"}</td>
        <td>${a.name || "-"}</td>
        <td>${a.id}</td>
        <td>${a.account_status}</td>
        <td>${a.currency}</td>
        <td>${money(a.amount_spent, a.currency)}</td>
        <td>${a.has_spend_cap ? money(a.spend_cap, a.currency) : "无上限"}</td>
        <td>${a.has_spend_cap ? money(a.remaining_budget, a.currency) : "不限制"}</td>
        <td><input value="${a.note || ""}" onchange="saveNote('${a.id}', this.value)" placeholder="备注" style="width:120px"/></td>
      `;
      tbody.appendChild(tr);
    });
    const errBox = document.getElementById("accounts-errors");
    if (res.errors && res.errors.length) {
      errBox.innerHTML = res.errors
        .map((e) => `<div style="color:#d93025">「${e.credential}」凭证拉取失败：${e.error}</div>`)
        .join("");
    } else {
      errBox.innerHTML = "";
    }
    fillAccountSelects();
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan='9' style="color:red">加载失败：${e.message}</td></tr>`;
  }
}

async function saveNote(accountId, note) {
  try {
    await apiJSON(`/api/accounts/${accountId}/note`, { note });
  } catch (e) {
    alert("保存备注失败：" + e.message);
  }
}

function fillAccountSelects() {
  fillManageBMSelect();
}

// ---- 广告管理：BM -> 账户 级联选择 ----
function fillManageBMSelect() {
  const bmSelect = document.getElementById("manage-bm-select");
  const hint = document.getElementById("manage-empty-hint");
  if (!bmSelect) return;

  if (!ACCOUNTS.length) {
    bmSelect.innerHTML = "";
    document.getElementById("manage-account-select").innerHTML = "";
    if (hint) hint.classList.remove("hidden");
    return;
  }
  if (hint) hint.classList.add("hidden");

  const seen = new Map(); // credential_id -> bm_label
  ACCOUNTS.forEach((a) => {
    if (!seen.has(a.credential_id)) seen.set(a.credential_id, a.bm_label || "(未命名BM)");
  });
  bmSelect.innerHTML = Array.from(seen.entries())
    .map(([id, label]) => `<option value="${id}">${label}</option>`)
    .join("");
  onBMChangeForManage();
}

function onBMChangeForManage() {
  const bmId = document.getElementById("manage-bm-select").value;
  const accSelect = document.getElementById("manage-account-select");
  const filtered = ACCOUNTS.filter((a) => String(a.credential_id) === String(bmId));
  accSelect.innerHTML = filtered
    .map((a) => `<option value="${a.id}">${a.name} (${a.id})</option>`)
    .join("");
  onAccountChangeForManage();
}

// ---------------- BM 账号管理 ----------------
async function loadCredentials() {
  const tbody = document.getElementById("bm-tbody");
  tbody.innerHTML = "<tr><td colspan='6'>加载中...</td></tr>";
  try {
    const rows = await api("/api/credentials");
    tbody.innerHTML = "";
    rows.forEach((r) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${r.label}</td>
        <td>${r.bm_id || "-"}</td>
        <td><code>${r.token_preview}</code></td>
        <td>${r.is_active ? "启用" : "已停用"}</td>
        <td>${new Date(r.created_at).toLocaleString()}</td>
        <td>
          <button onclick="toggleCredential(${r.id}, ${!r.is_active})">${r.is_active ? "停用" : "启用"}</button>
          <button onclick="deleteCredential(${r.id})">删除</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan='6' style="color:red">加载失败：${e.message}</td></tr>`;
  }
}

async function addCredential() {
  const label = document.getElementById("bm-label").value;
  const bm_id = document.getElementById("bm-id").value;
  const access_token = document.getElementById("bm-token").value;
  const box = document.getElementById("bm-add-result");
  if (!label || !access_token) return (box.innerText = "请填写 BM 名称和令牌");
  box.innerText = "校验中...";
  try {
    await apiJSON("/api/credentials", { label, bm_id, access_token });
    box.innerText = "添加成功";
    document.getElementById("bm-label").value = "";
    document.getElementById("bm-id").value = "";
    document.getElementById("bm-token").value = "";
    loadCredentials();
    loadAccounts();
  } catch (e) {
    box.innerText = "添加失败：" + e.message;
  }
}

async function toggleCredential(id, newState) {
  try {
    await api(`/api/credentials/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: newState }),
    });
    loadCredentials();
    loadAccounts();
  } catch (e) {
    alert("操作失败：" + e.message);
  }
}

async function deleteCredential(id) {
  if (!confirm("确定删除这个 BM 凭证吗？该操作不可恢复。")) return;
  try {
    await api(`/api/credentials/${id}`, { method: "DELETE" });
    loadCredentials();
    loadAccounts();
  } catch (e) {
    alert("删除失败：" + e.message);
  }
}


// ---------------- 广告管理（点名称逐层下钻：系列 → 组 → 广告，字段对齐 Ads Manager）----------------
const MANAGE = {
  accountId: null,
  level: "campaigns", // "campaigns" | "adsets" | "ads"
  campaignId: null,
  campaignName: "",
  adsetId: null,
  adsetName: "",
  rawRows: [],
  sortKey: null,
  sortDir: 1, // 1 = 升序, -1 = 降序
  showCreateForm: false,
};

const MANAGE_COLUMNS = [
  { key: "name", label: "名称" },
  { key: "status", label: "状态" },
  { key: "budget_cents", label: "预算" },
  { key: "spend", label: "已花费金额" },
  { key: "purchases", label: "购物次数" },
  { key: "purchase_value", label: "购物转化价值" },
  { key: "roas", label: "广告花费回报(ROAS)-购物" },
  { key: "cost_per_purchase", label: "单次购物成本" },
  { key: "frequency", label: "频次" },
  { key: "impressions", label: "展示次数" },
  { key: "cpm", label: "CPM" },
  { key: "link_clicks", label: "链接点击量" },
  { key: "cost_per_link_click", label: "单次链接点击费用" },
  { key: "link_ctr", label: "链接点击率" },
  { key: "atc", label: "加入购物车次数" },
  { key: "checkout_initiated", label: "结账发起次数" },
  { key: "video_views", label: "视频播放量" },
  { key: "video_p50", label: "视频播放达50%次数" },
  { key: "video_p100", label: "视频播放达100%次数" },
  { key: null, label: "操作" },
];

function fmtNum(v, digits = 0) {
  if (v === null || v === undefined || v === "" || isNaN(v)) return "-";
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}
function fmtMoney(v) {
  if (v === null || v === undefined || isNaN(v)) return "-";
  return "$" + Number(v).toFixed(2);
}
function fmtPct(v) {
  if (v === null || v === undefined || isNaN(v)) return "-";
  return Number(v).toFixed(2) + "%";
}
function fmtRoas(v) {
  if (v === null || v === undefined) return "-";
  return Number(v).toFixed(2);
}

function escapeHtml(s) {
  return (s || "").replace(/\\/g, "\\\\").replace(/'/g, "\\'");
}

function renderManageHeader() {
  document.getElementById("manage-thead").innerHTML =
    "<tr>" +
    MANAGE_COLUMNS.map((c) => {
      if (!c.key) return `<th>${c.label}</th>`;
      const arrow = MANAGE.sortKey === c.key ? (MANAGE.sortDir === 1 ? " ▲" : " ▼") : "";
      return `<th style="cursor:pointer;user-select:none;white-space:nowrap" onclick="sortManageBy('${c.key}')" title="点击排序">${c.label}${arrow}</th>`;
    }).join("") +
    "</tr>";
}

function sortManageBy(key) {
  if (MANAGE.sortKey === key) {
    MANAGE.sortDir *= -1;
  } else {
    MANAGE.sortKey = key;
    MANAGE.sortDir = 1;
  }
  applyManageFilterSort();
}

function getSortValue(row, key) {
  if (key === "name" || key === "status") {
    return (row[key] || "").toString().toLowerCase();
  }
  if (key === "budget_cents") {
    // 没有自己预算的（使用上级预算）排到最后，不参与数值比较
    return row.has_own_budget ? Number(row.budget_cents || 0) : -1;
  }
  const v = row[key];
  return v === null || v === undefined || v === "" ? -Infinity : Number(v);
}

function resetManageFilterSort() {
  document.getElementById("manage-filter-text").value = "";
  document.getElementById("manage-filter-status").value = "ACTIVE";
  MANAGE.sortKey = null;
  MANAGE.sortDir = 1;
  applyManageFilterSort();
}

function applyManageFilterSort() {
  const text = (document.getElementById("manage-filter-text").value || "").trim().toLowerCase();
  const status = document.getElementById("manage-filter-status").value;

  let rows = MANAGE.rawRows.filter((r) => {
    const matchesText = !text || (r.name || "").toLowerCase().includes(text);
    const matchesStatus = status === "ALL" || r.status === status;
    return matchesText && matchesStatus;
  });

  if (MANAGE.sortKey) {
    const key = MANAGE.sortKey;
    const dir = MANAGE.sortDir;
    rows = rows.slice().sort((a, b) => {
      const va = getSortValue(a, key);
      const vb = getSortValue(b, key);
      if (typeof va === "string" || typeof vb === "string") {
        return dir * String(va).localeCompare(String(vb));
      }
      return dir * (va - vb);
    });
  }

  renderManageHeader();
  renderManageRows(rows);
}

function renderBreadcrumb() {
  const parts = [];
  parts.push(
    MANAGE.level === "campaigns" ? `<b>全部广告系列</b>` : `<a href="#" onclick="goToCampaigns(); return false;">全部广告系列</a>`
  );
  if (MANAGE.level === "adsets" || MANAGE.level === "ads") {
    parts.push(
      MANAGE.level === "adsets"
        ? `<b>${MANAGE.campaignName}</b>`
        : `<a href="#" onclick="goToAdsets(); return false;">${MANAGE.campaignName}</a>`
    );
  }
  if (MANAGE.level === "ads") {
    parts.push(`<b>${MANAGE.adsetName}</b>`);
  }
  document.getElementById("manage-breadcrumb").innerHTML = parts.join(" &nbsp;›&nbsp; ");
}

function clearManageFilterInputsOnly() {
  // 切换层级/账户时清空筛选条件和排序状态，但不触发额外的渲染（loadManageTable 会统一渲染）
  const textEl = document.getElementById("manage-filter-text");
  const statusEl = document.getElementById("manage-filter-status");
  if (textEl) textEl.value = "";
  if (statusEl) statusEl.value = "ACTIVE";
  MANAGE.sortKey = null;
  MANAGE.sortDir = 1;
  MANAGE.showCreateForm = false;
}

async function onAccountChangeForManage() {
  MANAGE.accountId = document.getElementById("manage-account-select").value;
  goToCampaigns();
}

function goToCampaigns() {
  MANAGE.level = "campaigns";
  MANAGE.campaignId = null;
  MANAGE.adsetId = null;
  clearManageFilterInputsOnly();
  loadManageTable();
}

function goToAdsets() {
  MANAGE.level = "adsets";
  MANAGE.adsetId = null;
  clearManageFilterInputsOnly();
  loadManageTable();
}

function drillIntoCampaign(id, name) {
  MANAGE.level = "adsets";
  MANAGE.campaignId = id;
  MANAGE.campaignName = name;
  clearManageFilterInputsOnly();
  loadManageTable();
}

function drillIntoAdset(id, name) {
  MANAGE.level = "ads";
  MANAGE.adsetId = id;
  MANAGE.adsetName = name;
  clearManageFilterInputsOnly();
  loadManageTable();
}

async function loadManageTable() {
  renderManageHeader();
  renderBreadcrumb();
  renderCreateArea();
  const tbody = document.getElementById("manage-tbody");
  const colCount = MANAGE_COLUMNS.length;

  if (!MANAGE.accountId) {
    tbody.innerHTML = `<tr><td colspan="${colCount}">请先选择 BM 和广告账户</td></tr>`;
    return;
  }
  tbody.innerHTML = `<tr><td colspan="${colCount}">加载中...</td></tr>`;
  const datePreset = document.getElementById("manage-date-preset").value;

  try {
    let rows = [];
    if (MANAGE.level === "campaigns") {
      const res = await api(`/api/accounts/${MANAGE.accountId}/campaigns/overview?date_preset=${datePreset}`);
      rows = res.data || [];
    } else if (MANAGE.level === "adsets") {
      const res = await api(
        `/api/accounts/${MANAGE.accountId}/adsets/overview?campaign_id=${MANAGE.campaignId}&date_preset=${datePreset}`
      );
      rows = res.data || [];
    } else {
      const res = await api(
        `/api/accounts/${MANAGE.accountId}/ads/overview?adset_id=${MANAGE.adsetId}&date_preset=${datePreset}`
      );
      rows = res.data || [];
    }
    MANAGE.rawRows = rows;
    applyManageFilterSort();
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="${colCount}" style="color:red">加载失败：${e.message}</td></tr>`;
  }
}

function renderManageRows(rows) {
  const tbody = document.getElementById("manage-tbody");
  const colCount = MANAGE_COLUMNS.length;
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="${colCount}">暂无数据</td></tr>`;
    return;
  }
  const kind = MANAGE.level; // "campaigns" | "adsets" | "ads"，与接口路径一致

  tbody.innerHTML = rows
    .map((r) => {
      const nameCell =
        kind === "ads"
          ? r.name
          : `<a href="#" onclick="${
              kind === "campaigns"
                ? `drillIntoCampaign('${r.id}', '${escapeHtml(r.name)}')`
                : `drillIntoAdset('${r.id}', '${escapeHtml(r.name)}')`
            }; return false;">${r.name}</a>`;

      let budgetCell = "-";
      if (kind !== "ads") {
        if (r.has_own_budget) {
          const dollars = (r.budget_cents / 100).toFixed(2);
          budgetCell = `
            <span style="display:inline-flex;align-items:center;gap:3px;white-space:nowrap">
              $<input type="number" step="0.01" min="0" value="${dollars}"
                 id="budget-input-${r.id}" data-budget-type="${r.budget_type || "daily"}"
                 style="width:72px;padding:2px 4px;border:1px solid #ccc;border-radius:4px" />
              <button onclick="saveBudgetInline('${kind}','${r.id}')" style="padding:3px 8px;font-size:12px">保存</button>
              ${r.budget_type === "lifetime" ? '<span style="font-size:11px;color:#888">(总)</span>' : ""}
            </span>`;
        } else {
          budgetCell = `<span style="color:#888">使用${kind === "campaigns" ? "广告组" : "广告系列"}预算</span>`;
        }
      }

      const toggleLabel = r.status === "ACTIVE" ? "暂停" : "启用";
      const actionsCell = `
        <button onclick="toggleManageStatus('${kind}','${r.id}','${r.status}')">${toggleLabel}</button>
        <button onclick="doDuplicate('${kind}','${r.id}')">复制</button>
      `;

      return `<tr>
        <td>${nameCell}</td>
        <td>${statusBadge(r.status)}</td>
        <td>${budgetCell}</td>
        <td>${fmtMoney(r.spend)}</td>
        <td>${fmtNum(r.purchases)}</td>
        <td>${fmtMoney(r.purchase_value)}</td>
        <td>${fmtRoas(r.roas)}</td>
        <td>${fmtMoney(r.cost_per_purchase)}</td>
        <td>${fmtNum(r.frequency, 2)}</td>
        <td>${fmtNum(r.impressions)}</td>
        <td>${fmtMoney(r.cpm)}</td>
        <td>${fmtNum(r.link_clicks)}</td>
        <td>${fmtMoney(r.cost_per_link_click)}</td>
        <td>${fmtPct(r.link_ctr)}</td>
        <td>${fmtNum(r.atc)}</td>
        <td>${fmtNum(r.checkout_initiated)}</td>
        <td>${fmtNum(r.video_views)}</td>
        <td>${fmtNum(r.video_p50)}</td>
        <td>${fmtNum(r.video_p100)}</td>
        <td>${actionsCell}</td>
      </tr>`;
    })
    .join("");
}

function reportManage(msg) {
  document.getElementById("manage-result").innerText = msg;
}

function statusBadge(status) {
  const active = status === "ACTIVE";
  return `<span style="color:${active ? "#1a7f37" : "#888"}">${status}</span>`;
}

async function patchObject(kind, accountId, id, body) {
  return api(`/api/accounts/${accountId}/${kind}/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function duplicateObject(kind, accountId, id) {
  return apiJSON(`/api/accounts/${accountId}/${kind}/${id}/duplicate`, {
    deep_copy: true,
    status_option: "PAUSED",
    rename_suffix: " - 副本",
  });
}

async function toggleManageStatus(kind, id, currentStatus) {
  const next = currentStatus === "ACTIVE" ? "PAUSED" : "ACTIVE";
  try {
    await patchObject(kind, MANAGE.accountId, id, { status: next });
    reportManage(`已切换为 ${next}`);
    loadManageTable();
  } catch (e) {
    reportManage("操作失败：" + e.message);
  }
}

async function saveBudgetInline(kind, id) {
  const input = document.getElementById(`budget-input-${id}`);
  if (!input) return;
  const dollars = parseFloat(input.value);
  if (isNaN(dollars) || dollars < 0) {
    reportManage("请输入有效的预算金额");
    return;
  }
  const cents = Math.round(dollars * 100);
  const body = input.dataset.budgetType === "lifetime"
    ? { lifetime_budget_cents: cents }
    : { daily_budget_cents: cents };
  try {
    await patchObject(kind, MANAGE.accountId, id, body);
    reportManage("预算更新成功");
    loadManageTable();
  } catch (e) {
    reportManage("更新失败：" + e.message);
  }
}

async function doDuplicate(kind, id) {
  if (!confirm("确定要复制这个对象吗？复制出来的默认是暂停状态。")) return;
  try {
    const result = await duplicateObject(kind, MANAGE.accountId, id);
    reportManage("复制成功，新对象 ID：" + JSON.stringify(result));
    loadManageTable();
  } catch (e) {
    reportManage("复制失败：" + e.message);
  }
}

// ---------------- 分层创建：先建广告系列 → 进去后建广告组 → 再进去建广告 ----------------
function renderCreateArea() {
  const area = document.getElementById("manage-create-area");
  if (!area) return;
  if (!MANAGE.accountId) {
    area.innerHTML = "";
    return;
  }

  if (MANAGE.level === "campaigns") {
    area.innerHTML = MANAGE.showCreateForm
      ? `
      <div class="card">
        <h4>新建广告系列 Campaign</h4>
        <input id="new-campaign-name" placeholder="系列名称" />
        <select id="new-campaign-objective">
          <option value="OUTCOME_TRAFFIC">流量 Traffic</option>
          <option value="OUTCOME_ENGAGEMENT">互动 Engagement</option>
          <option value="OUTCOME_LEADS">潜在客户 Leads</option>
          <option value="OUTCOME_SALES">销售 Sales</option>
          <option value="OUTCOME_AWARENESS">品牌知名度 Awareness</option>
        </select>
        <button onclick="submitCreateCampaign()">创建</button>
        <button onclick="toggleCreateForm(false)" style="background:#888">取消</button>
        <div id="create-result" class="result"></div>
      </div>`
      : `<button onclick="toggleCreateForm(true)">+ 新建广告系列</button>`;
  } else if (MANAGE.level === "adsets") {
    area.innerHTML = MANAGE.showCreateForm
      ? `
      <div class="card">
        <h4>在「${MANAGE.campaignName}」下新建广告组 AdSet</h4>
        <input id="new-adset-name" placeholder="广告组名称" />
        <input id="new-adset-budget" type="number" step="0.01" placeholder="每日预算（美元，如 10 = $10.00）" />
        <input id="new-adset-countries" placeholder="投放国家，逗号分隔，如 US,CA" value="US" />
        <input id="new-adset-age-min" type="number" placeholder="最小年龄" value="18" />
        <input id="new-adset-age-max" type="number" placeholder="最大年龄" value="65" />
        <select id="new-adset-optimization">
          <option value="LINK_CLICKS">链接点击</option>
          <option value="IMPRESSIONS">曝光</option>
          <option value="REACH">触达</option>
          <option value="OFFSITE_CONVERSIONS">转化</option>
        </select>
        <button onclick="submitCreateAdSet()">创建</button>
        <button onclick="toggleCreateForm(false)" style="background:#888">取消</button>
        <div id="create-result" class="result"></div>
      </div>`
      : `<button onclick="toggleCreateForm(true)">+ 新建广告组</button>`;
  } else if (MANAGE.level === "ads") {
    area.innerHTML = MANAGE.showCreateForm
      ? `
      <div class="card">
        <h4>在「${MANAGE.adsetName}」下新建广告 Ad</h4>
        <input id="new-ad-name" placeholder="广告名称" />
        <input id="new-ad-page-id" placeholder="Facebook 主页 Page ID" />
        <input id="new-ad-message" placeholder="正文文案" />
        <input id="new-ad-link" placeholder="落地页链接 https://..." />
        <input id="new-ad-headline" placeholder="标题（可选）" />
        <input id="new-ad-image" type="file" accept="image/*" />
        <button onclick="submitCreateAd()">创建广告</button>
        <button onclick="toggleCreateForm(false)" style="background:#888">取消</button>
        <div id="create-result" class="result"></div>
      </div>`
      : `<button onclick="toggleCreateForm(true)">+ 新建广告</button>`;
  }
}

function toggleCreateForm(show) {
  MANAGE.showCreateForm = show;
  renderCreateArea();
}

async function submitCreateCampaign() {
  const name = document.getElementById("new-campaign-name").value;
  const objective = document.getElementById("new-campaign-objective").value;
  const box = document.getElementById("create-result");
  if (!name) return (box.innerText = "请输入系列名称");
  box.innerText = "创建中...";
  try {
    await apiJSON(`/api/accounts/${MANAGE.accountId}/campaigns`, { name, objective });
    MANAGE.showCreateForm = false;
    loadManageTable();
  } catch (e) {
    box.innerText = "创建失败：" + e.message;
  }
}

async function submitCreateAdSet() {
  const name = document.getElementById("new-adset-name").value;
  const dollars = parseFloat(document.getElementById("new-adset-budget").value);
  const countries = document.getElementById("new-adset-countries").value.split(",").map((s) => s.trim()).filter(Boolean);
  const age_min = parseInt(document.getElementById("new-adset-age-min").value, 10);
  const age_max = parseInt(document.getElementById("new-adset-age-max").value, 10);
  const optimization_goal = document.getElementById("new-adset-optimization").value;
  const box = document.getElementById("create-result");
  if (!name || isNaN(dollars) || dollars <= 0) return (box.innerText = "请填写广告组名称和有效的每日预算");
  box.innerText = "创建中...";
  try {
    await apiJSON(`/api/accounts/${MANAGE.accountId}/adsets`, {
      name,
      campaign_id: MANAGE.campaignId,
      daily_budget_cents: Math.round(dollars * 100),
      countries,
      age_min,
      age_max,
      optimization_goal,
    });
    MANAGE.showCreateForm = false;
    loadManageTable();
  } catch (e) {
    box.innerText = "创建失败：" + e.message;
  }
}

async function submitCreateAd() {
  const box = document.getElementById("create-result");
  const name = document.getElementById("new-ad-name").value;
  const page_id = document.getElementById("new-ad-page-id").value;
  const message = document.getElementById("new-ad-message").value;
  const link = document.getElementById("new-ad-link").value;
  const headline = document.getElementById("new-ad-headline").value;
  const fileInput = document.getElementById("new-ad-image");

  if (!name || !page_id || !message || !link) {
    box.innerText = "请完整填写广告名称、主页ID、正文文案、落地页链接";
    return;
  }

  box.innerText = "创建中...（上传素材 → 创建创意 → 创建广告）";
  try {
    let image_hash = null;
    if (fileInput.files.length) {
      const fd = new FormData();
      fd.append("file", fileInput.files[0]);
      const uploadRes = await fetch(`/api/accounts/${MANAGE.accountId}/images`, {
        method: "POST",
        headers: { "Authorization": "Bearer " + TOKEN },
        body: fd,
      });
      const uploadData = await uploadRes.json();
      if (!uploadRes.ok) throw new Error(JSON.stringify(uploadData.detail));
      const firstKey = Object.keys(uploadData.images || {})[0];
      image_hash = firstKey ? uploadData.images[firstKey].hash : null;
    }

    const creative = await apiJSON(`/api/accounts/${MANAGE.accountId}/creatives`, {
      name: name + " - 素材",
      page_id,
      message,
      link,
      headline,
      image_hash,
    });

    await apiJSON(`/api/accounts/${MANAGE.accountId}/ads`, {
      name,
      adset_id: MANAGE.adsetId,
      creative_id: creative.id,
    });

    MANAGE.showCreateForm = false;
    loadManageTable();
  } catch (e) {
    box.innerText = "创建失败：" + e.message;
  }
}
