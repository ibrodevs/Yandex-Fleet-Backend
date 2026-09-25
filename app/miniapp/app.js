(() => {
  const tg = window.Telegram?.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
  }

  const state = {
    data: null,
    source: "all",
    status: "incoming",
    tariff: "all",
  };

  const $ = (id) => document.getElementById(id);
  const money = (value) => `${Math.round(Number(value || 0))} сом`;

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function sourceClass(source) {
    return `source-${source}`;
  }

  function filteredOrders() {
    if (!state.data) return [];
    return state.data.orders.filter((order) => {
      if (state.source !== "all" && order.source !== state.source) return false;
      if (state.status !== "all" && order.status !== state.status) return false;
      if (state.tariff !== "all" && order.tariff !== state.tariff) return false;
      return true;
    });
  }

  function renderHeader() {
    const driver = state.data.driver;
    $("driverName").textContent = driver.full_name || "Водитель";
    $("driverCar").textContent = driver.car || "Автомобиль не указан";

    const summary = state.data.summary;
    $("incomingCount").textContent = summary.incoming_count;
    $("averagePrice").textContent = money(summary.average_incoming_price);
    $("exactCount").textContent = summary.exact_price_count;
    $("priceDisclaimer").textContent = state.data.price_disclaimer;
  }

  function renderOrders() {
    const orders = filteredOrders();
    $("emptyState").classList.toggle("hidden", orders.length !== 0);
    $("ordersList").innerHTML = orders.map((order) => {
      const price = order.price_is_estimated
        ? `≈ ${money(order.price)}`
        : money(order.price);
      const caption = order.price_is_estimated
        ? "примерный расчёт"
        : "цена агрегатора";

      return `
        <button class="order-card" data-order-id="${escapeHtml(order.id)}">
          <div class="order-top">
            <div class="badges">
              <span class="badge ${sourceClass(order.source)}">${escapeHtml(order.source_title)}</span>
              <span class="badge">${escapeHtml(order.tariff_title)}</span>
              <span class="badge">${escapeHtml(order.status_title)}</span>
            </div>
            <div>
              <div class="order-price">${price}</div>
              <div class="price-caption">${caption}</div>
            </div>
          </div>
          <div class="route">
            <div class="route-dots"><span class="dot"></span><span class="dot end"></span></div>
            <div class="route-text">
              <div>${escapeHtml(order.pickup_address)}</div>
              <div>${escapeHtml(order.destination_address)}</div>
            </div>
          </div>
          <div class="order-meta">
            <span>📍 ${order.distance_km} км</span>
            <span>⏱ ~${order.duration_minutes} мин</span>
            <span>${order.payment_method === "cash" ? "💵 Наличные" : "💳 Карта"}</span>
          </div>
        </button>
      `;
    }).join("");

    document.querySelectorAll(".order-card").forEach((card) => {
      card.addEventListener("click", () => openOrder(card.dataset.orderId));
    });
  }

  function renderStats() {
    const s = state.data.summary;
    const labels = { fasten: "Fasten", yandex: "Яндекс", vezet: "Везёт" };
    $("statsPanel").innerHTML = `
      <div class="stat-row"><span>Новых заказов</span><strong>${s.incoming_count}</strong></div>
      <div class="stat-row"><span>Принято</span><strong>${s.accepted_count}</strong></div>
      <div class="stat-row"><span>Средняя входящая цена</span><strong>${money(s.average_incoming_price)}</strong></div>
      <div class="stat-row"><span>Точная цена</span><strong>${s.exact_price_count}</strong></div>
      <div class="stat-row"><span>Расчётная цена</span><strong>${s.estimated_price_count}</strong></div>
      ${Object.entries(s.by_source).map(([key, value]) =>
        `<div class="stat-row"><span>${labels[key]}</span><strong>${value}</strong></div>`
      ).join("")}
    `;
  }

  function renderProfile() {
    const d = state.data.driver;
    const v = d.vehicle || {};
    $("profileCard").innerHTML = `
      <div class="profile-hero">
        <h2>${escapeHtml(d.full_name || "Водитель")}</h2>
        <p>${escapeHtml(d.phone || "")}</p>
      </div>
      <div class="profile-row"><span>Статус</span><strong>${escapeHtml(d.work_rule || d.status || "—")}</strong></div>
      <div class="profile-row"><span>Рейтинг</span><strong>⭐ ${escapeHtml(d.rating ?? "—")}</strong></div>
      <div class="profile-row"><span>Приоритет</span><strong>${escapeHtml(d.priority_points ?? "—")}</strong></div>
      <div class="profile-row"><span>Баланс</span><strong>${money(d.balance)}</strong></div>
      <div class="profile-row"><span>Автомобиль</span><strong>${escapeHtml([v.brand, v.model].filter(Boolean).join(" ") || "—")}</strong></div>
      <div class="profile-row"><span>Госномер</span><strong>${escapeHtml(v.plate || "—")}</strong></div>
      <div class="profile-row"><span>Тарифы</span><strong>${escapeHtml((d.tariffs || []).join(", ") || "—")}</strong></div>
    `;
  }

  function openOrder(orderId) {
    const order = state.data.orders.find((item) => item.id === orderId);
    if (!order) return;

    const price = order.price_is_estimated
      ? `≈ ${money(order.price)}`
      : money(order.price);
    const priceKind = order.price_is_estimated
      ? "Примерный расчёт"
      : "Цена агрегатора";

    $("sheetContent").innerHTML = `
      <div class="sheet-title">
        <div class="badges">
          <span class="badge ${sourceClass(order.source)}">${escapeHtml(order.source_title)}</span>
          <span class="badge">${escapeHtml(order.tariff_title)}</span>
        </div>
        <h2>${price}</h2>
        <p class="muted">${priceKind}</p>
      </div>
      <div class="sheet-route">
        <strong>Откуда</strong>
        <p>${escapeHtml(order.pickup_address)}</p>
        <br />
        <strong>Куда</strong>
        <p>${escapeHtml(order.destination_address)}</p>
      </div>
      <div class="sheet-grid">
        <div class="sheet-metric"><span>Расстояние</span><strong>${order.distance_km} км</strong></div>
        <div class="sheet-metric"><span>Время</span><strong>~${order.duration_minutes} мин</strong></div>
        <div class="sheet-metric"><span>Оплата</span><strong>${order.payment_method === "cash" ? "Наличные" : "Карта"}</strong></div>
        <div class="sheet-metric"><span>Статус</span><strong>${escapeHtml(order.status_title)}</strong></div>
      </div>
      ${order.price_is_estimated ? '<p class="disclaimer">Эта сумма рассчитана тестовой моделью. После подключения реального источника приоритет будет у цены, которую отдаёт агрегатор.</p>' : ""}
    `;
    $("sheetBackdrop").classList.remove("hidden");
    tg?.HapticFeedback?.impactOccurred("light");
  }

  function closeSheet() {
    $("sheetBackdrop").classList.add("hidden");
  }

  async function load() {
    $("refreshButton").classList.add("loading");
    try {
      const initData = tg?.initData || "";
      const demo = !initData;
      const response = await fetch(`/api/v1/miniapp/bootstrap?demo=${demo}`, {
        headers: initData ? { "X-Telegram-Init-Data": initData } : {},
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${response.status}`);
      }
      state.data = await response.json();
      renderHeader();
      renderOrders();
      renderStats();
      renderProfile();
    } catch (error) {
      showToast(error.message || "Не удалось загрузить приложение");
    } finally {
      $("refreshButton").classList.remove("loading");
    }
  }

  function showToast(message) {
    const toast = $("toast");
    toast.textContent = message;
    toast.classList.remove("hidden");
    setTimeout(() => toast.classList.add("hidden"), 2800);
  }

  document.querySelectorAll("[data-source]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-source]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      state.source = button.dataset.source;
      renderOrders();
    });
  });

  $("statusFilter").addEventListener("change", (event) => {
    state.status = event.target.value;
    renderOrders();
  });
  $("tariffFilter").addEventListener("change", (event) => {
    state.tariff = event.target.value;
    renderOrders();
  });
  $("refreshButton").addEventListener("click", load);
  $("sheetClose").addEventListener("click", closeSheet);
  $("sheetBackdrop").addEventListener("click", (event) => {
    if (event.target === $("sheetBackdrop")) closeSheet();
  });

  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
      button.classList.add("active");
      $(button.dataset.view).classList.add("active");
      tg?.HapticFeedback?.selectionChanged();
    });
  });

  load();
  setInterval(load, 15000);
})();
