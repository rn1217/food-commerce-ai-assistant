// 화면은 기존 API만 호출한다. DB 비밀번호나 API 키는 브라우저로 보내지 않는다.
const modes = {
  products: {
    endpoint: "/api/recommendations", title: "어떤 상품을 찾으세요?",
    description: "가격, 선물용, 포장 조건으로 찾아보세요.",
    label: "원하는 상품 조건", button: "조건에 맞는 상품 찾기",
    placeholder: "부모님 선물인데 너무 달지 않고 개별포장된 제품을 찾고 있어요.",
    note: "가격·선물 여부·개별포장 포함/제외·당도를 해석합니다. 가성비는 판매가격이 낮은 순서로 안내하며, 해석된 조건을 결과에서 확인해 주세요.",
    examples: [["담백한 선물", "너무 달지 않고 개별포장된 선물 추천해줘"], ["가성비 상품", "가성비 있는 상품을 추천해줘 제일 싼 상품도 포함해서"], ["2만원 이하", "2만원 이하 상품 중 개별포장은 제외해줘"]],
  },
  faq: {
    endpoint: "/api/faq/search", title: "무엇이 궁금하세요?",
    description: "배송·보관·주문 등 등록된 안내를 찾아보세요.",
    label: "궁금한 내용", button: "관련 FAQ 찾기",
    placeholder: "배송비는 얼마인가요?",
    note: "관련 FAQ를 근거로 AI가 답변합니다. 근거가 부족하면 안내하고, 생성 실패 시 원문을 보여드립니다. 출처도 함께 확인해 주세요.",
    examples: [["배송비", "배송비는 얼마인가요?"], ["해동 방법", "냉동 떡 해동 방법 알려줘"], ["주문 취소", "주문을 취소하고 싶어요"]],
  },
};
let currentMode = "products";
let busy = false;
const drafts = { products: "", faq: "" };
const savedResults = { products: null, faq: null };
const $ = (id) => document.getElementById(id);
const form = $("search-form");
const input = $("query");
const content = $("results-content");

// API와 사용자 입력은 innerHTML로 삽입하지 않고 textContent로 출력한다.
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function emptyState(title, description, symbol = "↗") {
  const box = element("div", "empty-state");
  const icon = element("div", "empty-symbol", symbol);
  icon.setAttribute("aria-hidden", "true");
  box.append(icon, element("strong", "", title), element("p", "", description));
  content.replaceChildren(box);
}

function clearMeta() {
  $("condition-tags").replaceChildren();
  $("request-details").hidden = true;
  $("request-details").open = false;
  $("request-id").textContent = "";
  $("result-status").classList.remove("error");
}

function showInitial() {
  clearMeta();
  $("results-title").textContent = currentMode === "products" ? "당신의 조건을 기다리고 있어요" : "궁금한 점, 근거에서 찾아볼게요";
  $("result-status").textContent = "질문을 입력하거나 예시를 골라 검색해 보세요.";
  $("result-count").textContent = "READY WHEN YOU ARE";
  emptyState(currentMode === "products" ? "작은 조건이 좋은 선택이 됩니다" : "등록된 안내를 한곳에서", currentMode === "products" ? "선물 여부, 포장 방식, 당도를 기준으로 등록된 상품만 찾아드립니다." : "배송부터 보관까지, 관련 FAQ 원문과 출처를 함께 확인하세요.");
}

function setMode(mode) {
  if (busy) return;
  drafts[currentMode] = input.value;
  currentMode = mode;
  const config = modes[mode];
  for (const name of Object.keys(modes)) {
    const button = $(`mode-${name}`);
    button.classList.toggle("active", name === mode);
    button.setAttribute("aria-pressed", String(name === mode));
  }
  $("form-title").textContent = config.title;
  $("form-description").textContent = config.description;
  $("query-label").textContent = config.label;
  $("scope-note").textContent = config.note;
  $("submit-label").textContent = config.button;
  input.placeholder = config.placeholder;
  input.value = drafts[mode];
  $("input-error").hidden = true;
  input.removeAttribute("aria-invalid");
  updateCount();
  $("example-buttons").replaceChildren(...config.examples.map(([label, query]) => {
    const button = element("button", "example-button", label);
    button.type = "button";
    button.addEventListener("click", () => {
      input.value = query;
      updateCount();
      $("input-error").hidden = true;
      input.removeAttribute("aria-invalid");
      input.focus();
    });
    return button;
  }));
  if (savedResults[mode]) renderResults(savedResults[mode]);
  else showInitial();
}

