# Fleet Hub

Flutter driver app and native Android overlay. Setup, Firebase, backend, build and acceptance checklist: [MOBILE_SETUP.md](../../docs/MOBILE_SETUP.md).

```bash
flutter pub get
flutter analyze
flutter test
flutter run
```

Requires the `/api/v1/mobile` backend routes from this repository and owner-supplied Firebase configuration for sign-in and notifications. No demo sign-in or production mock orders.
