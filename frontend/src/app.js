const $ = id => document.getElementById(id);
const pages = {sources:"Data Sources", workspace:"Studio SQL", explorer:"Studio SQL", "source-new":"Ajouter une connexion SQL Server", overview:"Storage", jobs:"Studio SQL", sql:"Studio SQL", history:"Studio SQL", performance:"Performances"};
const statuses = {queued:"En attente", running:"En cours", completed:"Terminée", failed:"En erreur"};
const escape = value => String(value ?? "—").replace(/[&<>"']/g, char =>
  ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"})[char]);
const number = (value, digits = 0) => new Intl.NumberFormat("fr-FR", {
  maximumFractionDigits: digits, minimumFractionDigits: digits
}).format(value);
const empty = text => '<p class="empty">' + escape(text) + '</p>';
const option = (value, label) => new Option(label, value);
const busy = (button, action) => guarded(async () => {
  button.disabled = true;
  try { await action(); } finally { button.disabled = false; }
});
let sources = [], sourceTables = [], columns = [], jobs = [], records = [];
let selected = null, exportResult = null, focusedJob = null, routeVersion = 0, jobListVersion = 0, lastSqlExportId = null;

async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(data)
  });
  const payload = await response.json();
  if (!response.ok) {
    const detail = payload.detail;
    throw new Error(typeof detail === "string" ? detail : Array.isArray(detail)
      ? detail.map(item => item.msg).join(" · ") : detail?.error || "Opération indisponible (" + response.status + ").");
  }
  return payload;
}

function notice(message, error = false) {
  $("notice").hidden = !message;
  $("notice").classList.toggle("error", error);
  $("notice").textContent = message;
}
async function guarded(action) {
  try { await action(); } catch (error) { notice(error.message, true); }
}

function table(headers, rows) {
  return '<div class="table-wrap"><table><thead><tr>' + headers.map(header =>
    '<th scope="col">' + escape(header) + '</th>').join("") + '</tr></thead><tbody>' + rows.map(row =>
    '<tr>' + row.map(cell => '<td>' + cell + '</td>').join("") + '</tr>').join("") + '</tbody></table></div>';
}

function metric(label, value, hint) {
  return '<div class="metric"><span>' + escape(label) + '</span><strong>' + escape(value) +
    '</strong><small>' + escape(hint) + '</small></div>';
}

function showJobs(items) {
  return items.length ? table(["Table source", "Format", "Partition", "État", ""], items.map(job => [
    '<b>' + escape(job.request.schema + "." + job.request.table) + '</b><small class="sub">' + escape(job.request.source_id) + '</small>',
    escape(job.request.format.toUpperCase()), escape(job.request.partition_by.join(", ") || "Aucune"),
    '<span class="status ' + escape(job.status) + '">' + escape(statuses[job.status]) + '</span>',
    '<button class="link" type="button" data-job="' + escape(job.id) + '">Détails</button>'
  ])) : empty("Aucune extraction enregistrée.");
}

async function refreshJobs() {
  const version = ++jobListVersion;
  const response = await api("/storage/jobs");
  if (version !== jobListVersion) return;
  jobs = response;
  $("job-list").innerHTML = showJobs(jobs);
  $("recent").innerHTML = showJobs(jobs.slice(0, 5));
}

async function refreshSources(preferred = $("source").value) {
  sources = await api("/sources");
  $("source").replaceChildren(...sources.map(source => option(source.id, source.id + " · " + source.database)));
  if (sources.some(source => source.id === preferred)) $("source").value = preferred;
  $("test-source").disabled = !sources.length;
}