function updateCount() { $("char-count").textContent = `${input.value.length} / 500`; }

function setBusy(value) {
  busy = value;
  $("results-area").setAttribute("aria-busy", String(value));
  input.disabled = value;
  document.querySelectorAll(".mode-button, .example-button, #submit-button").forEach(button => { button.disabled = value; });
  $("submit-label").textContent = value ? "찾고 있어요…" : modes[currentMode].button;
}

function showRequestId(id) {
  if (!id) return;
  $("request-id").textContent = id;
  $("request-details").hidden = false;
}

function renderProducts(data) {
  const products = data.products || [];
  $("results-title").textContent = products.length ? "이런 상품은 어떠세요?" : "조건을 조금 바꿔볼까요?";
  $("result-count").textContent = `${products.length} PRODUCTS`;
  $("result-status").textContent = data.message;
  const conditions = data.conditions || {};
  const tags = [];
  if (conditions.gift_only) tags.push("선물 가능");
  if (conditions.individual_only) tags.push("개별포장");
  if (conditions.exclude_individual) tags.push("개별포장 제외");
  if (conditions.max_sweetness != null) tags.push(`당도 ${conditions.max_sweetness} 이하`);
  if (conditions.min_price != null) tags.push(`${Number(conditions.min_price).toLocaleString("ko-KR")}원 이상`);
  if (conditions.max_price != null) tags.push(`${Number(conditions.max_price).toLocaleString("ko-KR")}원 이하`);
  if (conditions.sort === "price_asc") tags.push("가격 낮은 순");
  if (conditions.sort === "price_desc") tags.push("가격 높은 순");
  if (conditions.include_cheapest) tags.push("조건 내 최저가 포함");
  $("condition-tags").replaceChildren(...tags.map(text => element("span", "tag", text)));
  if (!products.length) {
    emptyState("추천할 상품이 없습니다", "위 안내를 확인하고 가격·선물·포장·당도 조건을 바꿔보세요.", "–");
    return;
  }
  const grid = element("div", "product-grid");
  const storage = {room: "실온 보관", refrigerated: "냉장 보관", frozen: "냉동 보관"};
  for (const product of products) {
    const card = element("article", "product-card");
    const top = element("div", "product-top");
    top.append(element("span", "category-badge", product.category), element("span", "product-id", `NO. ${String(product.product_id).padStart(2, "0")}`));
    const price = element("div", "price", Number(product.price).toLocaleString("ko-KR"));
    price.append(element("span", "", "원"));
    const meta = element("div", "product-tags");
    const labels = [`당도 ${product.sweetness}/5`, product.packaging === "individual" ? "개별포장" : "묶음포장", storage[product.storage_method] || product.storage_method];
    if (product.gift_available) labels.push("선물 가능");
    meta.append(...labels.map(text => element("span", "tag", text)));
    card.append(top, element("h3", "", product.name), element("p", "product-description", product.description), price, meta);
    if (product.recommendation_reason) {
      const reason = element("div", "recommendation-reason");
      reason.append(element("strong", "", "AI 추천 이유"), element("p", "", product.recommendation_reason));
      card.append(reason);
    }
    grid.append(card);
  }
  content.replaceChildren(grid);
}

