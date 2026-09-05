let TOKEN = localStorage.getItem("panel_token") || "";
let ACCOUNTS = [];
let chartInstance = null;

// ---------------- 登录 ----------------
async function doLogin() {
  const pw = document.getElementById("pw").value;
  const res = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: pw }),
  });
  if (!res.ok) {
    document.getElementById("login-err").innerText = "口令错误";
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
    });
  });
};

// ---------------- 通用请求 ----------------
async function api(path, options = {}) {
  options.headers = Object.assign({}, options.headers, { "X-Panel-Token": TOKEN });
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
  tbody.innerHTML = "<tr><td colspan='8'>加载中...</td></tr>";
  try {
    const res = await api("/api/accounts");
    ACCOUNTS = res.data || [];
    tbody.innerHTML = "";
    ACCOUNTS.forEach((a) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${a.name || "-"}</td>
        <td>${a.id}</td>
        <td>${a.account_status}</td>
        <td>${a.currency}</td>
        <td>${money(a.amount_spent, a.currency)}</td>
        <td>${money(a.balance, a.currency)}</td>
        <td>${a.spend_cap ? money(a.spend_cap, a.currency) : "无上限"}</td>
        <td><input value="${a.note || ""}" onchange="saveNote('${a.id}', this.value)" placeholder="备注" style="width:120px"/></td>
      `;
      tbody.appendChild(tr);
    });
    fillAccountSelects();
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan='8' style="color:red">加载失败：${e.message}</td></tr>`;
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
  const opts = ACCOUNTS.map((a) => `<option value="${a.id}">${a.name} (${a.id})</option>`).join("");
  ["create-account-select", "insight-account-select", "budget-account-select"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = opts;
  });
  if (ACCOUNTS.length) {
    onAccountChangeForCreate();
    loadBudgetInfo();
  }
}

// ---------------- 创建广告流程 ----------------
async function onAccountChangeForCreate() {
  const accountId = document.getElementById("create-account-select").value;
  if (!accountId) return;
  try {
    const campaigns = await api(`/api/accounts/${accountId}/campaigns`);
    const opts = (campaigns.data || [])
      .map((c) => `<option value="${c.id}">${c.name} (${c.status})</option>`)
      .join("");
    document.getElementById("as-campaign-select").innerHTML = opts;

    const adsets = await api(`/api/accounts/${accountId}/adsets`);
    const asOpts = (adsets.data || [])
      .map((s) => `<option value="${s.id}">${s.name}</option>`)
      .join("");
    document.getElementById("ad-adset-select").innerHTML = asOpts;
  } catch (e) {
    console.error(e);
  }
}

async function createCampaign() {
  const accountId = document.getElementById("create-account-select").value;
  const name = document.getElementById("c-name").value;
  const objective = document.getElementById("c-objective").value;
  const box = document.getElementById("campaign-result");
  if (!name) return (box.innerText = "请输入系列名称");
  try {
    const result = await apiJSON(`/api/accounts/${accountId}/campaigns`, { name, objective });
    box.innerText = "创建成功，Campaign ID: " + result.id;
    onAccountChangeForCreate();
  } catch (e) {
    box.innerText = "创建失败：" + e.message;
  }
}

async function createAdSet() {
  const accountId = document.getElementById("create-account-select").value;
  const campaign_id = document.getElementById("as-campaign-select").value;
  const name = document.getElementById("as-name").value;
  const daily_budget_cents = parseInt(document.getElementById("as-budget").value, 10);
  const countries = document.getElementById("as-countries").value.split(",").map((s) => s.trim()).filter(Boolean);
  const age_min = parseInt(document.getElementById("as-age-min").value, 10);
  const age_max = parseInt(document.getElementById("as-age-max").value, 10);
  const optimization_goal = document.getElementById("as-optimization").value;
  const box = document.getElementById("adset-result");
  if (!campaign_id || !name || !daily_budget_cents) return (box.innerText = "请完整填写");
  try {
    const result = await apiJSON(`/api/accounts/${accountId}/adsets`, {
      name, campaign_id, daily_budget_cents, countries, age_min, age_max, optimization_goal,
    });
    box.innerText = "创建成功，AdSet ID: " + result.id;
    onAccountChangeForCreate();
  } catch (e) {
    box.innerText = "创建失败：" + e.message;
  }
}

async function uploadImageThenCreative() {
  const accountId = document.getElementById("create-account-select").value;
  const fileInput = document.getElementById("cr-image-file");
  const box = document.getElementById("creative-result");
  let image_hash = null;

  try {
    if (fileInput.files.length) {
      const fd = new FormData();
      fd.append("file", fileInput.files[0]);
      const uploadRes = await fetch(`/api/accounts/${accountId}/images`, {
        method: "POST",
        headers: { "X-Panel-Token": TOKEN },
        body: fd,
      });
      const uploadData = await uploadRes.json();
      if (!uploadRes.ok) throw new Error(JSON.stringify(uploadData.detail));
      const firstKey = Object.keys(uploadData.images || {})[0];
      image_hash = firstKey ? uploadData.images[firstKey].hash : null;
    }

    const body = {
      name: document.getElementById("cr-name").value,
      page_id: document.getElementById("cr-page-id").value,
      message: document.getElementById("cr-message").value,
      link: document.getElementById("cr-link").value,
      headline: document.getElementById("cr-headline").value,
      image_hash,
    };
    const result = await apiJSON(`/api/accounts/${accountId}/creatives`, body);
    box.innerText = "创建成功，Creative ID: " + result.id;
    document.getElementById("ad-creative-id").value = result.id;
  } catch (e) {
    box.innerText = "创建失败：" + e.message;
  }
}

async function createAd() {
  const accountId = document.getElementById("create-account-select").value;
  const adset_id = document.getElementById("ad-adset-select").value;
  const name = document.getElementById("ad-name").value;
  const creative_id = document.getElementById("ad-creative-id").value;
  const box = document.getElementById("ad-result");
  if (!adset_id || !name || !creative_id) return (box.innerText = "请完整填写");
  try {
    const result = await apiJSON(`/api/accounts/${accountId}/ads`, { name, adset_id, creative_id });
    box.innerText = "创建成功，Ad ID: " + result.id;
  } catch (e) {
    box.innerText = "创建失败：" + e.message;
  }
}

// ---------------- 数据分析 ----------------
async function loadInsights() {
  const accountId = document.getElementById("insight-account-select").value;
  const preset = document.getElementById("insight-preset").value;
  const byCampaign = document.getElementById("insight-by-campaign").checked;
  if (!accountId) return;

  try {
    const res = await api(
      `/api/accounts/${accountId}/insights?date_preset=${preset}&by_campaign=${byCampaign}`
    );
    const rows = res.data || [];
    renderInsightStats(rows);
    renderInsightChart(rows, byCampaign);
    renderInsightTable(rows, byCampaign);
  } catch (e) {
    document.getElementById("insight-stats").innerHTML = `<div style="color:red">加载失败：${e.message}</div>`;
  }
}

function sum(rows, field) {
  return rows.reduce((acc, r) => acc + Number(r[field] || 0), 0);
}

function renderInsightStats(rows) {
  const spend = sum(rows, "spend").toFixed(2);
  const impressions = sum(rows, "impressions");
  const clicks = sum(rows, "clicks");
  const ctr = impressions ? ((clicks / impressions) * 100).toFixed(2) : "0.00";
  const el = document.getElementById("insight-stats");
  el.innerHTML = `
    <div class="stat-card"><div class="num">$${spend}</div><div class="label">花费</div></div>
    <div class="stat-card"><div class="num">${impressions}</div><div class="label">曝光</div></div>
    <div class="stat-card"><div class="num">${clicks}</div><div class="label">点击</div></div>
    <div class="stat-card"><div class="num">${ctr}%</div><div class="label">CTR</div></div>
  `;
}

function renderInsightChart(rows, byCampaign) {
  const ctx = document.getElementById("insight-chart");
  const labels = byCampaign ? rows.map((r) => r.campaign_name || r.date_start) : rows.map((r) => r.date_start);
  const spendData = rows.map((r) => Number(r.spend || 0));
  if (chartInstance) chartInstance.destroy();
  chartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{ label: "花费 ($)", data: spendData, backgroundColor: "#1877f2" }],
    },
    options: { responsive: true, plugins: { legend: { display: false } } },
  });
}