function refreshSelection() {
  $("selection").textContent = selected ? selected.source_id + " / " + selected.schema + "." + selected.table :
    "Choisissez une table dans l’explorateur.";
  $("submit-job").disabled = !selected;
  $("partitions").replaceChildren();
  const dates = columns.filter(column => ["date", "datetime", "datetime2", "smalldatetime"].includes(column.type)
    && /^[a-z_][a-z0-9_]*$/i.test(column.name)
    && (column.type === "date" || !columns.some(other => other.name.toLowerCase() === column.name.toLowerCase() + "_day")));
  if (!dates.length) {
    $("partitions").textContent = "Aucune colonne de date ou d’horodatage disponible.";
    return;
  }
  const label = document.createElement("label");
  label.textContent = "Colonne à partitionner";
  const select = document.createElement("select");
  select.name = "partition";
  select.append(option("", "Aucune partition"), ...dates.map(column => option(column.name,
    column.name + " · " + column.type.toUpperCase() + (column.type === "date" ? "" : " → " + column.name.toLowerCase() + "_day"))));
  label.append(select);
  $("partitions").append(label);
}

function renderTableTree() {
  const active = $("table").value;
  const groups = new Map();
  sourceTables.forEach((item, index) => {
    if (!groups.has(item.schema)) groups.set(item.schema, []);
    groups.get(item.schema).push({item, index});
  });
  $("table-tree").innerHTML = groups.size ? [...groups].map(([schema, items]) =>
    '<div class="studio-tree-schema"><span class="studio-tree-folder" aria-hidden="true">▾</span>' + escape(schema) + '</div>' +
    items.map(({item, index}) => '<button type="button" role="treeitem" data-table-index="' + index +
      '" aria-selected="' + (String(index) === active) + '" class="studio-tree-table' +
      (String(index) === active ? ' is-active' : '') + '"><span aria-hidden="true">▦</span>' + escape(item.table) + '</button>').join('')
  ).join('') : empty("Aucune table disponible.");
}

async function loadColumns() {
  const source = $("source").value;
  const tableIndex = $("table").value;
  const item = sourceTables[tableIndex];
  renderTableTree();
  selected = null;
  columns = [];
  refreshSelection();
  $("columns").innerHTML = item ? empty("Lecture des colonnes…") : empty("Aucune table sélectionnée.");
  if (!item) return;
  const response = await api("/sources/" + encodeURIComponent(source) + "/tables/" + encodeURIComponent(item.table) +
    "/columns?schema=" + encodeURIComponent(item.schema));
  if (source !== $("source").value || tableIndex !== $("table").value) return;
  selected = {source_id:source, schema:item.schema, table:item.table};
  columns = response;
  $("columns").innerHTML = table(["Colonne", "Type SQL Server", "Valeur nulle"], columns.map(column => [
    escape(column.name), escape(["decimal","numeric"].includes(column.type) ? column.type +
      "(" + column.precision + "," + column.scale + ")" : column.type), column.is_nullable ? "Oui" : "Non"
  ]));
  refreshSelection();
}

async function loadTables() {
  const source = $("source").value;
  const previous = selected?.source_id === source ? selected : null;
  sourceTables = [];
  $("table").replaceChildren(option("", "Chargement…"));
  await loadColumns();
  const response = source ? await api("/sources/" + encodeURIComponent(source) + "/tables") : [];
  if (source !== $("source").value) return;
  sourceTables = response;
  $("table").replaceChildren(...sourceTables.map((item, i) => option(i, item.schema + "." + item.table)));
  if (!sourceTables.length) $("table").append(option("", "Aucune table"));
  const index = previous ? sourceTables.findIndex(item => item.schema === previous.schema && item.table === previous.table) : -1;
  if (index >= 0) $("table").value = index;
  renderTableTree();
  await loadColumns();
}

