(() => {
  "use strict";

  // State
  const tg = window.Telegram?.WebApp;
  const state = {
    data: null,
    source: "all",
    status: "incoming",
    tariff: "all",
    actionVersion: 0,
    loadSequence: 0,
  };

  // Utilities
  const $ = (id) => document.getElementById(id);
  const money = (value) => `${Math.round(Number(value || 0))} сом`;

  function icon(name, className = "icon") {
    return `<svg class="${className}" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function paymentLabel(method) {
    return method === "cash" ? "Наличные" : "Карта";
  }

  function priceDetails(order) {
    return {
      value: order.price_is_estimated ? `≈ ${money(order.price)}` : money(order.price),
      caption: order.price_is_estimated ? "Ориентировочная цена" : "Цена агрегатора",
    };
  }

  function statusPillClass(status) {
    if (status === "active") return "pill-info";
    if (status === "completed") return "pill-success";
    if (status === "incoming" || status === "waiting") return "pill-warning";
    return "pill-neutral";
  }

  function apiRequestContext() {
    const initData = tg?.initData || "";
    return {
      demo: !initData,
      headers: initData ? { "X-Telegram-Init-Data": initData } : {},
    };
  }

  function filteredOrders() {
    if (!state.data) return [];
    return state.data.orders.filter((order) => {
      if (state.source !== "all" && order.source !== state.source) return false;
      if (state.status !== "all" && order.status !== state.status) return false;
      if (state.tariff !== "all" && order.tariff !== state.tariff) return false;
      return order.status !== "active";
    });
  }

  // Telegram and theme
  function setTheme() {
    const dark = tg?.colorScheme
      ? tg.colorScheme === "dark"
      : window.matchMedia?.("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    document.querySelector('meta[name="theme-color"]')?.setAttribute(
      "content",
      dark ? "#000000" : "#F5F5F7",
    );
  }

  function confirmAction(message) {
    if (tg?.initData && tg?.showConfirm) {
      return new Promise((resolve) => tg.showConfirm(message, resolve));
    }
    return Promise.resolve(window.confirm(message));
  }

  function haptic(type) {
    tg?.HapticFeedback?.notificationOccurred(type);
  }

  // Reusable order markup
  function routeMarkup(order) {
    return `
      <div class="route-list">
        <div class="route-row">
          ${icon("pin")}
          <div><strong>Откуда</strong><span>${escapeHtml(order.pickup_address)}</span></div>
        </div>
        <div class="route-row">
          ${icon("flag")}
          <div><strong>Куда</strong><span>${escapeHtml(order.destination_address)}</span></div>
        </div>
      </div>
    `;
  }

  function metaMarkup(order) {
    const paymentIcon = order.payment_method === "cash" ? "cash" : "card";
    return `
      <div class="order-meta">
        <span class="meta-item">${icon("route")} ${escapeHtml(order.distance_km)} км</span>
        <span class="meta-item">${icon("clock")} ~${escapeHtml(order.duration_minutes)} мин</span>
        <span class="meta-item">${icon(paymentIcon)} ${paymentLabel(order.payment_method)}</span>
      </div>
    `;
  }

  function actionMarkup(order) {
    const accept = order.can_accept
      ? `<button class="btn btn-primary order-accept-btn" type="button" data-order-id="${escapeHtml(order.id)}">${icon("check")}<span>Принять заказ</span></button>`
      : "";
    const complete = order.can_complete
      ? `<button class="btn btn-primary order-complete-btn" type="button" data-order-id="${escapeHtml(order.id)}">${icon("check")}<span>Завершить заказ</span></button>`
      : "";

    return `
      <div class="order-actions">
        <button class="btn btn-secondary order-details-btn" type="button" data-order-id="${escapeHtml(order.id)}">
          <span>Подробнее</span>${icon("chevron")}
        </button>
        ${accept}${complete}
      </div>
    `;
  }

  function orderCardMarkup(order, active = false) {
    const price = priceDetails(order);
    return `
      <article class="${active ? "active-order-card" : "order-card"}" data-order-id="${escapeHtml(order.id)}">
        <div class="order-head">
          <div class="order-tags">
            <span class="pill pill-source">${escapeHtml(order.source_title)}</span>
            <span class="pill pill-neutral">${escapeHtml(order.tariff_title)}</span>
            <span class="pill ${statusPillClass(order.status)}">${escapeHtml(order.status_title)}</span>
          </div>
          <div class="price-block">
            <div class="order-price">${price.value}</div>
            <div class="price-caption">${price.caption}</div>
          </div>
        </div>
        ${routeMarkup(order)}
        ${metaMarkup(order)}
        ${actionMarkup(order)}
      </article>
    `;
  }

  function bindOrderActions(root = document) {
    root.querySelectorAll(".order-details-btn").forEach((button) => {
      button.addEventListener("click", () => openOrder(button.dataset.orderId));
    });
    root.querySelectorAll(".order-accept-btn").forEach((button) => {
      button.addEventListener("click", () => acceptOrder(button.dataset.orderId, button));
    });
    root.querySelectorAll(".order-complete-btn").forEach((button) => {
      button.addEventListener("click", () => completeOrder(button.dataset.orderId, button));
    });
  }

  // Rendering
  function renderHeader() {
    const { driver, summary } = state.data;
    $("driverCar").textContent = (driver.car || "Автомобиль не указан").replace(" • ", " · ");
    $("incomingCount").textContent = summary.incoming_count;
    $("activeCount").textContent = summary.active_count;
    $("averagePrice").textContent = money(summary.average_incoming_price);
    $("priceDisclaimer").textContent = state.data.price_disclaimer;
  }

  function renderActiveOrder() {
    const activeOrder = state.data.orders.find((order) => order.status === "active");
    $("activeOrderSection").classList.toggle("hidden", !activeOrder);
    $("activeOrderContent").innerHTML = activeOrder ? orderCardMarkup(activeOrder, true) : "";
    if (activeOrder) bindOrderActions($("activeOrderContent"));
  }

  function renderOrders() {
    const headings = {
      incoming: ["Поступающие заказы", "Новые предложения для водителя"],
      active: ["Активные заказы", "Текущий заказ показан выше"],
      completed: ["Завершённые заказы", "Недавние выполненные поездки"],
      all: ["Все заказы", "Вся доступная история заказов"],
    };
    const [title, subtitle] = headings[state.status] || headings.all;
    $("ordersSectionTitle").textContent = title;
    $("ordersSectionSubtitle").textContent = subtitle;

    const orders = filteredOrders();
    $("ordersList").innerHTML = orders.map((order) => orderCardMarkup(order)).join("");
    $("emptyState").classList.toggle("hidden", orders.length !== 0);
    const emptyCopy = $("emptyState").querySelector("span:last-child");
    if (emptyCopy) {
      emptyCopy.textContent = state.status === "active"
        ? "Текущий активный заказ находится в приоритетном блоке выше."
        : "Попробуйте изменить фильтры или обновить ленту.";
    }
    bindOrderActions($("ordersList"));
  }

  function settingRow(iconName, title, value) {
    return `<div class="setting-row"><span class="setting-label">${icon(iconName)}${escapeHtml(title)}</span><strong>${escapeHtml(value)}</strong></div>`;
  }

  function settingsGroup(title, rows) {
    return `<section><h3 class="settings-group-title">${escapeHtml(title)}</h3><div class="settings-card">${rows}</div></section>`;
  }

  function renderStats() {
    const s = state.data.summary;
    const labels = { fasten: "Fasten", yandex: "Яндекс", vezet: "Везёт" };
    $("statsPanel").innerHTML = [
      settingsGroup("Заказы", [
        settingRow("orders", "Новые", s.incoming_count),
        settingRow("route", "Активные", s.active_count),
        settingRow("check", "Завершённые", s.completed_count),
      ].join("")),
      settingsGroup("Цены", [
        settingRow("trending", "Средняя цена", money(s.average_incoming_price)),
        settingRow("card", "Точные цены", s.exact_price_count),
        settingRow("calculator", "Расчётные цены", s.estimated_price_count),
      ].join("")),
      settingsGroup("По агрегаторам", Object.entries(s.by_source).map(([key, value]) =>
        settingRow("orders", labels[key] || key, value)
      ).join("")),
    ].join("");
  }

  function renderProfile() {
    const d = state.data.driver;
    const v = d.vehicle || {};
    const car = [v.brand, v.model].filter(Boolean).join(" ") || "Автомобиль не указан";
    const vehicleDetails = [v.year, v.color].filter(Boolean).join(" · ");
    const tariffs = (d.tariffs || []).map((tariff) => `<span class="tariff-pill">${escapeHtml(tariff)}</span>`).join("") || `<span class="tariff-pill">Не указаны</span>`;

    $("profileCard").innerHTML = `
      <section class="settings-card profile-hero">
        <div class="profile-avatar">${icon("user")}</div>
        <div><h3>${escapeHtml(d.full_name || "Водитель")}</h3><p>${escapeHtml(d.phone || "")}</p></div>
      </section>
      ${settingsGroup("Водитель", [
        settingRow("star", "Рейтинг", d.rating ?? "—"),
        settingRow("trending", "Приоритет", d.priority_points ?? "—"),
        settingRow("card", "Баланс", money(d.balance)),
        settingRow("shield", "Статус", d.work_rule || d.status || "—"),
      ].join(""))}
      <section><h3 class="settings-group-title">Автомобиль</h3><div class="settings-card">
        <div class="vehicle-main"><strong>${escapeHtml(car)}</strong><span>${escapeHtml(vehicleDetails)}</span></div>
        ${settingRow("car", "Госномер", v.plate || "—")}
      </div></section>
      <section><h3 class="settings-group-title">Тарифы</h3><div class="settings-card tariff-list">${tariffs}</div></section>
    `;
  }

  function renderAll() {
    renderHeader();
    renderActiveOrder();
    renderOrders();
    renderStats();
    renderProfile();
  }

  // Order actions
  function setButtonLoading(button, loading) {
    if (!button) return;
    button.disabled = loading;
    button.classList.toggle("loading", loading);
  }

  function setStatusFilter(status) {
    state.status = status;
    document.querySelectorAll("[data-status]").forEach((button) => {
      button.classList.toggle("active", button.dataset.status === status);
    });
  }

  async function acceptOrder(orderId, button = null) {
    const order = state.data?.orders.find((item) => item.id === orderId);
    if (!order?.can_accept || !(await confirmAction("Принять этот заказ?"))) return;
    setButtonLoading(button, true);

    try {
      const { demo, headers } = apiRequestContext();
      const response = await fetch(`/api/v1/miniapp/orders/${encodeURIComponent(orderId)}/accept?demo=${demo}`, {
        method: "POST", headers, cache: "no-store",
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);

      state.actionVersion += 1;
      state.data.orders = state.data.orders.map((item) => item.id === orderId ? body.order : item);
      state.data.summary = body.summary;
      setStatusFilter("active");
      renderAll();
      closeSheet();
      showToast("Заказ принят");
      haptic("success");
      window.requestAnimationFrame(() => $("activeOrderSection").scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (error) {
      showToast(error.message || "Не удалось принять заказ");
      haptic("error");
    } finally {
      if (button?.isConnected) setButtonLoading(button, false);
    }
  }

  async function completeOrder(orderId, button = null) {
    const order = state.data?.orders.find((item) => item.id === orderId);
    if (!order?.can_complete || !(await confirmAction("Завершить этот заказ?"))) return;
    setButtonLoading(button, true);

    try {
      const { demo, headers } = apiRequestContext();
      const response = await fetch(`/api/v1/miniapp/orders/${encodeURIComponent(orderId)}/complete?demo=${demo}`, {
        method: "POST", headers, cache: "no-store",
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);

      state.actionVersion += 1;
      state.data.orders = state.data.orders.map((item) => item.id === orderId ? body.order : item);
      state.data.summary = body.summary;
      setStatusFilter("completed");
      renderAll();
      closeSheet();
      showToast("Заказ завершён");
      haptic("success");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (error) {
      showToast(error.message || "Не удалось завершить заказ");
      haptic("error");
    } finally {
      if (button?.isConnected) setButtonLoading(button, false);
    }
  }

  // Bottom sheet
  function openOrder(orderId) {
    const order = state.data.orders.find((item) => item.id === orderId);
    if (!order) return;
    const price = priceDetails(order);
    const paymentIcon = order.payment_method === "cash" ? "cash" : "card";
    const calculation = order.price_is_estimated && order.price_calculation
      ? `<section class="sheet-section"><div class="sheet-section-title">Расчёт цены</div>
          <div class="calc-line"><span>База</span><strong>${money(order.price_calculation.base)}</strong></div>
          <div class="calc-line"><span>Расстояние</span><strong>${money(order.price_calculation.distance_part)}</strong></div>
          <div class="calc-line"><span>Время</span><strong>${money(order.price_calculation.time_part)}</strong></div>
          <div class="calc-line"><span>Коэффициент</span><strong>×${escapeHtml(order.price_calculation.demand_multiplier)}</strong></div>
          <p class="disclaimer">Расчёт является ориентировочным. После подключения агрегатора будет использоваться его фактическая цена.</p>
        </section>`
      : "";
    const action = order.can_accept
      ? `<div class="sheet-actions"><button class="btn btn-primary btn-large sheet-accept-btn" type="button" data-order-id="${escapeHtml(order.id)}">${icon("check")}Принять заказ</button></div>`
      : order.can_complete
        ? `<div class="sheet-actions"><button class="btn btn-primary btn-large sheet-complete-btn" type="button" data-order-id="${escapeHtml(order.id)}">${icon("check")}Завершить заказ</button></div>`
        : "";

    $("sheetContent").innerHTML = `
      <div class="sheet-title">
        <div class="order-tags">
          <span class="pill pill-source">${escapeHtml(order.source_title)}</span>
          <span class="pill pill-neutral">${escapeHtml(order.tariff_title)}</span>
          <span class="pill ${statusPillClass(order.status)}">${escapeHtml(order.status_title)}</span>
        </div>
        <h2>${price.value}</h2><p>${price.caption}</p>
      </div>
      <section class="sheet-section"><div class="sheet-section-title">Маршрут</div>${routeMarkup(order)}</section>
      <div class="sheet-grid">
        <div class="sheet-metric"><span>Расстояние</span><strong>${escapeHtml(order.distance_km)} км</strong></div>
        <div class="sheet-metric"><span>Время</span><strong>~${escapeHtml(order.duration_minutes)} мин</strong></div>
        <div class="sheet-metric"><span>Оплата</span><strong>${icon(paymentIcon)}${paymentLabel(order.payment_method)}</strong></div>
        <div class="sheet-metric"><span>Статус</span><strong>${escapeHtml(order.status_title)}</strong></div>
      </div>
      ${calculation}${action}
    `;

    document.querySelector(".sheet-accept-btn")?.addEventListener("click", (event) => acceptOrder(orderId, event.currentTarget));
    document.querySelector(".sheet-complete-btn")?.addEventListener("click", (event) => completeOrder(orderId, event.currentTarget));
    $("sheetBackdrop").classList.remove("hidden");
    document.body.style.overflow = "hidden";
    $("sheetClose").focus({ preventScroll: true });
    tg?.HapticFeedback?.impactOccurred("light");
  }

  function closeSheet() {
    $("sheetBackdrop").classList.add("hidden");
    document.body.style.overflow = "";
  }

  function showToast(message) {
    const toast = $("toast");
    toast.textContent = message;
    toast.classList.remove("hidden");
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => toast.classList.add("hidden"), 2400);
  }

  // Data loading. Ignore any GET response that began before a successful action.
  async function load({ silent = false } = {}) {
    const sequence = ++state.loadSequence;
    const actionVersion = state.actionVersion;
    if (!silent) $("refreshButton").classList.add("loading");
    try {
      const { demo, headers } = apiRequestContext();
      const response = await fetch(`/api/v1/miniapp/bootstrap?demo=${demo}`, { headers, cache: "no-store" });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${response.status}`);
      }
      const payload = await response.json();
      if (sequence !== state.loadSequence || actionVersion !== state.actionVersion) return;
      state.data = payload;
      renderAll();
    } catch (error) {
      if (!silent) showToast(error.message || "Не удалось загрузить приложение");
    } finally {
      if (sequence === state.loadSequence) $("refreshButton").classList.remove("loading");
    }
  }

  // Events
  function activateView(button) {
    document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
    button.classList.add("active");
    $(button.dataset.view).classList.add("active");
    window.scrollTo({ top: 0, behavior: "smooth" });
    tg?.HapticFeedback?.selectionChanged();
  }

  setTheme();
  tg?.ready();
  tg?.expand();
  tg?.onEvent?.("themeChanged", setTheme);

  document.querySelectorAll("[data-source]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-source]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      state.source = button.dataset.source;
      renderOrders();
    });
  });
  document.querySelectorAll("[data-status]").forEach((button) => {
    button.addEventListener("click", () => {
      setStatusFilter(button.dataset.status);
      renderOrders();
    });
  });
  $("tariffFilter").addEventListener("change", (event) => {
    state.tariff = event.target.value;
    renderOrders();
  });
  $("refreshButton").addEventListener("click", () => load());
  $("sheetClose").addEventListener("click", closeSheet);
  $("sheetBackdrop").addEventListener("click", (event) => {
    if (event.target === $("sheetBackdrop")) closeSheet();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("sheetBackdrop").classList.contains("hidden")) closeSheet();
  });
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => activateView(button));
  });

  load();
  window.setInterval(() => load({ silent: true }), 15000);
})();