function renderInsightTable(rows, byCampaign) {
  const wrap = document.getElementById("insight-table-wrap");
  if (!rows.length) {
    wrap.innerHTML = "<tr><td>暂无数据</td></tr>";
    return;
  }
  const head = byCampaign
    ? "<tr><th>广告系列</th><th>花费</th><th>曝光</th><th>点击</th><th>CTR</th><th>CPC</th></tr>"
    : "<tr><th>日期</th><th>花费</th><th>曝光</th><th>点击</th><th>CTR</th><th>CPC</th></tr>";
  const body = rows
    .map(
      (r) => `<tr>
        <td>${byCampaign ? r.campaign_name : r.date_start}</td>
        <td>${Number(r.spend || 0).toFixed(2)}</td>
        <td>${r.impressions || 0}</td>
        <td>${r.clicks || 0}</td>
        <td>${Number(r.ctr || 0).toFixed(2)}%</td>
        <td>${Number(r.cpc || 0).toFixed(2)}</td>
      </tr>`
    )
    .join("");
  wrap.innerHTML = "<thead>" + head + "</thead><tbody>" + body + "</tbody>";
}

// ---------------- 额度管理 ----------------
async function loadBudgetInfo() {
  const accountId = document.getElementById("budget-account-select").value;
  if (!accountId) return;
  const box = document.getElementById("budget-info");
  box.innerHTML = "加载中...";
  try {
    const a = await api(`/api/accounts/${accountId}`);
    box.innerHTML = `
      <p><b>账户：</b>${a.name}</p>
      <p><b>已花费：</b>${money(a.amount_spent, a.currency)}</p>
      <p><b>账户余额：</b>${money(a.balance, a.currency)}</p>
      <p><b>当前花费上限：</b>${a.spend_cap ? money(a.spend_cap, a.currency) : "未设置"}</p>
    `;
  } catch (e) {
    box.innerHTML = `<span style="color:red">加载失败：${e.message}</span>`;
  }
}

async function setSpendCap() {
  const accountId = document.getElementById("budget-account-select").value;
  const cap = parseInt(document.getElementById("budget-new-cap").value, 10);
  const box = document.getElementById("budget-result");
  if (!cap) return (box.innerText = "请输入有效数字");
  try {
    await apiJSON(`/api/accounts/${accountId}/spend_cap`, { spend_cap_cents: cap });
    box.innerText = "更新成功";
    loadBudgetInfo();
  } catch (e) {
    box.innerText = "更新失败：" + e.message;
  }
}
