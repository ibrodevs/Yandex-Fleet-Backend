(() => {
  const tg = window.Telegram?.WebApp;
  const state = {
    data: null,
    source: "all",
    status: "incoming",
    tariff: "all",
  };

  const $ = (id) => document.getElementById(id);
  const money = (value) => \`\${Math.round(Number(value || 0))} сом\`;

  function icon(name, className = "icon") {
    return \`<svg class="\${className}" aria-hidden="true"><use href="#i-\${name}"></use></svg>\`;
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
    if (status === "accepted" || status === "completed") return "pill-success";
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
    $("exactCount").textContent = summary.exact_price_count;
    $("priceDisclaimer").textContent = state.data.price_disclaimer;
  }

  function renderOrders() {
    const orders = filteredOrders();
    $("emptyState").classList.toggle("hidden", orders.length !== 0);

    $("ordersList").innerHTML = orders.map((order) => {
      const price = order.price_is_estimated
        ? \`≈ \${money(order.price)}\`
        : money(order.price);
      const caption = order.price_is_estimated
        ? "Ориентировочный расчёт"
        : "Цена агрегатора";
      const paymentIcon = order.payment_method === "cash" ? "cash" : "card";

      return \`
        <button class="order-card" type="button" data-order-id="\${escapeHtml(order.id)}">
          <div class="order-head">
            <div class="order-tags">
              <span class="pill pill-source">\${escapeHtml(order.source_title)}</span>
              <span class="pill pill-neutral">\${escapeHtml(order.tariff_title)}</span>
              <span class="pill \${statusPillClass(order.status)}">\${escapeHtml(order.status_title)}</span>
            </div>
            <div class="price-block">
              <div class="order-price">\${price}</div>
              <div class="price-caption">\${caption}</div>
            </div>
          </div>

          <div class="route-list">
            <div class="route-row">
              \${icon("pin")}
              <div>
                <strong>Откуда</strong>
                <span>\${escapeHtml(order.pickup_address)}</span>
              </div>
            </div>
            <div class="route-row">
              \${icon("flag")}
              <div>
                <strong>Куда</strong>
                <span>\${escapeHtml(order.destination_address)}</span>
              </div>
            </div>
          </div>

          <div class="order-meta">
            <span class="meta-item">\${icon("route")} \${escapeHtml(order.distance_km)} км</span>
            <span class="meta-item">\${icon("clock")} ~\${escapeHtml(order.duration_minutes)} мин</span>
            <span class="meta-item">\${icon(paymentIcon)} \${paymentLabel(order.payment_method)}</span>
          </div>
        </button>
      \`;
    }).join("");

    document.querySelectorAll(".order-card").forEach((card) => {
      card.addEventListener("click", () => openOrder(card.dataset.orderId));
    });
  }

  function statRow(iconName, title, value) {
    return \`
      <div class="stat-row">
        <span class="stat-label">\${icon(iconName)} \${escapeHtml(title)}</span>
        <strong>\${escapeHtml(value)}</strong>
      </div>
    \`;
  }

  function renderStats() {
    const s = state.data.summary;
    const labels = { fasten: "Fasten", yandex: "Яндекс", vezet: "Везёт" };

    $("statsPanel").innerHTML = [
      statRow("orders", "Новых заказов", s.incoming_count),
      statRow("check", "Принято", s.accepted_count),
      statRow("trending", "Средняя входящая цена", money(s.average_incoming_price)),
      statRow("card", "Точная цена", s.exact_price_count),
      statRow("calculator", "Расчётная цена", s.estimated_price_count),
      ...Object.entries(s.by_source).map(([key, value]) =>
        statRow("orders", labels[key], value)
      ),
    ].join("");
  }

  function profileRow(iconName, title, value) {
    return \`
      <div class="profile-row">
        <span class="profile-label">\${icon(iconName)} \${escapeHtml(title)}</span>
        <strong>\${escapeHtml(value)}</strong>
      </div>
    \`;
  }

  function renderProfile() {
    const d = state.data.driver;
    const v = d.vehicle || {};
    const car = [v.brand, v.model].filter(Boolean).join(" ") || "—";

    $("profileCard").innerHTML = \`
      <div class="profile-hero">
        <div class="profile-avatar">\${icon("user")}</div>
        <div>
          <h2>\${escapeHtml(d.full_name || "Водитель")}</h2>
          <p>\${escapeHtml(d.phone || "")}</p>
        </div>
      </div>
      \${profileRow("shield", "Статус", d.work_rule || d.status || "—")}
      \${profileRow("star", "Рейтинг", d.rating ?? "—")}
      \${profileRow("trending", "Приоритет", d.priority_points ?? "—")}
      \${profileRow("card", "Баланс", money(d.balance))}
      \${profileRow("car", "Автомобиль", car)}
      \${profileRow("car", "Госномер", v.plate || "—")}
      \${profileRow("orders", "Тарифы", (d.tariffs || []).join(", ") || "—")}
    \`;
  }

  function openOrder(orderId) {
    const order = state.data.orders.find((item) => item.id === orderId);
    if (!order) return;

    const price = order.price_is_estimated
      ? \`≈ \${money(order.price)}\`
      : money(order.price);
    const priceKind = order.price_is_estimated
      ? "Ориентировочный расчёт"
      : "Цена агрегатора";
    const paymentIcon = order.payment_method === "cash" ? "cash" : "card";

    const calculation = order.price_is_estimated && order.price_calculation
      ? \`
        <section class="sheet-section">
          <div class="sheet-section-title">Расчёт цены</div>
          <div class="calc-line"><span>Базовая часть</span><strong>\${money(order.price_calculation.base)}</strong></div>
          <div class="calc-line"><span>Расстояние</span><strong>\${money(order.price_calculation.distance_part)}</strong></div>
          <div class="calc-line"><span>Время</span><strong>\${money(order.price_calculation.time_part)}</strong></div>
          <div class="calc-line"><span>Коэффициент</span><strong>× \${escapeHtml(order.price_calculation.demand_multiplier)}</strong></div>
          <p class="disclaimer">Это демонстрационный расчёт. После подключения реального источника приоритет будет у цены, которую отдаёт агрегатор.</p>
        </section>
      \`
      : "";

    $("sheetContent").innerHTML = \`
      <div class="sheet-title">
        <div class="order-tags">
          <span class="pill pill-source">\${escapeHtml(order.source_title)}</span>
          <span class="pill pill-neutral">\${escapeHtml(order.tariff_title)}</span>
          <span class="pill \${statusPillClass(order.status)}">\${escapeHtml(order.status_title)}</span>
        </div>
        <h2>\${price}</h2>
        <p>\${priceKind}</p>
      </div>

      <section class="sheet-section">
        <div class="route-list">
          <div class="route-row">
            \${icon("pin")}
            <div><strong>Откуда</strong><span>\${escapeHtml(order.pickup_address)}</span></div>
          </div>
          <div class="route-row">
            \${icon("flag")}
            <div><strong>Куда</strong><span>\${escapeHtml(order.destination_address)}</span></div>
          </div>
        </div>
      </section>

      <div class="sheet-grid">
        <div class="sheet-metric"><span>Расстояние</span><strong>\${escapeHtml(order.distance_km)} км</strong></div>
        <div class="sheet-metric"><span>Время</span><strong>~\${escapeHtml(order.duration_minutes)} мин</strong></div>
        <div class="sheet-metric"><span>Оплата</span><strong>\${icon(paymentIcon)} \${paymentLabel(order.payment_method)}</strong></div>
        <div class="sheet-metric"><span>Статус</span><strong>\${escapeHtml(order.status_title)}</strong></div>
      </div>

      \${calculation}
    \`;

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
      const initData = tg?.initData || "";
      const demo = !initData;
      const response = await fetch(\`/api/v1/miniapp/bootstrap?demo=\${demo}\`, {
        headers: initData ? { "X-Telegram-Init-Data": initData } : {},
        cache: "no-store",
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || \`HTTP \${response.status}\`);
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
