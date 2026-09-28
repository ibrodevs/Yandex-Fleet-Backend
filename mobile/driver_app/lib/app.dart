import 'dart:io';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'core/api.dart';
import 'core/models.dart';
import 'core/phone_login.dart';
import 'core/state.dart';

const lime = Color(0xFFD8F36A);

class FleetApp extends StatefulWidget {
  final AppState state;
  const FleetApp({super.key, required this.state});
  @override
  State<FleetApp> createState() => _FleetAppState();
}

class _FleetAppState extends State<FleetApp> {
  late final router = GoRouter(
    refreshListenable: widget.state,
    redirect: (context, state) {
      if (!widget.state.ready) {
        return state.uri.path == '/loading' ? null : '/loading';
      }
      if (!widget.state.signedIn) {
        return state.uri.path == '/login' ? null : '/login';
      }
      return ['/login', '/loading'].contains(state.uri.path) ? '/' : null;
    },
    routes: [
      GoRoute(
        path: '/loading',
        builder: (_, _) =>
            const Scaffold(body: Center(child: CircularProgressIndicator())),
      ),
      GoRoute(
        path: '/login',
        builder: (_, _) => LoginScreen(state: widget.state),
      ),
      GoRoute(
        path: '/',
        builder: (_, _) => Dashboard(state: widget.state),
      ),
      GoRoute(
        path: '/orders/:id',
        builder: (_, s) =>
            OrderDetails(state: widget.state, id: s.pathParameters['id']!),
      ),
    ],
  );
  @override
  void initState() {
    super.initState();
    widget.state.openOrder = (id) {
      if (widget.state.signedIn) {
        router.go('/orders/${Uri.encodeComponent(id)}');
      }
    };
  }

  ThemeData theme(Brightness b) => ThemeData(
    useMaterial3: true,
    brightness: b,
    scaffoldBackgroundColor: b == Brightness.dark
        ? const Color(0xFF101412)
        : const Color(0xFFF4F5F0),
    colorScheme: ColorScheme.fromSeed(
      seedColor: const Color(0xFF567327),
      brightness: b,
      primary: b == Brightness.dark ? lime : const Color(0xFF344A16),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: Colors.transparent,
      elevation: 0,
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 14),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(18),
        borderSide: BorderSide.none,
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(56),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      ),
    ),
  );
  @override
  Widget build(BuildContext context) => MaterialApp.router(
    title: 'Fleet Hub',
    debugShowCheckedModeBanner: false,
    theme: theme(Brightness.light),
    darkTheme: theme(Brightness.dark),
    routerConfig: router,
  );
}

class LoginScreen extends StatefulWidget {
  final AppState state;
  const LoginScreen({super.key, required this.state});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final phone = TextEditingController(), code = TextEditingController();
  late final PhoneLoginController login;
  String? get verification => login.verificationId;
  String? get error => login.error;
  bool get sending => login.busy;

  @override
  void initState() {
    super.initState();
    login = PhoneLoginController(
      gateway: FirebasePhoneAuthGateway(),
      exchangeToken: widget.state.loginWithFirebaseToken,
    )..addListener(_changed);
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    login.removeListener(_changed);
    login.dispose();
    phone.dispose();
    code.dispose();
    super.dispose();
  }