async function jobDetails(id) {
  focusedJob = id;
  const job = await api("/storage/jobs/" + id);
  const result = job.status === "completed" ? await api("/storage/jobs/" + id + "/result") : null;
  if (focusedJob !== id) return;
  const target = $("job-details");
  target.hidden = false;
  target.innerHTML = '<div class="card-head"><h2>' + escape(job.request.schema + "." + job.request.table) +
    '</h2><span class="status ' + escape(job.status) + '">' + escape(statuses[job.status]) + '</span></div><p class="muted mono">' +
    escape(id) + '</p>' + (job.error ? '<p class="failure">' + escape(job.error) + '</p>' : "") +
    (result ? '<div class="metrics">' + metric("Lignes", number(result.rows), result.format.toUpperCase()) +
      metric("Fichiers", number(result.files), result.compression) +
      metric("Taille", number(result.bytes / 1e6, 2) + " Mo", number(result.total_seconds, 2) + " s au total") +
      '</div><dl class="detail"><dt>Emplacement MinIO</dt><dd>' + escape(result.storage_uri) +
      '</dd><dt>Table Trino</dt><dd>' + escape(result.sql_table) + '</dd>' +
      (result.partition_by.length ? '<dt>Partition par jour</dt><dd>' + escape(result.partition_by.map((name, index) => {
        const source = result.partition_source_columns?.[index] || name;
        return source === name ? name : source + ' → ' + name;
      }).join(', ')) + '</dd>' : '') + '<dt>Extraction</dt><dd>' +
      number(result.extraction_seconds, 3) + ' s</dd><dt>Chargement</dt><dd>' + number(result.load_seconds, 3) +
      ' s</dd></dl><button class="primary" data-sql="' + escape(id) + '">Interroger dans Trino</button>' : "");
}

async function chooseExport() {
  const id = $("sql-export").value;
  exportResult = null;
  $("query-preview").disabled = !id;
  $("query-count").disabled = !id;
  $("sql-partition").replaceChildren(option("", "Aucune partition"));
  $("sql-date").disabled = true;
  $("sql-date").value = "";
  $("sql-output").hidden = true;
  if (!id) return;
  const result = await api("/storage/jobs/" + id + "/result");
  if ($("sql-export").value !== id) return;
  exportResult = result;
  $("sql-partition").replaceChildren(...(result.partition_by.length
    ? result.partition_by.map(key => option(key, key)) : [option("", "Aucune partition")]));
  $("sql-date").disabled = !result.partition_by.length;
  if (lastSqlExportId !== id) {
    lastSqlExportId = id;
    setQueryTemplate("preview");
  }
}

function setQueryTemplate(operation) {
  if (!exportResult) return;
  const tableName = exportResult.sql_table;
  const day = $("sql-date").value;
  const partition = $("sql-partition").value;
  const value = exportResult.format === "parquet" ? `DATE '${day}'` : `'${day}'`;
  const where = day && partition ? ` WHERE "${partition}" = ${value}` : "";
  $("sql-editor").value = operation === "count"
    ? `SELECT count(*) AS lignes FROM ${tableName}${where};`
    : `SELECT * FROM ${tableName}${where} LIMIT 100;`;
  $("sql-editor").focus();
}

async function refreshSqlExports(preferred) {
  const prior = preferred || $("sql-export").value;
  const done = jobs.filter(job => job.status === "completed");
  $("sql-export").replaceChildren(option("", "Choisir un export"), ...done.map(job => option(job.id,
    job.request.table + " · " + job.request.format.toUpperCase() + " · " + job.id.slice(0, 8))));
  if (done.some(job => job.id === prior)) $("sql-export").value = prior;
  else if (done.length && !$("sql-editor").value.trim()) $("sql-export").value = done[0].id;
  await chooseExport();
}

const benchFilters = {format:"bench-format", partitioned:"bench-partition", compression:"bench-compression", batch_size:"bench-batch"};
function renderBenchmark() {
  const filtered = records.filter(row => Object.entries(benchFilters).every(([key, id]) =>
    !$(id).value || row[key] === $(id).value));
  $("benchmark-table").innerHTML = filtered.length ? table(
    ["Format", "Compression", "Partition", "Lot", "Fichiers", "Taille (Mo)", "Extraction (s)", "Chargement (s)", "SQL global (s)", "SQL filtré (s)"],
    filtered.map(r => [escape(r.format.toUpperCase()), r.compression === "none" ? "Aucune" : escape(r.compression),
      r.partitioned === "jour" ? "Jour" : "Aucune", number(r.batch_size), number(r.files), number(r.bytes / 1e6, 2),
      ...["extraction_seconds","load_seconds","scan_seconds","filter_seconds"].map(key => number(r[key], 3))])
  ) : empty("Aucun scénario pour ces filtres.");
}