function renderFaq(data) {
  const matches = data.matches || [];
  const titles = { matched: "관련된 안내를 찾았어요", needs_clarification: "어떤 내용이 궁금하신가요?", no_match: "아직 등록된 안내가 없어요", insufficient_evidence: "질문에 답할 근거가 부족해요" };
  $("results-title").textContent = titles[data.status] || "FAQ 검색 결과";
  $("result-count").textContent = `${matches.length} SOURCES`;
  $("result-status").textContent = data.message;
  if (!matches.length) {
    emptyState("답변 근거를 찾지 못했습니다", "배송비, 주문 취소, 보관 방법처럼 질문을 구체적으로 바꿔보세요.", "?");
    return;
  }
  const list = element("div", "faq-list");
  if (data.mode === "generated" && data.answer) {
    const answer = element("article", "faq-card recommendation-reason");
    answer.append(element("h3", "", "AI FAQ 답변"), element("p", "faq-answer", data.answer));
    const sources = element("div", "faq-meta");
    sources.append(element("span", "", "답변 출처: "));
    for (const source of data.sources || []) {
      const faq = matches.find(item => item.source === source);
      if (!faq) continue;
      const link = element("a", "faq-source faq-source-link", `원문 보기 · ${source}`);
      link.href = `#faq-${faq.faq_id}`;
      link.addEventListener("click", (event) => {
        const target = document.getElementById(`faq-${faq.faq_id}`);
        if (!target) return;
        event.preventDefault();
        // 이미 화면 안에 있는 원문도 선택됐음을 알 수 있게 강조하고 초점을 옮긴다.
        list.querySelectorAll(".source-selected").forEach(node => node.classList.remove("source-selected"));
        target.classList.add("source-selected");
        target.focus({preventScroll: true});
        target.scrollIntoView({behavior: "auto", block: "center"});
      });
      sources.append(link);
    }
    answer.append(sources);
    list.append(answer);
  }
  if (data.notice) list.append(element("p", "muted", data.notice));
  for (const faq of matches) {
    const card = element("article", "faq-card");
    card.id = `faq-${faq.faq_id}`;
    card.tabIndex = -1;
    const meta = element("div", "faq-meta");
    meta.append(element("span", "faq-category", faq.category), element("span", "faq-source", `FAQ 원문 · ${faq.source}`));
    card.append(meta, element("h3", "", faq.question), element("p", "faq-answer", faq.answer));
    list.append(card);
  }
  content.replaceChildren(list);
}

function renderResults(data) {
  clearMeta();
  if (currentMode === "products") renderProducts(data);
  else renderFaq(data);
  showRequestId(data.request_id);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;
  const query = input.value.trim();
  if (!query || query.length > 500) {
    $("input-error").textContent = "공백을 제외한 질문을 1~500자로 입력해 주세요.";
    $("input-error").hidden = false;
    input.setAttribute("aria-invalid", "true");
    input.focus();
    return;
  }
  $("input-error").hidden = true;
  input.removeAttribute("aria-invalid");
  savedResults[currentMode] = null;
  clearMeta();
  setBusy(true);
  $("results-title").textContent = "등록된 정보를 확인하고 있어요";
  $("result-status").textContent = "잠시만 기다려 주세요.";
  $("result-count").textContent = "SEARCHING";
  const loading = element("div", "loading-state");
  loading.append(element("span", "spinner"), element("span", "", "조건에 맞는 근거를 찾는 중입니다."));
  content.replaceChildren(loading);
  const controller = new AbortController();
  // 브라우저 대기만 중단한다. 서버에서 시작된 처리/로그 저장이 취소되는 것은 아니다.
  // 조건 해석과 이유 생성의 순차 호출을 기다린다. 서버의 작업 취소는 아니다.
  const timeout = setTimeout(() => controller.abort(), currentMode === "faq" ? 60000 : 120000);
  try {
    const response = await fetch(modes[currentMode].endpoint, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({query}), signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) {
      const message = typeof data.detail === "string" ? data.detail : "입력 내용을 확인한 뒤 다시 시도해 주세요.";
      const error = new Error(message);
      error.requestId = response.headers.get("X-Request-ID");
      throw error;
    }
    savedResults[currentMode] = data;
    renderResults(data);
  } catch (error) {
    $("results-title").textContent = "잠시 연결을 확인해 주세요";
    $("result-count").textContent = "TRY AGAIN";
    $("result-status").classList.add("error");
    $("result-status").textContent = error.name === "AbortError"
      ? "응답 대기 시간이 길어졌습니다. 서버 상태를 확인한 뒤 다시 시도해 주세요."
      : error instanceof TypeError || error instanceof SyntaxError
        ? "서버에 연결하지 못했습니다. 서버 실행 상태를 확인해 주세요."
        : error.message;
    emptyState("검색을 완료하지 못했습니다", "입력한 질문은 그대로 유지됩니다. 연결을 확인한 후 검색 버튼을 다시 눌러주세요.", "!");
    showRequestId(error.requestId);
  } finally {
    clearTimeout(timeout);
    setBusy(false);
  }
});

input.addEventListener("input", () => {
  updateCount();
  $("input-error").hidden = true;
  input.removeAttribute("aria-invalid");
});
$("mode-products").addEventListener("click", () => setMode("products"));
$("mode-faq").addEventListener("click", () => setMode("faq"));
setMode("products");
