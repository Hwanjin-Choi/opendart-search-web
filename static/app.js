const reportNameMap = {
  "11011": "사업보고서",
  "11012": "반기보고서",
  "11013": "1분기보고서",
  "11014": "3분기보고서",
};

const state = {
  selectedCompanies: [],
  lastResult: null,
};

const form = document.getElementById("search-form");
const queryInput = document.getElementById("query");
const suggestionsEl = document.getElementById("suggestions");
const downloadButton = document.getElementById("download-json");
const overviewPanel = document.getElementById("overview-panel");
const singleTableWrap = document.getElementById("single-table");
const multiTableWrap = document.getElementById("multi-table");
const indexTableWrap = document.getElementById("index-table");
const rawJsonEl = document.getElementById("raw-json");
const statusText = document.getElementById("status-text");
const companyText = document.getElementById("company-text");
const requestText = document.getElementById("request-text");

const filters = {
  single: document.getElementById("single-filter"),
  multi: document.getElementById("multi-filter"),
  index: document.getElementById("index-filter"),
};

let suggestionTimer = null;

function setStatus(message) {
  statusText.textContent = message;
}

function setRequestLabel() {
  const year = document.getElementById("bsns-year").value;
  const reprtCode = document.getElementById("reprt-code").value;
  requestText.textContent = `${year} / ${reportNameMap[reprtCode] || reprtCode}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toLocaleString("ko-KR") : value.toLocaleString("ko-KR", { maximumFractionDigits: 6 });
  }

  return String(value);
}

async function fetchSuggestions() {
  const query = getCurrentToken(queryInput.value);
  if (!query) {
    renderSuggestions([]);
    return;
  }

  const response = await fetch(`/api/companies?q=${encodeURIComponent(query)}&limit=8`);
  const payload = await response.json();
  renderSuggestions(payload.matches || []);
}

function getTokens(rawValue) {
  return String(rawValue || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function getCurrentToken(rawValue) {
  const parts = String(rawValue || "").split(",");
  return (parts[parts.length - 1] || "").trim();
}

function renderSuggestions(matches) {
  if (!matches.length) {
    suggestionsEl.classList.remove("visible");
    suggestionsEl.innerHTML = "";
    return;
  }

  suggestionsEl.innerHTML = matches
    .map(
      (match) => `
        <button
          class="suggestion-item"
          type="button"
          data-corp-code="${escapeHtml(match.corp_code)}"
          data-corp-name="${escapeHtml(match.corp_name)}"
          data-stock-code="${escapeHtml(match.stock_code)}"
        >
          <strong>${escapeHtml(match.corp_name)}</strong>
          <span class="suggestion-meta">고유번호 ${escapeHtml(match.corp_code)} / 종목코드 ${escapeHtml(match.stock_code || "-")}</span>
        </button>
      `
    )
    .join("");
  suggestionsEl.classList.add("visible");
}

function selectSuggestion(match) {
  const parts = queryInput.value.split(",");
  if (parts.length <= 1) {
    queryInput.value = match.corp_name;
  } else {
    parts[parts.length - 1] = ` ${match.corp_name}`;
    queryInput.value = `${parts.join(",").replace(/^ /, "")}, `;
  }
  renderSuggestions([]);
}

function collectIdxCodes() {
  return Array.from(document.querySelectorAll('input[name="idx_cl_codes"]:checked')).map((input) => input.value);
}

function buildOverview(data) {
  const selectedCompanies = data.selected_companies || [];
  const singleList = data.responses.fnlttSinglAcnt.list || [];
  const multiList = data.responses.fnlttMultiAcnt.list || [];
  const indexRows = flattenIndexRows(data.responses.fnlttSinglIndx);

  const cards = [
    { label: "선택 기업 수", value: `${selectedCompanies.length}개` },
    { label: "선택 기업", value: selectedCompanies.map((company) => company.corp_name).join(", ") || "-" },
    { label: "종목코드", value: selectedCompanies.map((company) => company.stock_code || "-").join(", ") || "-" },
    { label: "보고서", value: `${data.request.bsns_year} / ${data.request.report_name || data.request.reprt_code}` },
    { label: "단일계정 건수", value: singleList.length },
    { label: "다중계정 건수", value: multiList.length },
    { label: "지표 건수", value: indexRows.length },
    { label: "지표 분류", value: data.request.idx_cl_codes.join(", ") },
  ];

  const candidatePills = selectedCompanies
    .slice(0, 5)
    .map(
      (candidate) =>
        `<span class="candidate-pill">${escapeHtml(candidate.corp_name)} · ${escapeHtml(candidate.stock_code || candidate.corp_code)}</span>`
    )
    .join("");

  overviewPanel.innerHTML = `
    <div class="summary-grid">
      ${cards
        .map(
          (card) => `
            <article class="summary-card">
              <span class="label">${escapeHtml(card.label)}</span>
              <div class="value">${escapeHtml(formatValue(card.value))}</div>
            </article>
          `
        )
        .join("")}
    </div>
    <div class="status-badge">OpenDART 상태: ${escapeHtml(data.responses.fnlttSinglAcnt.status)} / ${escapeHtml(data.responses.fnlttMultiAcnt.status)}</div>
    <div class="candidate-list">${candidatePills}</div>
  `;
}

function flattenIndexRows(indexResponses) {
  return Object.values(indexResponses || {}).flatMap((entry) => entry.list || []);
}

function renderTable(targetEl, rows, columns) {
  if (!rows.length) {
    targetEl.innerHTML = '<div class="empty-state">표시할 데이터가 없습니다.</div>';
    return;
  }

  const thead = columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("");
  const tbody = rows
    .map(
      (row) => `
        <tr>
          ${columns.map((column) => `<td>${escapeHtml(formatValue(row[column.key]))}</td>`).join("")}
        </tr>
      `
    )
    .join("");

  targetEl.innerHTML = `
    <table>
      <thead><tr>${thead}</tr></thead>
      <tbody>${tbody}</tbody>
    </table>
  `;
}

function renderSingleAndMulti() {
  if (!state.lastResult) {
    singleTableWrap.innerHTML = '<div class="empty-state">검색 결과가 없습니다.</div>';
    multiTableWrap.innerHTML = '<div class="empty-state">검색 결과가 없습니다.</div>';
    return;
  }

  const singleFilter = filters.single.value.trim();
  const multiFilter = filters.multi.value.trim();

  const singleRows = (state.lastResult.responses.fnlttSinglAcnt.list || []).filter((row) =>
    !singleFilter || String(row.account_nm || "").includes(singleFilter)
  );
  const multiRows = (state.lastResult.responses.fnlttMultiAcnt.list || []).filter((row) =>
    !multiFilter || String(row.account_nm || "").includes(multiFilter)
  );

  const columns = [
    { key: "corp_name", label: "회사명" },
    { key: "fs_div", label: "구분" },
    { key: "sj_nm", label: "재무제표" },
    { key: "account_nm", label: "계정명" },
    { key: "thstrm_dt", label: "당기일자" },
    { key: "thstrm_amount", label: "당기금액" },
    { key: "frmtrm_amount", label: "전기금액" },
    { key: "bfefrmtrm_amount", label: "전전기금액" },
    { key: "currency", label: "통화" },
  ];

  renderTable(singleTableWrap, singleRows, columns);
  renderTable(multiTableWrap, multiRows, columns);
}

function renderIndexTable() {
  if (!state.lastResult) {
    indexTableWrap.innerHTML = '<div class="empty-state">검색 결과가 없습니다.</div>';
    return;
  }

  const indexFilter = filters.index.value.trim();
  const rows = flattenIndexRows(state.lastResult.responses.fnlttSinglIndx).filter((row) =>
    !indexFilter || String(row.idx_nm || "").includes(indexFilter)
  );

  renderTable(indexTableWrap, rows, [
    { key: "corp_name", label: "회사명" },
    { key: "idx_cl_nm", label: "지표분류" },
    { key: "idx_code", label: "지표코드" },
    { key: "idx_nm", label: "지표명" },
    { key: "idx_val", label: "값" },
    { key: "stlm_dt", label: "결산일" },
  ]);
}

function renderRawJson() {
  rawJsonEl.textContent = state.lastResult ? JSON.stringify(state.lastResult, null, 2) : "검색 결과가 여기에 표시됩니다.";
}

function renderAll() {
  if (!state.lastResult) {
    overviewPanel.innerHTML = '<div class="empty-state">검색 결과가 여기에 표시됩니다.</div>';
    renderSingleAndMulti();
    renderIndexTable();
    renderRawJson();
    return;
  }

  buildOverview(state.lastResult);
  renderSingleAndMulti();
  renderIndexTable();
  renderRawJson();
}

async function submitSearch(event) {
  event.preventDefault();

  const query = queryInput.value.trim();
  const bsnsYear = document.getElementById("bsns-year").value;
  const reprtCode = document.getElementById("reprt-code").value;
  const idxCodes = collectIdxCodes();

  if (!query) {
    setStatus("기업명을 먼저 입력해주세요.");
    return;
  }

  if (!idxCodes.length) {
    setStatus("최소 하나의 지표 분류를 선택해주세요.");
    return;
  }

  setStatus("OpenDART 데이터를 조회하는 중입니다...");
  setRequestLabel();

  const searchParams = new URLSearchParams({
    query,
    bsns_year: bsnsYear,
    reprt_code: reprtCode,
    idx_cl_codes: idxCodes.join(","),
  });

  try {
    const response = await fetch(`/api/company-data?${searchParams.toString()}`);
    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.error || "조회에 실패했습니다.");
    }

    state.lastResult = payload;
    state.selectedCompanies = payload.selected_companies || [];
    companyText.textContent =
      state.selectedCompanies.length > 1
        ? `${state.selectedCompanies.length}개 회사 선택`
        : `${payload.selected_company.corp_name} (${payload.selected_company.stock_code || payload.selected_company.corp_code})`;
    setStatus("조회가 완료되었습니다.");
    downloadButton.disabled = false;
    renderAll();
  } catch (error) {
    state.lastResult = null;
    state.selectedCompanies = [];
    downloadButton.disabled = true;
    overviewPanel.innerHTML = `<div class="error-box">${escapeHtml(error.message)}</div>`;
    singleTableWrap.innerHTML = '<div class="empty-state">검색 결과가 없습니다.</div>';
    multiTableWrap.innerHTML = '<div class="empty-state">검색 결과가 없습니다.</div>';
    indexTableWrap.innerHTML = '<div class="empty-state">검색 결과가 없습니다.</div>';
    rawJsonEl.textContent = "검색 결과가 여기에 표시됩니다.";
    companyText.textContent = "-";
    setStatus(error.message);
  }
}

function downloadJson() {
  if (!state.lastResult) return;

  const blob = new Blob([JSON.stringify(state.lastResult, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const companyName =
    (state.lastResult.selected_companies || []).length > 1
      ? `${state.lastResult.selected_companies.length}companies`
      : state.lastResult.selected_company?.corp_name || "company";
  const year = state.lastResult.request?.bsns_year || "year";
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${companyName}_${year}_opendart.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function bindTabs() {
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tab-button").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.remove("active"));
      button.classList.add("active");
      document.getElementById(`tab-${button.dataset.tab}`).classList.add("active");
    });
  });
}

function bindSuggestionEvents() {
  queryInput.addEventListener("input", () => {
    state.selectedCompanies = [];

    window.clearTimeout(suggestionTimer);
    suggestionTimer = window.setTimeout(fetchSuggestions, 180);
  });

  suggestionsEl.addEventListener("click", (event) => {
    const button = event.target.closest(".suggestion-item");
    if (!button) return;

    selectSuggestion({
      corp_name: button.dataset.corpName,
      corp_code: button.dataset.corpCode,
      stock_code: button.dataset.stockCode,
    });
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".field-group")) {
      renderSuggestions([]);
    }
  });
}

function bindFilters() {
  filters.single.addEventListener("input", renderSingleAndMulti);
  filters.multi.addEventListener("input", renderSingleAndMulti);
  filters.index.addEventListener("input", renderIndexTable);
}

form.addEventListener("submit", submitSearch);
downloadButton.addEventListener("click", downloadJson);
document.getElementById("bsns-year").addEventListener("change", setRequestLabel);
document.getElementById("reprt-code").addEventListener("change", setRequestLabel);

bindTabs();
bindSuggestionEvents();
bindFilters();
setRequestLabel();
renderAll();
