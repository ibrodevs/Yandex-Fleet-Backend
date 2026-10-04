import 'dart:convert';

String value(Object? v) =>
    v == null || v.toString().isEmpty ? '—' : v.toString();

class FleetOrder {
  final Map<String, dynamic> data;
  FleetOrder(this.data);
  String get id => data['id']?.toString() ?? data['order_id']?.toString() ?? '';
  String get status => value(data['status']);
  bool get active => {'assigned', 'waiting', 'in_progress'}.contains(status);
  bool get history => {'completed', 'cancelled'}.contains(status);
  String get tariff => value(data['tariff_title'] ?? data['tariff']);
  String get pickup => value(data['pickup_address'] ?? data['pickup']);
  String get destination =>
      value(data['destination_address'] ?? data['destination']);
  String get price {
    if (data['price'] == null) return '—';
    final currency = switch (data['currency']) {
      'RUB' => '₽',
      'KGS' => 'сом',
      final String raw => raw,
      _ => '',
    };
    return '${value(data['price'])} $currency'.trim();
  }

  String get payment => switch (data['payment_method']) {
    'card' => 'Карта',
    'cashless' => 'Безнал',
    'cash' => 'Наличные',
    'corporate' => 'Корпоративная',
    'corp' => 'Корпоративная',
    'prepaid' => 'Предоплата',
    'internal' => 'Внутренняя',
    _ => value(data['payment_method']),
  };
  String get statusTitle => value(
    data['status_title'] ??
        const {
          'assigned': 'Назначен',
          'waiting': 'Ожидание',
          'in_progress': 'В поездке',
          'completed': 'Завершён',
          'cancelled': 'Отменён',
        }[status],
  );
  static FleetOrder? fromPush(Map<String, dynamic> data) {
    try {
      final payload = data['payload'] is String
          ? jsonDecode(data['payload'])
          : data;
      final order = FleetOrder(Map<String, dynamic>.from(payload));
      return order.id.isEmpty ? null : order;
    } catch (_) {
      return null;
    }
  }
}

class OverlaySettings {
  final Map<String, dynamic> data;
  OverlaySettings([Map<String, dynamic> values = const {}])
    : data = {...defaults, ...values};
  static const defaults = <String, dynamic>{
    'overlay_enabled': true,
    'notifications': true,
    'sound': true,
    'vibration': true,
    'auto_hide': true,
    'display_seconds': 15,
    'transparency': 0,
    'show_price': true,
    'show_address': true,
    'show_tariff': true,
    'show_distance': true,
  };
  OverlaySettings copy(String key, dynamic value) =>
      OverlaySettings({...data, key: value});
}
