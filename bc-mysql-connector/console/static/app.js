/* Pretech Connect console */
(() => {
  "use strict";

  const $ = (s) => document.querySelector(s);
  const ENTITY_LABEL = { customers: "Customers", vendors: "Vendors", items: "Items", salesOrders: "Sales orders" };
  const STATUS_LABEL = {
    "synced": "In sync", "changed-in-bc": "Changed in BC", "pending": "Waiting to push",
    "new-in-bc": "New in BC", "only-mysql": "Not in BC", "done": "Done", "failed": "Failed",
  };
  const SHOW = {
    customers: ["number", "display_name", "city", "state", "credit_limit", "balance_due"],
    vendors: ["number", "display_name", "city", "balance"],
    items: ["number", "display_name", "item_category_code", "unit_price", "unit_cost", "inventory"],
    salesOrders: ["number", "external_document_number", "customer_name", "order_date", "requested_delivery_date", "status", "total_incl_tax"],
  };
  const HEAD = {
    number: "No.", display_name: "Name", city: "City", state: "State", credit_limit: "Credit limit",
    balance_due: "Balance due", balance: "Balance", item_category_code: "Category", unit_price: "Unit price",
    unit_cost: "Unit cost", inventory: "Inventory", external_document_number: "Customer PO",
    customer_name: "Customer", order_date: "Order date", requested_delivery_date: "Delivery", status: "Status",
    total_incl_tax: "Total incl. GST",
  };
  const MONEY = new Set(["credit_limit", "balance_due", "balance", "unit_price", "unit_cost", "total_incl_tax"]);
  const FIELDS = {
    bc: {
      items: [["unitPrice", "Unit price", "num"], ["unitCost", "Unit cost", "num"], ["displayName", "Name", "text"], ["inventory", "Inventory", "num"]],
      customers: [["city", "City", "text"], ["creditLimit", "Credit limit", "num"], ["displayName", "Name", "text"], ["phoneNumber", "Phone", "text"]],
    },
    mysql: {
      items: [["unitPrice", "Unit price", "num"], ["unitCost", "Unit cost", "num"], ["displayName", "Name", "text"]],
      customers: [["creditLimit", "Credit limit", "num"], ["city", "City", "text"], ["phoneNumber", "Phone", "text"], ["email", "Email", "text"]],
    },
  };
  const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });

  let overview = null;
  let active = "items";
  let lastRecords = null;
  let previousEtags = {};
  let meta = { customers: [], items: [] };
  let busy = false;

  /* ---------- helpers ---------- */
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (col, v) => {
    if (v === null || v === undefined || v === "") return '<span class="muted">–</span>';
    if (MONEY.has(col)) return inr.format(v);
    if (col === "inventory") return Number(v).toLocaleString("en-IN");
    if (/_date$/.test(col)) return new Date(v + "T00:00:00").toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
    return esc(v);
  };
  const when = (iso) => {
    if (!iso) return "never";
    const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
    const s = Math.round((Date.now() - d.getTime()) / 1000);
    if (s < 5) return "just now";
    if (s < 60) return `${s} s ago`;
    if (s < 3600) return `${Math.round(s / 60)} min ago`;
    return d.toLocaleString("en-IN");
  };
  const chip = (status) => `<span class="chip ${status}">${STATUS_LABEL[status] || esc(status)}</span>`;

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      method: opts.method || "GET",
      headers: opts.body ? { "Content-Type": "application/json" } : undefined,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    return data;
  }

  let toastTimer = 0;
  function toast(msg, isErr = false) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.toggle("err", isErr);
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), 4200);
  }

  async function withBusy(btn, fn) {
    if (btn) btn.disabled = true;
    try { await fn(); } catch (e) { toast(e.message, true); } finally { if (btn) btn.disabled = false; }
  }

  /* ---------- overview ---------- */
  async function loadOverview() {
    overview = await api("/api/overview");
    const mock = overview.mode === "mock";
    document.querySelectorAll(".mock-only").forEach((el) => (el.hidden = !mock));
    document.querySelectorAll(".live-only").forEach((el) => (el.hidden = mock));
    if (!mock) { $("#n3").textContent = "2"; $("#n4").textContent = "3"; $("#liveEnv").textContent = overview.environment; }

    const company = (overview.company && (overview.company.displayName || overview.company.name)) || "unknown";
    $("#bcName").textContent = `${mock ? "mock tenant" : overview.environment} · ${company}`;
    $("#bcDot").className = "dot " + (company.startsWith("not reachable") ? "bad" : "ok");
    const db = overview.db;
    $("#dbKind").textContent = db.dialect === "mysql" ? "MySQL" : "SQLite (fallback)";
    $("#dbName").textContent = db.ok
      ? `${(db.version || "").split("-")[0]} · ${db.database}${db.dialect === "mysql" ? " @ " + db.host + ":" + db.port : ""}`
      : "not reachable";
    $("#dbDot").className = "dot " + (db.ok ? "ok" : "bad");
    $("#autoSync").checked = overview.auto_sync;
    $("#autoEvery").textContent = `${overview.auto_interval} s`;

    $("#cards").innerHTML = overview.entities.map((e) => {
      let status;
      if (e.last_error) status = '<span class="chip error">Error</span>';
      else if (e.pending) status = `<span class="chip pending">${e.pending} waiting</span>`;
      else if (e.bc_rows !== null && e.bc_rows !== e.mysql_rows) status = `<span class="chip changed-in-bc">${Math.abs(e.bc_rows - e.mysql_rows)} not pulled</span>`;
      else if (!e.last_run) status = `<span class="chip pending">not pulled yet</span>`;
      else status = chip("synced");
      return `<div class="card">
        <div class="card-top"><h3>${esc(e.label)}</h3>${status}</div>
        <div class="card-counts">
          <div><span>Business Central</span><b>${e.bc_rows ?? "–"}</b></div>
          <div class="arrow">⇄</div>
          <div><span>MySQL</span><b>${e.mysql_rows}</b></div>
        </div>
        <div class="card-foot">${e.last_error ? '<span style="color:var(--err)">' + esc(e.last_error) + "</span>" : "Last pull " + when(e.last_run)}</div>
      </div>`;
    }).join("");

    if (!$("#entityTabs").children.length) {
      $("#entityTabs").innerHTML = overview.entities.map((e) =>
        `<button role="tab" data-entity="${e.entity}" aria-selected="${e.entity === active}">${esc(e.label)}<span id="cnt-${e.entity}"></span></button>`).join("");
      $("#entityTabs").addEventListener("click", (ev) => {
        const b = ev.target.closest("button[data-entity]");
        if (!b) return;
        active = b.dataset.entity;
        document.querySelectorAll("#entityTabs button").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
        previousEtags = {};
        loadRecords();
      });
    }
    overview.entities.forEach((e) => { const c = document.getElementById(`cnt-${e.entity}`); if (c) c.textContent = e.mysql_rows; });
    const ob = overview.outbox || {};
    $("#obCount").textContent = (ob.pending || 0) ? `${ob.pending} pending` : "";
  }

  /* ---------- records table ---------- */
  async function loadRecords() {
    const data = await api(`/api/records/${active}`);
    lastRecords = data;
    const cols = SHOW[active];
    const rows = data.rows;
    if (!rows.length && !data.new_in_bc.length) {
      $("#tableWrap").innerHTML = `<div class="empty">No ${ENTITY_LABEL[active].toLowerCase()} in MySQL yet. Run step 1 to pull them from Business Central.</div>`;
      return;
    }
    const head = `<tr><th>Sync</th>${cols.map((c) => `<th class="${MONEY.has(c) || c === "inventory" ? "num" : ""}">${HEAD[c] || c}</th>`).join("")}</tr>`;
    const body = rows.map((r) => {
      const changed = previousEtags[r.id] && previousEtags[r.id] !== r.etag;
      return `<tr data-id="${esc(r.id)}" class="${changed ? "flash" : ""}"><td>${chip(r.sync_status)}</td>${cols.map((c) =>
        `<td class="${c === "number" ? "key" : ""} ${MONEY.has(c) || c === "inventory" ? "num" : ""}">${fmt(c, r[c])}</td>`).join("")}</tr>`;
    }).join("") + data.new_in_bc.map((n) =>
      `<tr data-id="${esc(n.id)}"><td>${chip("new-in-bc")}</td><td class="key">${esc(n.number)}</td><td colspan="${cols.length - 1}">${esc(n.name || "")} <span class="muted">· exists in BC, arrives on the next sync</span></td></tr>`).join("");
    $("#tableWrap").innerHTML = `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
    previousEtags = Object.fromEntries(rows.map((r) => [r.id, r.etag]));
  }

  $("#tableWrap").addEventListener("click", (ev) => {
    const tr = ev.target.closest("tr[data-id]");
    if (tr && lastRecords) openDrawer(tr.dataset.id);
  });

  function openDrawer(id) {
    const r = lastRecords.rows.find((x) => x.id === id);
    const bc = lastRecords.bc ? lastRecords.bc[id] : null;
    const title = r ? `${r.number} · ${r.display_name || r.customer_name || ""}` : (bc ? bc.number : id);
    $("#drawerTitle").textContent = title;
    let html = "";
    if (r && bc) {
      html += `<div><h3 style="font:500 14px/1.3 var(--sans);margin-bottom:8px">Business Central and MySQL, field by field</h3>
        <table class="cmp"><thead><tr><th>BC field</th><th>Business Central</th><th>MySQL column</th><th>MySQL</th></tr></thead><tbody>` +
        lastRecords.fields.map((f) => {
          const a = bc[f.bc], b = r[f.col];
          const same = (a ?? "") == (b ?? "") || (f.kind === "decimal" && Number(a) === Number(b)) || (f.kind === "date" && String(a || "").slice(0, 10) === String(b || ""));
          return `<tr class="${same ? "" : "diff"}"><td class="mono">${esc(f.bc)}</td><td>${esc(a ?? "")}</td><td class="mono">${esc(f.col)}</td><td>${esc(b ?? "")}</td></tr>`;
        }).join("") + `</tbody></table></div>`;
    }
    if (r) html += `<div><h3 style="font:500 14px/1.3 var(--sans);margin-bottom:8px">MySQL row</h3><pre>${esc(JSON.stringify(Object.fromEntries(Object.entries(r).filter(([k]) => k !== "sync_status")), null, 2))}</pre></div>`;
    if (bc) html += `<div><h3 style="font:500 14px/1.3 var(--sans);margin-bottom:8px">Business Central record (API v2.0)</h3><pre>${esc(JSON.stringify(bc, null, 2))}</pre></div>`;
    $("#drawerBody").innerHTML = html || '<div class="empty">No details</div>';
    $("#drawer").classList.add("open");
    $("#drawer").setAttribute("aria-hidden", "false");
  }
  $("#drawer").addEventListener("click", (ev) => { if (ev.target.closest("[data-close]")) closeDrawer(); });
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") closeDrawer(); });
  function closeDrawer() { $("#drawer").classList.remove("open"); $("#drawer").setAttribute("aria-hidden", "true"); }

  /* ---------- outbox and activity ---------- */
  async function loadOutbox() {
    const rows = await api("/api/outbox");
    if (!rows.length) { $("#outboxWrap").innerHTML = '<div class="empty">bc_outbox is empty. Steps 3 and 4 add rows here.</div>'; return; }
    $("#outboxWrap").innerHTML = `<table><thead><tr><th>#</th><th>Status</th><th>Entity</th><th>Operation</th><th>Target</th><th>Payload</th><th class="num">Attempts</th><th>Last error</th><th></th></tr></thead><tbody>` +
      rows.map((o) => `<tr style="cursor:default"><td class="key">${o.id}</td><td>${chip(o.status)}</td><td>${esc(ENTITY_LABEL[o.entity] || o.entity)}</td><td>${esc(o.operation)}</td>
        <td class="key">${esc(o.bc_number || (o.bc_id ? o.bc_id.slice(0, 8) + "…" : "new"))}</td><td class="mono" style="font-size:12px">${esc(JSON.stringify(o.payload))}</td>
        <td class="num">${o.attempts}</td><td style="color:var(--err);font-size:12px">${esc(o.last_error || "")}</td>
        <td>${o.status === "failed" ? `<button class="btn btn-ghost btn-sm" data-retry="${o.id}">Retry</button>` : ""}</td></tr>`).join("") + "</tbody></table>";
  }
  $("#outboxWrap").addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-retry]");
    if (b) withBusy(b, async () => { await api(`/api/outbox/${b.dataset.retry}/retry`, { method: "POST" }); await refresh(); });
  });

  async function loadEvents() {
    const ev = await api("/api/events");
    $("#logCount").textContent = ev.length || "";
    $("#log").innerHTML = ev.length
      ? ev.map((e) => `<li><time>${esc(e.at)}</time><span class="k ${esc(e.kind)}">${esc(e.kind)}</span><span>${esc(e.message)}</span></li>`).join("")
      : '<li style="grid-template-columns:1fr"><span class="muted">Nothing yet. Start with step 1.</span></li>';
  }

  $("#lowerTabs").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-pane]");
    if (!b) return;
    document.querySelectorAll("#lowerTabs button").forEach((x) => {
      const on = x === b;
      x.setAttribute("aria-selected", String(on));
      document.getElementById(x.dataset.pane).hidden = !on;
    });
  });

  /* ---------- action forms ---------- */
  async function loadMeta() {
    meta = await api("/api/meta");
    fillRecords("#bcRecord", $("#bcEntity").value);
    fillRecords("#mxRecord", $("#mxEntity").value);
    fillRecords("#cfRecord", "customers");
  }
  function fillRecords(sel, entity) {
    const el = $(sel), keep = el.value;
    const list = meta[entity] || [];
    el.innerHTML = list.length
      ? list.map((r) => `<option value="${esc(r.number)}">${esc(r.number)} · ${esc(r.display_name)}</option>`).join("")
      : '<option value="">Pull first (step 1)</option>';
    if (list.some((r) => r.number === keep)) el.value = keep;
  }
  function fillFields(sel, side, entity) {
    $(sel).innerHTML = FIELDS[side][entity].map(([k, label]) => `<option value="${k}">${label}</option>`).join("");
  }
  function value(side, entity, field, raw) {
    const def = FIELDS[side][entity].find((f) => f[0] === field);
    if (!def) throw new Error("Pick a field");
    if (raw === "") throw new Error("Enter a value");
    if (def[2] === "num") {
      const n = Number(String(raw).replace(/[,₹\s]/g, ""));
      if (!Number.isFinite(n)) throw new Error("Enter a number");
      return n;
    }
    return raw;
  }

  $("#bcEntity").addEventListener("change", () => { fillRecords("#bcRecord", $("#bcEntity").value); fillFields("#bcField", "bc", $("#bcEntity").value); });
  $("#mxEntity").addEventListener("change", () => { fillRecords("#mxRecord", $("#mxEntity").value); fillFields("#mxField", "mysql", $("#mxEntity").value); });

  $("#bcSave").addEventListener("click", (ev) => withBusy(ev.currentTarget, async () => {
    const entity = $("#bcEntity").value, number = $("#bcRecord").value, field = $("#bcField").value;
    if (!number) throw new Error("Pull first (step 1)");
    const v = value("bc", entity, field, $("#bcValue").value.trim());
    await api("/api/demo/bc-edit", { method: "POST", body: { entity, number, fields: { [field]: v } } });
    toast(`Saved in Business Central. Press Sync now (or turn on Auto sync) to bring ${number} into MySQL.`);
    $("#bcValue").value = "";
    await refresh();
  }));

  $("#mxQueue").addEventListener("click", (ev) => withBusy(ev.currentTarget, async () => {
    const entity = $("#mxEntity").value, number = $("#mxRecord").value, field = $("#mxField").value;
    if (!number) throw new Error("Pull first (step 1)");
    const v = value("mysql", entity, field, $("#mxValue").value.trim());
    await api("/api/outbox", { method: "POST", body: { entity, operation: "update", bc_number: number, payload: { [field]: v } } });
    toast(`Queued in bc_outbox. Press Sync now to push ${number} to Business Central.`);
    $("#mxValue").value = "";
    await refresh();
  }));

  $("#ncQueue").addEventListener("click", (ev) => withBusy(ev.currentTarget, async () => {
    const name = $("#ncName").value.trim();
    if (!name) throw new Error("Enter a company name");
    const payload = { displayName: name, type: "Company", country: "IN", currencyCode: "INR" };
    if ($("#ncCity").value.trim()) payload.city = $("#ncCity").value.trim();
    if ($("#ncState").value.trim()) payload.state = $("#ncState").value.trim().toUpperCase();
    if ($("#ncCredit").value) payload.creditLimit = Number($("#ncCredit").value);
    await api("/api/outbox", { method: "POST", body: { entity: "customers", operation: "create", payload } });
    toast("New customer queued. Press Sync now: Business Central will assign its number.");
    ["#ncName", "#ncCity", "#ncState", "#ncCredit"].forEach((s) => ($(s).value = ""));
    await refresh();
  }));

  $("#cfRun").addEventListener("click", (ev) => withBusy(ev.currentTarget, async () => {
    const number = $("#cfRecord").value;
    if (!number) throw new Error("Pull first (step 1)");
    const rec = (meta.customers || []).find((c) => c.number === number);
    await api("/api/outbox", { method: "POST", body: { entity: "customers", operation: "update", bc_number: number, payload: { creditLimit: 9900000 } } });
    await api("/api/demo/bc-edit", { method: "POST", body: { entity: "customers", number, fields: { city: "Pune (edited in BC)" } } });
    toast(`Conflict set up on ${number}${rec ? " (" + rec.display_name + ")" : ""}: BC changed the city, MySQL the credit limit. Press Sync now.`);
    await refresh();
  }));

  $("#throttle").addEventListener("change", (ev) => withBusy(null, async () => {
    await api("/api/demo/throttle", { method: "POST", body: { on: ev.target.checked } });
    toast(ev.target.checked ? "Throttling on: some calls will get HTTP 429 and be retried." : "Throttling off.");
    await loadEvents();
  }));

  $("#reset").addEventListener("click", (ev) => withBusy(ev.currentTarget, async () => {
    if (!confirm("Reset the demo? This restores the sample Business Central company and empties the MySQL tables.")) return;
    await api("/api/demo/reset", { method: "POST" });
    $("#throttle").checked = false;
    previousEtags = {};
    toast("Demo reset. Start again with step 1.");
    await refresh(true);
  }));

  $("#fullPull").addEventListener("click", (ev) => withBusy(ev.currentTarget, async () => {
    const r = await api("/api/sync", { method: "POST", body: { full: true } });
    const total = Object.values(r.pulled).reduce((a, b) => a + b, 0);
    toast(r.errors.length ? `Pulled with errors: ${r.errors[0]}` : `Pulled ${total} records from Business Central in ${r.ms} ms.`, !!r.errors.length);
    await refresh(true);
  }));

  $("#syncBtn").addEventListener("click", (ev) => withBusy(ev.currentTarget, async () => {
    const r = await api("/api/sync", { method: "POST", body: { full: false } });
    const pulled = Object.values(r.pulled).reduce((a, b) => a + b, 0);
    toast(r.errors.length && !r.pushed && !pulled ? r.errors[0]
      : `Sync done: ${pulled} pulled, ${r.pushed} pushed${r.failed ? ", " + r.failed + " failed" : ""}${r.retry_later ? ", " + r.retry_later + " waiting" : ""} · ${r.ms} ms`, !!r.failed);
    await refresh(true);
  }));

  $("#autoSync").addEventListener("change", (ev) => withBusy(null, async () => {
    await api("/api/auto-sync", { method: "POST", body: { on: ev.target.checked, interval: 10 } });
    toast(ev.target.checked ? "Auto sync on: pull and push every 10 seconds." : "Auto sync off.");
  }));

  /* ---------- SQL ---------- */
  const EXAMPLES = [
    ["Flameproof panels", "SELECT number, display_name, unit_price, inventory\nFROM bc_items\nWHERE item_category_code = 'FLAMEPROOF'\nORDER BY unit_price DESC"],
    ["Open orders with city", "SELECT so.number, so.external_document_number AS customer_po, so.customer_name, c.city,\n       so.requested_delivery_date, so.total_incl_tax\nFROM bc_sales_orders so\nJOIN bc_customers c ON c.id = so.customer_id\nWHERE so.status = 'Open'\nORDER BY so.requested_delivery_date"],
    ["Exposure by customer", "SELECT number, display_name, credit_limit, balance_due,\n       ROUND(100 * balance_due / NULLIF(credit_limit, 0), 1) AS pct_used\nFROM bc_customers\nORDER BY pct_used DESC"],
    ["Outbox", "SELECT id, entity, operation, bc_number, status, attempts, last_error, created_at\nFROM bc_outbox\nORDER BY id DESC"],
    ["Audit log", "SELECT at, kind, message\nFROM bc_sync_log\nORDER BY id DESC\nLIMIT 50"],
    ["Raw JSON field", "SELECT number, JSON_UNQUOTE(JSON_EXTRACT(raw, '$.\"@odata.etag\"')) AS bc_etag, bc_last_modified\nFROM bc_items\nORDER BY bc_last_modified DESC\nLIMIT 10"],
  ];
  $("#sqlExamples").innerHTML = EXAMPLES.map(([label], i) => `<button class="btn btn-ghost btn-sm" data-ex="${i}">${esc(label)}</button>`).join("");
  $("#sql").value = EXAMPLES[0][1];
  $("#sqlExamples").addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-ex]");
    if (b) { $("#sql").value = EXAMPLES[Number(b.dataset.ex)][1]; runSql(); }
  });
  $("#sqlRun").addEventListener("click", () => runSql());
  async function runSql() {
    $("#sqlErr").textContent = "";
    try {
      const r = await api("/api/sql", { method: "POST", body: { query: $("#sql").value } });
      $("#sqlOut").innerHTML = r.rows.length
        ? `<table><thead><tr>${r.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${r.rows.map((row) =>
            `<tr style="cursor:default">${row.map((v) => `<td class="${typeof v === "number" ? "num" : ""}">${v === null ? '<span class="muted">NULL</span>' : esc(typeof v === "object" ? JSON.stringify(v) : v)}</td>`).join("")}</tr>`).join("")}</tbody></table>`
          + (r.truncated ? '<p class="muted" style="padding:8px 12px">First 200 rows</p>' : "")
        : '<div class="empty">No rows</div>';
    } catch (e) { $("#sqlErr").textContent = e.message; $("#sqlOut").innerHTML = ""; }
  }

  /* ---------- refresh loop ---------- */
  async function refresh(withMeta = false) {
    // the record pickers must update after every action, even if the 3-second refresh is mid-flight
    const metaDone = withMeta ? loadMeta().catch(() => {}) : null;
    if (busy) { if (metaDone) await metaDone; return; }
    busy = true;
    try {
      await loadOverview();
      await Promise.all([loadRecords(), loadOutbox(), loadEvents()]);
      if (metaDone) await metaDone;
    } catch (e) {
      toast("Console lost contact with the connector: " + e.message, true);
    } finally { busy = false; }
  }

  fillFields("#bcField", "bc", "items");
  fillFields("#mxField", "mysql", "items");
  refresh(true);
  setInterval(() => refresh(false), 3000);
  setInterval(() => loadMeta().catch(() => {}), 15000);
})();