function ratio(dimension, baseline, variant, metricKey) {
  const keys = Object.keys(benchFilters).filter(key => key !== dimension);
  const pairs = records.filter(r => r[dimension] === baseline && Number(r[metricKey]) > 0).flatMap(r =>
    records.filter(v => v[dimension] === variant && keys.every(key => r[key] === v[key]))
      .map(v => Number(v[metricKey]) / Number(r[metricKey]))).sort((a,b) => a-b);
  const middle = Math.floor(pairs.length / 2);
  return pairs.length ? (pairs[middle] + pairs[Math.floor((pairs.length - 1) / 2)]) / 2 : null;
}
async function loadBenchmark() {
  records = await api("/performance/results");
  const batches = [...new Set(records.map(r => r.batch_size))].sort((a,b) => a-b);
  $("bench-batch").replaceChildren(option("", "Toutes"), ...batches.map(n => option(n, number(n))));
  renderBenchmark();
  if (!records.length) return;
  $("benchmark-metrics").innerHTML = metric("Scénarios", records.length, "Combinaisons mesurées") +
    metric("Factures par scénario", number(records[0].rows), "Jeu de données fictif") +
    metric("Taille minimale", number(Math.min(...records.map(r => Number(r.bytes))) / 1e6, 2) + " Mo", "Objets stockés dans MinIO");
  const observations = [
    ["Parquet / CSV", ratio("format","csv","parquet","scan_seconds"), "Requête globale", "Trino peut cibler la colonne montant dans Parquet."],
    ["Partition jour / aucune", ratio("partitioned","non","jour","filter_seconds"), "Requête filtrée", "Le filtre permet à Trino d’écarter les autres partitions."],
    ["Gzip / aucune compression", ratio("compression","none","gzip","bytes"), "Taille stockée", "La compression réduit les octets écrits et demande du temps d’encodage."],
    ["Grand lot / petit lot", ratio("batch_size",batches[0],batches.at(-1),"files"), "Nombre de fichiers", "La taille du lot et le nombre de partitions influencent le nombre d’objets."]
  ];
  $("benchmark-insights").innerHTML = '<div class="insights">' + observations.filter(row => row[1] !== null)
    .map(([label, value, measure, note]) => '<div><strong>' + number(value, 2) + '×</strong><h3>' +
      escape(label) + '</h3><p>' + escape(measure + " · " + note) + '</p></div>').join("") + '</div>';
}

function setStudioTab(tab) {
  for (const button of document.querySelectorAll("[data-studio-tab]")) {
    button.setAttribute("aria-selected", String(button.dataset.studioTab === tab));
  }
  for (const name of ["structure", "extract", "sql", "history"]) $("studio-" + name).hidden = name !== tab;
}