  Future<void> submit() => verification != null || login.numberVerified
      ? login.submitCode(code.text)
      : login.request(phone.text);

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480),
          child: ListView(
            padding: const EdgeInsets.all(28),
            shrinkWrap: true,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: lime,
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: const Icon(
                      Icons.local_taxi_rounded,
                      color: Colors.black,
                      size: 32,
                    ),
                  ),
                  const SizedBox(width: 14),
                  const Text(
                    'fleet hub',
                    style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800),
                  ),
                ],
              ),
              const SizedBox(height: 64),
              const Text(
                'Ваша смена.\nВсё под контролем.',
                style: TextStyle(
                  fontSize: 38,
                  fontWeight: FontWeight.w800,
                  height: 1.12,
                ),
              ),
              const SizedBox(height: 18),
              const Text(
                'Заказы, баланс и автомобиль вашего парка — в одном приложении.',
                style: TextStyle(fontSize: 17, height: 1.5),
              ),
              const SizedBox(height: 38),
              Text(
                verification == null ? 'Вход по номеру телефона' : 'Код из SMS',
                style: const TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                key: ValueKey(verification == null ? 'phone' : 'sms-code'),
                enabled: !sending && !login.numberVerified,
                controller: verification == null ? phone : code,
                keyboardType: verification == null
                    ? TextInputType.phone
                    : TextInputType.number,
                autofillHints: verification == null
                    ? const [AutofillHints.telephoneNumber]
                    : const [AutofillHints.oneTimeCode],
                decoration: InputDecoration(
                  hintText: verification == null
                      ? '+996 ___ ___ ___'
                      : 'Введите код',
                  prefixIcon: Icon(
                    verification == null
                        ? Icons.phone_outlined
                        : Icons.lock_outline,
                  ),
                ),
              ),
              const SizedBox(height: 18),
              if (error != null)
                Text(
                  error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              if (!widget.state.firebaseReady)
                const Padding(
                  padding: EdgeInsets.only(bottom: 16),
                  child: Text(
                    'Вход станет доступен после подключения Firebase владельцем парка.',
                  ),
                ),
              FilledButton(
                onPressed: sending || !widget.state.firebaseReady
                    ? null
                    : submit,
                child: Text(
                  sending
                      ? 'Подождите…'
                      : login.numberVerified
                      ? 'Повторить вход'
                      : verification == null
                      ? 'Получить код'
                      : 'Войти',
                ),
              ),
              if (verification != null)
                TextButton(
                  onPressed: sending
                      ? null
                      : () {
                          code.clear();
                          login.changePhone();
                        },
                  child: const Text('Изменить номер'),
                ),
              if (verification != null && !login.numberVerified)
                TextButton(
                  onPressed: sending
                      ? null
                      : () {
                          code.clear();
                          login.request(phone.text, resend: true);
                        },
                  child: const Text('Запросить код повторно'),
                ),
              const SizedBox(height: 22),
              const Text(
                'Используйте номер вашего таксопарка. Номер передаётся Firebase для подтверждения и защиты от спама.',
                style: TextStyle(fontSize: 12, height: 1.5),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

class Dashboard extends StatefulWidget {
  final AppState state;
  const Dashboard({super.key, required this.state});
  @override
  State<Dashboard> createState() => _DashboardState();
}

class _DashboardState extends State<Dashboard> with WidgetsBindingObserver {
  int tab = 0;
  bool history = false;
  AppState get s => widget.state;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      s.refresh();
    }
  }

  Future<void> action(Future<void> Function() task) async {
    try {
      await task();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(errorMessage(e))));
      }
    }
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: s,
    builder: (context, _) => Scaffold(
      appBar: AppBar(
        title: const Text(
          'fleet hub',
          style: TextStyle(fontWeight: FontWeight.w800, letterSpacing: -1),
        ),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 20),
            child: Chip(
              avatar: Icon(
                Icons.circle,
                size: 9,
                color: s.driverMode ? Colors.green : Colors.grey,
              ),
              label: Text(s.driverMode ? 'На линии' : 'Вне смены'),
            ),
          ),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: (v) => setState(() => tab = v),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.grid_view_rounded),
            label: 'Главная',
          ),
          NavigationDestination(
            icon: Icon(Icons.route_outlined),
            label: 'Заказы',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline),
            label: 'Профиль',
          ),
          NavigationDestination(
            icon: Icon(Icons.tune_rounded),
            label: 'Настройки',
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          await s.refresh();
          await s.registerPush();
        },
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 14, 20, 28),
          children: [
            if (s.api.offline)
              const Card(
                child: ListTile(
                  leading: Icon(Icons.wifi_off),
                  title: Text('Нет подключения'),
                  subtitle: Text('Показаны последние сохранённые данные'),
                ),
              ),
            if (s.error != null)
              Card(
                child: ListTile(
                  title: Text(s.error!),
                  trailing: IconButton(
                    onPressed: s.refresh,
                    icon: const Icon(Icons.refresh),
                  ),
                ),
              ),
            ...switch (tab) {
              0 => home(),
              1 => orderList(),
              2 => profile(),
              _ => preferences(),
            },
          ],
        ),
      ),
    ),
  );
  Widget title(String text) => Padding(
    padding: const EdgeInsets.only(bottom: 20),
    child: Text(
      text,
      style: const TextStyle(
        fontSize: 30,
        fontWeight: FontWeight.w800,
        letterSpacing: -.7,
      ),
    ),
  );
  List<Widget> home() => [
    const Text(
      'ХОРОШЕЙ ДОРОГИ',
      style: TextStyle(
        fontSize: 11,
        fontWeight: FontWeight.w700,
        letterSpacing: 2,
      ),
    ),
    const SizedBox(height: 8),
    title('Здравствуйте, ${value(s.driver['first_name'])}'),
    Container(
      padding: const EdgeInsets.all(24),
      margin: const EdgeInsets.only(bottom: 18),
      decoration: BoxDecoration(
        color: const Color(0xFF202C23),
        borderRadius: BorderRadius.circular(26),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Баланс парка',
                style: TextStyle(color: Colors.white70, fontSize: 15),
              ),
              Icon(Icons.account_balance_wallet_outlined, color: lime),
            ],
          ),
          const SizedBox(height: 24),
          Text(
            '${value(s.driver['balance'])} ${value(s.driver['currency'])}',
            style: const TextStyle(
              fontSize: 38,
              fontWeight: FontWeight.w800,
              color: Colors.white,
            ),
          ),
          const SizedBox(height: 22),
          const Text(
            'Яндекс Fleet  ↗',
            style: TextStyle(color: lime, fontSize: 13),
          ),
        ],
      ),
    ),
    Card(
      child: ListTile(
        contentPadding: const EdgeInsets.all(18),
        leading: const Icon(Icons.directions_car_outlined, size: 34),
        title: Text(value(s.driver['car'])),
        subtitle: Text((s.driver['tariffs'] as List? ?? []).join(' · ')),
      ),
    ),
    const SizedBox(height: 12),
    const Text(
      'Активный заказ',
      style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
    ),
    const SizedBox(height: 16),
    if (s.orders.where((o) => o.active).isEmpty)
      empty(
        'Сейчас активных заказов нет',
        'Новые заказы появятся после передачи данных из Яндекс Fleet.',
      )
    else
      ...s.orders.where((o) => o.active).map((o) => OrderCard(order: o)),
    const Text(
      'Данные официального API Яндекс Fleet.',
      style: TextStyle(fontSize: 12, color: Colors.grey),
    ),
  ];
  List<Widget> orderList() {
    final items = s.orders
        .where((o) => history ? o.history : o.active)
        .toList();
    return [
      title('Ваши заказы'),
      SegmentedButton<bool>(
        segments: const [
          ButtonSegment(value: false, label: Text('Активные')),
          ButtonSegment(value: true, label: Text('История')),
        ],
        selected: {history},
        onSelectionChanged: (v) => setState(() => history = v.first),
      ),
      const SizedBox(height: 22),
      if (items.isEmpty)
        empty('Заказов пока нет', 'Потяните вниз, чтобы обновить данные.')
      else
        ...items.map((o) => OrderCard(order: o)),
    ];
  }

  List<Widget> profile() => [
    title('Профиль'),
    Card(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            const CircleAvatar(
              radius: 36,
              backgroundColor: lime,
              child: Icon(Icons.person_outline, size: 40, color: Colors.black),
            ),
            const SizedBox(height: 16),
            Text(
              value(s.driver['full_name']),
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
            ),
            Text(value(s.driver['phone'])),
          ],
        ),
      ),
    ),
    info('Статус водителя', s.driver['status']),
    info('Тарифы', (s.driver['tariffs'] as List? ?? []).join(' · ')),
    const SizedBox(height: 20),
    title('Автомобиль'),
    info(
      'Марка и модель',
      '${value(s.vehicle['brand'])} ${value(s.vehicle['model'])}',
    ),
    info('Госномер', s.vehicle['plate']),
    info('Цвет', s.vehicle['color']),
    info('Год', s.vehicle['year']),
    const SizedBox(height: 18),
    OutlinedButton(
      onPressed: () => action(s.logout),
      child: const Text('Выйти из аккаунта'),
    ),
  ];
  Widget info(String label, Object? text) => Card(
    child: ListTile(
      title: Text(
        label,
        style: const TextStyle(fontSize: 13, color: Colors.grey),
      ),
      subtitle: Text(
        value(text),
        style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600),
      ),
    ),
  );
  List<Widget> preferences() => [
    title('Настройки'),
    if (Platform.isAndroid) ...[
      Card(
        child: SwitchListTile(
          title: const Text('Режим водителя'),
          subtitle: const Text('Ожидать новые заказы во время смены'),
          value: s.driverMode,
          onChanged: (v) => action(() => s.setMode(v)),
        ),
      ),
      const SizedBox(height: 12),
      const Text(
        'Виджет заказов',
        style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
      ),
      const SizedBox(height: 16),
      OutlinedButton.icon(
        onPressed: () => action(() async {
          await overlayChannel.invokeMethod('requestOverlayPermission');
        }),
        icon: const Icon(Icons.layers_outlined),
        label: const Text('Разрешить поверх приложений'),
      ),
    ],
    ...{
          'overlay_enabled': 'Показывать поверх приложений',
          'notifications': 'Уведомления',
          'sound': 'Звук',
          'vibration': 'Вибрация',
          'auto_hide': 'Автоматически скрывать',
          'show_price': 'Показывать цену',
          'show_address': 'Показывать адрес',
          'show_tariff': 'Показывать тариф',
          'show_distance': 'Показывать расстояние',
        }.entries
        .where(
          (e) =>
              Platform.isAndroid || ['notifications', 'sound'].contains(e.key),
        )
        .map(
          (e) => Card(
            child: SwitchListTile(
              title: Text(e.value),
              value: s.settings.data[e.key] as bool,
              onChanged: (v) =>
                  action(() => s.saveSettings(s.settings.copy(e.key, v))),
            ),
          ),
        ),
    if (Platform.isAndroid) ...[
      Card(
        child: ListTile(
          title: const Text('Время показа'),
          trailing: DropdownButton<int>(
            value: s.settings.data['display_seconds'],
            items: [5, 10, 15, 30]
                .map((v) => DropdownMenuItem(value: v, child: Text('$v сек')))
                .toList(),
            onChanged: (v) => action(
              () => s.saveSettings(s.settings.copy('display_seconds', v)),
            ),
          ),
        ),
      ),
      Card(
        child: Column(
          children: [
            ListTile(
              title: const Text('Прозрачность'),
              trailing: Text('${s.settings.data['transparency']}%'),
            ),
            Slider(
              value: (s.settings.data['transparency'] as num).toDouble(),
              min: 0,
              max: 80,
              divisions: 8,
              onChanged: (v) => action(
                () =>
                    s.saveSettings(s.settings.copy('transparency', v.round())),
              ),
            ),
          ],
        ),
      ),
      FilledButton.icon(
        onPressed: () => action(() async {
          await overlayChannel.invokeMethod('showTestOverlay');
        }),
        icon: const Icon(Icons.layers),
        label: const Text('Проверить виджет'),
      ),
    ],
    const SizedBox(height: 22),
    const Text(
      'Оформление следует теме устройства.\nFleet Hub · 1.0',
      textAlign: TextAlign.center,
      style: TextStyle(color: Colors.grey, fontSize: 12),
    ),
  ];
  Widget empty(String heading, String subtitle) => Card(
    child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 34),
      child: Column(
        children: [
          const Icon(Icons.route_rounded, size: 44, color: Colors.grey),
          const SizedBox(height: 16),
          Text(
            heading,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          Text(
            subtitle,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.grey, height: 1.5),
          ),
        ],
      ),
    ),
  );
}

