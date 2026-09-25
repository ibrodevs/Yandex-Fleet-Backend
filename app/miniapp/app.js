(() => {
  const tg = window.Telegram?.WebApp;
  const state = {
    data: null,
    source: "all",
    status: "incoming",
    tariff: "all",
  };

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

  function setTheme() {
    const telegramTheme = tg?.colorScheme;
    const dark = telegramTheme
      ? telegramTheme === "dark"
      : window.matchMedia?.("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  }

  function statusPillClass(status) {
    if (status === "active") return "pill-info";
    if (status === "completed") return "pill-success";
    if (status === "incoming" || status === "waiting") return "pill-warning";
    if (status === "cancelled") return "pill-neutral";
    return "pill-info";
  }

  function paymentLabel(method) {
    return method === "cash" ? "Наличные" : "Карта";
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
    $("driverCar").textContent = driver.car || "Автомобиль не указан";

    const summary = state.data.summary;
    $("incomingCount").textContent = summary.incoming_count;
    $("averagePrice").textContent = money(summary.average_incoming_price);
    $("activeCount").textContent = summary.active_count;
    $("priceDisclaimer").textContent = state.data.price_disclaimer;
  }

  function renderOrders() {
    const headings = {
      incoming: ["Поступающие заказы", "Fasten, Яндекс и Везёт в одной ленте"],
      active: ["Активный заказ", "Текущий заказ водителя"],
      completed: ["Завершённые заказы", "История завершённых поездок"],
      all: ["Все заказы", "Все статусы в одной ленте"],
    };
    const [title, subtitle] = headings[state.status] || headings.all;
    $("ordersSectionTitle").textContent = title;
    $("ordersSectionSubtitle").textContent = subtitle;

    const orders = filteredOrders();
    $("emptyState").classList.toggle("hidden", orders.length !== 0);

    $("ordersList").innerHTML = orders.map((order) => {
      const price = order.price_is_estimated
        ? `≈ ${money(order.price)}`
        : money(order.price);
      const caption = order.price_is_estimated
        ? "Ориентировочный расчёт"
        : "Цена агрегатора";
      const paymentIcon = order.payment_method === "cash" ? "cash" : "card";
      const acceptButton = order.can_accept
        ? `
          <button class="btn btn-primary order-accept-btn" type="button" data-order-id="${escapeHtml(order.id)}">
            ${icon("check")}
            <span>Принять заказ</span>
          </button>
        `
        : "";
      const completeButton = order.can_complete
        ? `
          <button class="btn btn-success order-complete-btn" type="button" data-order-id="${escapeHtml(order.id)}">
            ${icon("check")}
            <span>Завершить заказ</span>
          </button>
        `
        : "";

      return `
        <article class="order-card" data-order-id="${escapeHtml(order.id)}">
          <div class="order-head">
            <div class="order-tags">
              <span class="pill pill-source">${escapeHtml(order.source_title)}</span>
              <span class="pill pill-neutral">${escapeHtml(order.tariff_title)}</span>
              <span class="pill ${statusPillClass(order.status)}">${escapeHtml(order.status_title)}</span>
            </div>
            <div class="price-block">
              <div class="order-price">${price}</div>
              <div class="price-caption">${caption}</div>
            </div>
          </div>

          <div class="route-list">
            <div class="route-row">
              ${icon("pin")}
              <div>
                <strong>Откуда</strong>
                <span>${escapeHtml(order.pickup_address)}</span>
              </div>
            </div>
            <div class="route-row">
              ${icon("flag")}
              <div>
                <strong>Куда</strong>
                <span>${escapeHtml(order.destination_address)}</span>
              </div>
            </div>
          </div>

          <div class="order-meta">
            <span class="meta-item">${icon("route")} ${escapeHtml(order.distance_km)} км</span>
            <span class="meta-item">${icon("clock")} ~${escapeHtml(order.duration_minutes)} мин</span>
            <span class="meta-item">${icon(paymentIcon)} ${paymentLabel(order.payment_method)}</span>
          </div>

          <div class="order-actions">
            <button class="btn btn-secondary order-details-btn" type="button" data-order-id="${escapeHtml(order.id)}">
              <span>Подробнее</span>
              ${icon("chevron")}
            </button>
            ${acceptButton}
            ${completeButton}
          </div>
        </article>
      `;
    }).join("");

    document.querySelectorAll(".order-details-btn").forEach((button) => {
      button.addEventListener("click", () => openOrder(button.dataset.orderId));
    });

    document.querySelectorAll(".order-accept-btn").forEach((button) => {
      button.addEventListener("click", async () => {
        await acceptOrder(button.dataset.orderId, button);
      });
    });

    document.querySelectorAll(".order-complete-btn").forEach((button) => {
      button.addEventListener("click", async () => {
        await completeOrder(button.dataset.orderId, button);
      });
    });
  }

  function statRow(iconName, title, value) {
    return `
      <div class="stat-row">
        <span class="stat-label">${icon(iconName)} ${escapeHtml(title)}</span>
        <strong>${escapeHtml(value)}</strong>
      </div>
    `;
  }

  function renderStats() {
    const s = state.data.summary;
    const labels = { fasten: "Fasten", yandex: "Яндекс", vezet: "Везёт" };

    $("statsPanel").innerHTML = [
      statRow("orders", "Новых заказов", s.incoming_count),
      statRow("check", "Активных", s.active_count),
      statRow("check", "Завершено", s.completed_count),
      statRow("trending", "Средняя входящая цена", money(s.average_incoming_price)),
      statRow("card", "Точная цена", s.exact_price_count),
      statRow("calculator", "Расчётная цена", s.estimated_price_count),
      ...Object.entries(s.by_source).map(([key, value]) =>
        statRow("orders", labels[key], value)
      ),
    ].join("");
  }

  function profileRow(iconName, title, value) {
    return `
      <div class="profile-row">
        <span class="profile-label">${icon(iconName)} ${escapeHtml(title)}</span>
        <strong>${escapeHtml(value)}</strong>
      </div>
    `;
  }

  function renderProfile() {
    const d = state.data.driver;
    const v = d.vehicle || {};
    const car = [v.brand, v.model].filter(Boolean).join(" ") || "—";

    $("profileCard").innerHTML = `
      <div class="profile-hero">
        <div class="profile-avatar">${icon("user")}</div>
        <div>
          <h2>${escapeHtml(d.full_name || "Водитель")}</h2>
          <p>${escapeHtml(d.phone || "")}</p>
        </div>
      </div>
      ${profileRow("shield", "Статус", d.work_rule || d.status || "—")}
      ${profileRow("star", "Рейтинг", d.rating ?? "—")}
      ${profileRow("trending", "Приоритет", d.priority_points ?? "—")}
      ${profileRow("card", "Баланс", money(d.balance))}
      ${profileRow("car", "Автомобиль", car)}
      ${profileRow("car", "Госномер", v.plate || "—")}
      ${profileRow("orders", "Тарифы", (d.tariffs || []).join(", ") || "—")}
    `;
  }

  function apiRequestContext() {
    const initData = tg?.initData || "";
    return {
      demo: !initData,
      headers: initData ? { "X-Telegram-Init-Data": initData } : {},
    };
  }

  async function confirmAccept() {
    if (tg?.showConfirm) {
      return await new Promise((resolve) => {
        tg.showConfirm("Принять этот заказ?", resolve);
      });
    }
    return window.confirm("Принять этот заказ?");
  }

  async function acceptOrder(orderId, button = null) {
    const order = state.data?.orders.find((item) => item.id === orderId);
    if (!order || !order.can_accept) return;

    const confirmed = await confirmAccept();
    if (!confirmed) return;

    if (button) {
      button.disabled = true;
      button.classList.add("loading");
    }

    try {
      const { demo, headers } = apiRequestContext();
      const response = await fetch(
        `/api/v1/miniapp/orders/${encodeURIComponent(orderId)}/accept?demo=${demo}`,
        {
          method: "POST",
          headers,
          cache: "no-store",
        },
      );

      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(body.detail || `HTTP ${response.status}`);
      }

      state.data.orders = state.data.orders.map((item) =>
        item.id === orderId ? body.order : item
      );
      state.data.summary = body.summary;
      state.status = "active";
      $("statusFilter").value = "active";

      renderHeader();
      renderOrders();
      renderStats();
      closeSheet();
      showToast("Заказ принят и стал активным");
      tg?.HapticFeedback?.notificationOccurred("success");
    } catch (error) {
      showToast(error.message || "Не удалось принять заказ");
      tg?.HapticFeedback?.notificationOccurred("error");
    } finally {
      if (button?.isConnected) {
        button.disabled = false;
        button.classList.remove("loading");
      }
    }
  }

  async function confirmComplete() {
    if (tg?.showConfirm) {
      return await new Promise((resolve) => {
        tg.showConfirm("Завершить этот заказ?", resolve);
      });
    }
    return window.confirm("Завершить этот заказ?");
  }

  async function completeOrder(orderId, button = null) {
    const order = state.data?.orders.find((item) => item.id === orderId);
    if (!order || !order.can_complete) return;

    const confirmed = await confirmComplete();
    if (!confirmed) return;

    if (button) {
      button.disabled = true;
      button.classList.add("loading");
    }

    try {
      const { demo, headers } = apiRequestContext();
      const response = await fetch(
        `/api/v1/miniapp/orders/${encodeURIComponent(orderId)}/complete?demo=${demo}`,
        {
          method: "POST",
          headers,
          cache: "no-store",
        },
      );

      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(body.detail || `HTTP ${response.status}`);
      }

      state.data.orders = state.data.orders.map((item) =>
        item.id === orderId ? body.order : item
      );
      state.data.summary = body.summary;
      state.status = "completed";
      $("statusFilter").value = "completed";

      renderHeader();
      renderOrders();
      renderStats();
      closeSheet();
      showToast("Заказ завершён");
      tg?.HapticFeedback?.notificationOccurred("success");
    } catch (error) {
      showToast(error.message || "Не удалось завершить заказ");
      tg?.HapticFeedback?.notificationOccurred("error");
    } finally {
      if (button?.isConnected) {
        button.disabled = false;
        button.classList.remove("loading");
      }
    }
  }

  function openOrder(orderId) {
    const order = state.data.orders.find((item) => item.id === orderId);
    if (!order) return;

    const price = order.price_is_estimated
      ? `≈ ${money(order.price)}`
      : money(order.price);
    const priceKind = order.price_is_estimated
      ? "Ориентировочный расчёт"
      : "Цена агрегатора";
    const paymentIcon = order.payment_method === "cash" ? "cash" : "card";

    const calculation = order.price_is_estimated && order.price_calculation
      ? `
        <section class="sheet-section">
          <div class="sheet-section-title">Расчёт цены</div>
          <div class="calc-line"><span>Базовая часть</span><strong>${money(order.price_calculation.base)}</strong></div>
          <div class="calc-line"><span>Расстояние</span><strong>${money(order.price_calculation.distance_part)}</strong></div>
          <div class="calc-line"><span>Время</span><strong>${money(order.price_calculation.time_part)}</strong></div>
          <div class="calc-line"><span>Коэффициент</span><strong>× ${escapeHtml(order.price_calculation.demand_multiplier)}</strong></div>
          <p class="disclaimer">Это демонстрационный расчёт. После подключения реального источника приоритет будет у цены, которую отдаёт агрегатор.</p>
        </section>
      `
      : "";

    const acceptAction = order.can_accept
      ? `
        <div class="sheet-actions">
          <button class="btn btn-primary btn-large sheet-accept-btn" type="button" data-order-id="${escapeHtml(order.id)}">
            ${icon("check")}
            <span>Принять заказ</span>
          </button>
        </div>
      `
      : "";
    const completeAction = order.can_complete
      ? `
        <div class="sheet-actions">
          <button class="btn btn-success btn-large sheet-complete-btn" type="button" data-order-id="${escapeHtml(order.id)}">
            ${icon("check")}
            <span>Завершить заказ</span>
          </button>
        </div>
      `
      : "";

    $("sheetContent").innerHTML = `
      <div class="sheet-title">
        <div class="order-tags">
          <span class="pill pill-source">${escapeHtml(order.source_title)}</span>
          <span class="pill pill-neutral">${escapeHtml(order.tariff_title)}</span>
          <span class="pill ${statusPillClass(order.status)}">${escapeHtml(order.status_title)}</span>
        </div>
        <h2>${price}</h2>
        <p>${priceKind}</p>
      </div>

      <section class="sheet-section">
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
      </section>

      <div class="sheet-grid">
        <div class="sheet-metric"><span>Расстояние</span><strong>${escapeHtml(order.distance_km)} км</strong></div>
        <div class="sheet-metric"><span>Время</span><strong>~${escapeHtml(order.duration_minutes)} мин</strong></div>
        <div class="sheet-metric"><span>Оплата</span><strong>${icon(paymentIcon)} ${paymentLabel(order.payment_method)}</strong></div>
        <div class="sheet-metric"><span>Статус</span><strong>${escapeHtml(order.status_title)}</strong></div>
      </div>

      ${calculation}
      ${acceptAction}
      ${completeAction}
    `;

    const sheetAccept = document.querySelector(".sheet-accept-btn");
    if (sheetAccept) {
      sheetAccept.addEventListener("click", async () => {
        await acceptOrder(sheetAccept.dataset.orderId, sheetAccept);
      });
    }

    const sheetComplete = document.querySelector(".sheet-complete-btn");
    if (sheetComplete) {
      sheetComplete.addEventListener("click", async () => {
        await completeOrder(sheetComplete.dataset.orderId, sheetComplete);
      });
    }

    $("sheetBackdrop").classList.remove("hidden");
    tg?.HapticFeedback?.impactOccurred("light");
  }

  function closeSheet() {
    $("sheetBackdrop").classList.add("hidden");
  }

  function showToast(message) {
    const toast = $("toast");
    toast.textContent = message;
    toast.classList.remove("hidden");
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => toast.classList.add("hidden"), 2800);
  }

  async function load() {
    $("refreshButton").classList.add("loading");
    try {
      const { demo, headers } = apiRequestContext();
      const response = await fetch(`/api/v1/miniapp/bootstrap?demo=${demo}`, {
        headers,
        cache: "no-store",
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

  function activateView(button) {
    document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
    button.classList.add("active");
    $(button.dataset.view).classList.add("active");
    $("pageTitle").textContent = button.dataset.title || "Fleet Hub";
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
    button.addEventListener("click", () => activateView(button));
  });

  load();
  window.setInterval(load, 15000);
})();