async function navigate(preferredExport) {
  const current = ++routeVersion;
  const page = Object.hasOwn(pages, location.hash.slice(1)) ? location.hash.slice(1) : "sources";
  const isWorkspace = ["workspace", "explorer", "jobs", "sql", "history"].includes(page);
  const visiblePage = isWorkspace ? "workspace" : page;
  for (const key of ["sources", "workspace", "source-new", "overview", "performance"]) $(key).hidden = key !== visiblePage;
  for (const item of document.querySelectorAll("[data-page]")) {
    if (item.dataset.page === (page === "source-new" ? "sources" : visiblePage)) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  }
  window.scrollTo(0, 0);
  const tab = page === "jobs" ? "extract" : page === "sql" ? "sql" : page === "history" ? "history" : "structure";
  $("breadcrumb").textContent = page === "source-new" ? "Data Sources  ›  " + pages[page] :
    isWorkspace ? "Studio SQL  ›  " + ({structure:"Structure", extract:"Extraction", sql:"Éditeur SQL", history:"Historique"})[tab] : pages[page];
  notice("");
  if (page === "overview") await refreshJobs();
  if (page === "sources") { await refreshSources(); if (current === routeVersion) renderSources(); }
  if (isWorkspace) {
    setStudioTab(tab);
    const source = preferredSource || $("source").value;
    const forceReload = !!preferredSource;
    preferredSource = null;
    await refreshSources(source);
    if (current !== routeVersion) return;
    if (forceReload || !sourceTables.length || selected?.source_id !== $("source").value) await loadTables();
    if (current !== routeVersion) return;
    await refreshJobs();
    if (current !== routeVersion) return;
    await refreshSqlExports(preferredExport);
    if (focusedJob && tab === "history") {
      await jobDetails(focusedJob);
      $("job-details").scrollIntoView({block:"nearest"});
    }
  }
  if (page === "performance") await loadBenchmark();
}

let nextExport;
window.addEventListener("hashchange", () => { const id = nextExport; nextExport = null; guarded(() => navigate(id)); });
document.addEventListener("click", event => {
  const job = event.target.closest("[data-job]");
  if (job) {
    focusedJob = job.dataset.job;
    if (location.hash === "#history") guarded(async () => {
      await jobDetails(focusedJob);
      $("job-details").scrollIntoView({behavior:"smooth", block:"nearest"});
    });
    else location.hash = "history";
  }
  const sql = event.target.closest("[data-sql]");
  if (sql) {
    nextExport = sql.dataset.sql;
    if (location.hash === "#sql") {
      const id = nextExport;
      nextExport = null;
      guarded(() => refreshSqlExports(id));
    }
    else location.hash = "sql";
  }
});
$("source").onchange = () => guarded(loadTables);
$("table").onchange = () => guarded(loadColumns);
$("table-tree").onclick = event => {
  const button = event.target.closest("[data-table-index]");
  if (!button) return;
  $("table").value = button.dataset.tableIndex;
  guarded(loadColumns);
  if (location.hash !== "#workspace") location.hash = "workspace";
  else setStudioTab("structure");
};
$("refresh-tables").onclick = () => guarded(loadTables);
for (const button of document.querySelectorAll("[data-studio-tab]")) button.onclick = () => {
  const hash = ({structure:"workspace", extract:"jobs", sql:"sql", history:"history"})[button.dataset.studioTab];
  if (location.hash === "#" + hash) setStudioTab(button.dataset.studioTab);
  else location.hash = hash;
};
$("test-source").onclick = () => busy($("test-source"), async () => {
  const response = await testSaved($("source").value);
  notice("Connexion réussie pour " + response.source_id + ".");
});
$("source-form").onsubmit = event => {
  event.preventDefault();
  busy(event.submitter, async () => {
    const source = await api("/sources", draftData());
    if (successfulDraft) {
      sourceChecks[source.id] = {state:"connected", at:successfulDraft.at};
      storeSourceChecks();
    }
    event.target.reset();
    passwordVisibility(false);
    successfulDraft = null;
    resetDraft();
    $("source-search").value = "";
    sourceFilter = "all";
    location.hash = "sources";
  });
};
function compressionOptions() {
  const values = $("format").value === "parquet" ? ["snappy","none","gzip","zstd"] : ["none","gzip"];
  $("compression").replaceChildren(...values.map(value => option(value, value === "none" ? "Aucune" : value.toUpperCase())));
}
$("format").onchange = compressionOptions;
$("job-form").onsubmit = event => {
  event.preventDefault();
  if (!selected) return;
  busy(event.submitter, async () => {
    const form = new FormData(event.target);
    const created = await api("/storage/jobs", {...selected, format:form.get("format"), compression:form.get("compression"),
      batch_size:Number(form.get("batch_size")), partition_by:form.getAll("partition").filter(Boolean)});
    notice("Extraction ajoutée à la file.");
    await refreshJobs();
    await jobDetails(created.id);
    $("job-details").scrollIntoView({behavior:"smooth", block:"nearest"});
  });
};
$("refresh-jobs").onclick = () => guarded(async () => { await refreshJobs(); if (focusedJob) await jobDetails(focusedJob); });
$("sql-export").onchange = () => guarded(chooseExport);
$("query-preview").onclick = () => setQueryTemplate("preview");
$("query-count").onclick = () => setQueryTemplate("count");
$("sql-editor").onkeydown = event => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    $("sql-form").requestSubmit();
  }
};
$("sql-form").onsubmit = event => {
  event.preventDefault();
  busy(event.submitter || $("run-query"), async () => {
    $("sql-output").hidden = false;
    $("sql-output").innerHTML = '<p class="muted">Exécution de la requête dans Trino…</p>';
    try {
      const output = await api("/sql/query", {sql:$("sql-editor").value, limit:200});
      $("sql-output").innerHTML = '<div class="studio-results-head"><h3>Résultat de la requête</h3><span>' +
        number(output.row_count) + ' lignes · ' + number(output.elapsed_ms) + ' ms' +
        (output.truncated ? ' · Affichage limité à 200 lignes' : '') + '</span></div>' +
        (output.rows.length ? table(output.columns, output.rows.map(row => row.map(cell =>
          escape(typeof cell === "object" && cell !== null ? JSON.stringify(cell) : cell)))) :
          empty("Aucune ligne retournée."));
    } catch (error) {
      $("sql-output").innerHTML = '<p class="failure">' + escape(error.message) + '</p>';
    }
  });
};
for (const id of Object.values(benchFilters)) $(id).onchange = renderBenchmark;
async function refreshHealth() {
  try { await api("/health"); $("health").textContent = "Services opérationnels"; $("health").className = "online"; }
  catch { $("health").textContent = "Services indisponibles"; $("health").className = ""; }
}
const sourceLabels = {all:"Toutes", connected:"Connectées", failed:"En échec", untested:"Non testées"};
const sourceStates = {connected:"Connectée", failed:"Échec", running:"Test en cours", untested:"Non testée"};
let sourceFilter = "all", preferredSource;
const sourceChecks = Object.create(null);
try { Object.assign(sourceChecks, JSON.parse(localStorage.getItem("data-platform-source-checks") || "{}")); } catch {}