class OrderCard extends StatelessWidget {
  final FleetOrder order;
  final bool tappable;
  const OrderCard({super.key, required this.order, this.tappable = true});
  @override
  Widget build(BuildContext context) => Card(
    child: InkWell(
      borderRadius: BorderRadius.circular(24),
      onTap: tappable
          ? () => context.push('/orders/${Uri.encodeComponent(order.id)}')
          : null,
      child: Padding(
        padding: const EdgeInsets.all(22),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    order.tariff,
                    style: const TextStyle(
                      fontSize: 21,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                Chip(
                  label: Text(
                    order.statusTitle,
                    style: const TextStyle(fontSize: 11),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            route('А', order.pickup, lime),
            const Padding(
              padding: EdgeInsets.only(left: 14),
              child: Text('┊', style: TextStyle(color: Colors.grey)),
            ),
            route('Б', order.destination, const Color(0xFFE3E7E1)),
            const SizedBox(height: 22),
            const Divider(),
            const SizedBox(height: 10),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  order.price,
                  style: const TextStyle(
                    fontSize: 26,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                Text(order.payment),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              '${value(order.data['distance_km'])} км  ·  ${value(order.data['duration_minutes'])} мин  ·  Яндекс',
              style: const TextStyle(color: Colors.grey, fontSize: 12),
            ),
          ],
        ),
      ),
    ),
  );
  Widget route(String mark, String address, Color color) => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Container(
        width: 28,
        height: 28,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(9),
        ),
        child: Text(
          mark,
          style: const TextStyle(
            color: Colors.black,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
      const SizedBox(width: 12),
      Expanded(
        child: Text(address, style: const TextStyle(fontSize: 16, height: 1.5)),
      ),
    ],
  );
}

class OrderDetails extends StatefulWidget {
  final AppState state;
  final String id;
  const OrderDetails({super.key, required this.state, required this.id});
  @override
  State<OrderDetails> createState() => _OrderDetailsState();
}

class _OrderDetailsState extends State<OrderDetails> {
  late Future<dynamic> result = widget.state.api.get(
    '/orders/${Uri.encodeComponent(widget.id)}',
  );
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Детали заказа'),
      leading: IconButton(
        icon: const Icon(Icons.arrow_back),
        onPressed: () => context.go('/'),
      ),
    ),
    body: FutureBuilder(
      future: result,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(errorMessage(snapshot.error!)),
                TextButton(
                  onPressed: () => setState(
                    () => result = widget.state.api.get(
                      '/orders/${Uri.encodeComponent(widget.id)}',
                    ),
                  ),
                  child: const Text('Повторить'),
                ),
              ],
            ),
          );
        }
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        return ListView(
          padding: const EdgeInsets.all(20),
          children: [
            OrderCard(
              order: FleetOrder(Map<String, dynamic>.from(snapshot.data)),
              tappable: false,
            ),
            const Text(
              'Управление поездкой доступно в Яндекс Про.',
              style: TextStyle(color: Colors.grey),
            ),
          ],
        );
      },
    ),
  );
}