function storeSourceChecks() {
  try { localStorage.setItem("data-platform-source-checks", JSON.stringify(
    Object.fromEntries(Object.entries(sourceChecks).filter(([, test]) => test.state !== "running")))); } catch {}
}
const checkedAt = at => at ? new Intl.DateTimeFormat("fr-FR", {dateStyle:"medium", timeStyle:"short"}).format(new Date(at)) : "Jamais";

function renderSources() {
  const search = $("source-search").value.trim();
  const query = search.toLocaleLowerCase("fr");
  const matching = sources.filter(source => [source.id, source.host, source.database, String(source.port)].some(
    value => value.toLocaleLowerCase("fr").includes(query)));
  const status = source => sourceChecks[source.id]?.state || "untested";
  const visible = matching.filter(source => sourceFilter === "all" || status(source) === sourceFilter);
  $("source-toolbar").hidden = !sources.length;
  $("source-filters").innerHTML = Object.entries(sourceLabels).map(([key,label]) =>
    '<button class="secondary filter" data-source-filter="' + key + '" aria-pressed="' + (sourceFilter === key) +
    '">' + label + ' <small>' + matching.filter(source => key === "all" || status(source) === key).length + '</small></button>').join("");
  if (!sources.length) {
    $("source-list").innerHTML = '<div class="card source-empty"><span class="empty-icon wire-icon database" aria-hidden="true"></span><h2>Aucune source de données pour l’instant</h2><p>Connectez votre première base SQL Server pour explorer ses tables et lancer des extractions.</p><a class="button primary" href="#source-new"><span class="wire-icon plus" aria-hidden="true"></span>Ajouter une source</a></div>';
    return;
  }

  const footer = '<div class="source-footer"><span>' + visible.length + ' sur ' + sources.length + ' sources affichées</span>' +
    '<span>Les statuts reflètent le dernier test</span></div>';
  if (!visible.length) {
    $("source-list").innerHTML = '<div class="card source-grid"><div class="source-empty"><span class="empty-icon wire-icon search-icon" aria-hidden="true"></span><h2>' +
      escape(search ? 'Aucune source ne correspond à « ' + search + ' »' : "Aucune source pour ce filtre") +
      '</h2><p>La recherche porte sur le nom de la connexion, l’hôte et la base de données.</p><button class="secondary" id="clear-source-search">Effacer la recherche</button></div>' + footer + '</div>';
    return;
  }
  $("source-list").innerHTML = '<div class="card source-grid">' +
    table(["Type","Nom de la connexion","Hôte / Serveur","Base de données","Statut","Dernier test","Actions"], visible.map(source => {
      const state = status(source);
      const test = sourceChecks[source.id];
      const id = escape(source.id);
      return ['<span class="wire-icon database" aria-hidden="true"></span> SQL Server','<b>' + id + '</b>',
        '<span class="mono">' + escape(source.host + ":" + source.port) + '</span>', escape(source.database),
        '<span class="status ' + state + '">' + escape(sourceStates[state]) + '</span>' +
          (state === "failed" ? '<small class="sub source-error">' + escape(test.message) + '</small>' : ""),
        escape(checkedAt(test?.at)), '<div class="actions"><button class="secondary" data-test-source="' + id + '"' +
          (state === "running" ? ' disabled>Test…' : '><span class="wire-icon jobs" aria-hidden="true"></span>Tester') + '</button><button class="link" data-explore-source="' +
          id + '">Explorer</button></div>'];
    })) + footer + '</div>';
}

async function testSaved(id) {
  const previous = sourceChecks[id];
  sourceChecks[id] = {...previous, state:"running"};
  renderSources();
  try {
    const result = await api("/sources/" + encodeURIComponent(id) + "/test");
    sourceChecks[id] = {state:"connected", at:Date.now()};
    return result;
  } catch (error) {
    sourceChecks[id] = {state:"failed", at:Date.now(), message:error.message};
    throw error;
  } finally {
    storeSourceChecks();
    renderSources();
  }
}

function draftData() {
  const data = Object.fromEntries(new FormData($("source-form")));
  data.port = Number(data.port);
  data.login_timeout = Number(data.login_timeout);
  data.encryption = data.encryption || null;
  return data;
}

function draftSteps(state, config) {
  if (!config || !["running", "connected"].includes(state)) return "";
  const ok = state === "connected";
  const steps = [
    ["Joindre le serveur", config.host + ":" + config.port, ok ? "Réussi" : "En cours"],
    ["Sécuriser la connexion", config.encryption === "require" ? "Chiffrement exigé" : "Paramètre du pilote",
      ok ? (config.encryption === "require" ? "Réussi" : "Par défaut") : "En attente"],
    ["S’authentifier", config.user, ok ? "Réussi" : "En attente"],
    ["Ouvrir la base de données", config.database, ok ? "Réussi" : "En attente"]
  ];
  return '<ol class="test-steps">' + steps.map(([label, detail, outcome]) => '<li><span aria-hidden="true">' +
    (outcome === "Réussi" ? "✓" : outcome === "En cours" ? "◌" : "–") +
    '</span><div><strong>' + escape(label) + '</strong><small>' + escape(detail) +
    '</small></div><em>' + escape(outcome) + '</em></li>').join("") + '</ol>';
}

function draftStatus(state, title, message, result, config) {
  $("draft-result").dataset.state = state;
  $("draft-result").innerHTML = '<div class="test-summary"><strong>' + escape(title) + '</strong><p>' + escape(message) + '</p></div>' + draftSteps(state, config) +
    (result ? '<dl class="test-details"><dt>Base de données</dt><dd>' + escape(result.database) +
      '</dd><dt>Version du serveur</dt><dd>' + escape(result.version) +
      '</dd><dt>Temps de réponse</dt><dd>' + number(result.elapsed_ms) + ' ms</dd><dt>Testée le</dt><dd>' +
      escape(checkedAt(Date.now())) + '</dd></dl><p class="muted">Enregistrez la connexion pour l’ajouter à Data Sources.</p>' : "");
  $("draft-footer-state").textContent = title;
  $("draft-alert").hidden = state !== "failed";
  $("draft-alert").textContent = state === "failed" ? message : "";
}

function passwordVisibility(visible) {
  const button = $("toggle-password");
  $("source-form").elements.password.type = visible ? "text" : "password";
  button.setAttribute("aria-pressed", String(visible));
  button.setAttribute("aria-label", visible ? "Masquer le mot de passe" : "Afficher le mot de passe");
}
$("toggle-password").onclick = () => passwordVisibility($("toggle-password").getAttribute("aria-pressed") !== "true");

function resetDraft() {
  draftStatus("untested", "Pas encore testée", "Lancez un test pour vérifier que la plateforme peut joindre ce serveur et ouvrir cette base avec les identifiants saisis.");
}
let successfulDraft = null;
$("source-form").addEventListener("input", () => { successfulDraft = null; resetDraft(); });
$("cancel-source").onclick = () => { $("source-form").reset(); passwordVisibility(false); successfulDraft = null; resetDraft(); };
$("test-draft").onclick = async () => {
  const form = $("source-form");
  if (!form.reportValidity()) return;
  const data = draftData();
  successfulDraft = null;
  const controls = [...form.querySelectorAll("input, select, button")];
  const cancel = $("cancel-source");
  for (const control of controls) control.disabled = true;
  cancel.hidden = true;
  draftStatus("running", "Test de la connexion en cours…", "Vérification du serveur, de l’authentification et de l’accès à la base de données.", null, data);
  try {
    const result = await api("/sources/test", data);
    successfulDraft = {at:Date.now()};
    draftStatus("connected", "Connexion réussie", "La plateforme a joint le serveur, s’est authentifiée et a ouvert la base.", result, data);
  } catch (error) {
    draftStatus("failed", "Échec de la connexion", error.message);
  } finally {
    for (const control of controls) control.disabled = false;
    cancel.hidden = false;
  }
};
$("source-search").oninput = renderSources;
$("source-filters").onclick = event => {
  const button = event.target.closest("[data-source-filter]");
  if (!button) return;
  sourceFilter = button.dataset.sourceFilter;
  renderSources();
  $("source-filters").querySelector('[aria-pressed="true"]')?.focus();
};
$("source-list").onclick = event => {
  const test = event.target.closest("[data-test-source]");
  const explore = event.target.closest("[data-explore-source]");
  if (test) guarded(() => testSaved(test.dataset.testSource));
  if (explore) { preferredSource = explore.dataset.exploreSource; location.hash = "explorer"; }
  if (event.target.closest("#clear-source-search")) {
    $("source-search").value = "";
    sourceFilter = "all";
    renderSources();
    $("source-search").focus();
  }
};
resetDraft();

compressionOptions();
refreshSelection();
guarded(navigate);
refreshHealth();
let polling = false;
setInterval(async () => {
  if (polling || document.hidden) return;
  polling = true;
  try {
    await refreshHealth();
    if (["","#overview","#workspace","#explorer","#jobs","#sql","#history"].includes(location.hash)) {
      await guarded(async () => {
        await refreshJobs();
        if (location.hash === "#history" && focusedJob) await jobDetails(focusedJob);
      });
    }
  } finally { polling = false; }
}, 4000);
