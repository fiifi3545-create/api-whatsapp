import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'agora/agora_chat_session.dart';
import 'agora/agora_session.dart';
import 'agora/rtm_session.dart';
import 'api/client.dart';
import 'notifications/notifications_service.dart';
import 'screens/home_screen.dart';
import 'screens/phone_auth_screen.dart';
import 'state/app_config_state.dart';
import 'state/chat_state.dart';
import 'state/groups_state.dart';
import 'state/incoming_call_state.dart';
import 'state/presence_state.dart';
import 'state/session.dart';
import 'widgets/incoming_call_banner.dart';

class CompanionApp extends StatelessWidget {
  const CompanionApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        Provider<ApiClient>(
          create: (_) => ApiClient(),
          dispose: (_, c) => c.close(),
        ),
        Provider<AgoraSession>(
          create: (ctx) => AgoraSession(ctx.read<ApiClient>()),
          dispose: (_, s) => s.dispose(),
        ),
        Provider<AgoraChatSession>(
          create: (ctx) => AgoraChatSession(ctx.read<ApiClient>()),
          dispose: (_, s) => s.signOut(),
        ),
        Provider<RtmSession>(
          create: (ctx) => RtmSession(ctx.read<AgoraSession>()),
          dispose: (_, rtm) => rtm.signOut(),
        ),
        ChangeNotifierProvider<PresenceState>(
          create: (ctx) => PresenceState(ctx.read<RtmSession>()),
        ),
        ChangeNotifierProvider<IncomingCallState>(
          create: (_) => IncomingCallState(),
        ),
        ChangeNotifierProvider<Session>(
          create: (_) => Session()..load(),
        ),
        ChangeNotifierProxyProvider<ApiClient, GroupsState>(
          create: (ctx) => GroupsState(ctx.read<ApiClient>()),
          update: (_, api, prev) => prev ?? GroupsState(api),
        ),
        ChangeNotifierProxyProvider<ApiClient, AppConfigState>(
          create: (ctx) => AppConfigState(ctx.read<ApiClient>())..load(),
          update: (_, api, prev) => prev ?? (AppConfigState(api)..load()),
        ),
        ChangeNotifierProvider<ChatState>(
          create: (ctx) => ChatState(
            ctx.read<ApiClient>(),
            ctx.read<AgoraChatSession>(),
          ),
        ),
        Provider<NotificationsService>(
          create: (ctx) => NotificationsService(ctx.read<ApiClient>()),
        ),
      ],
      child: MaterialApp(
        title: 'Student Chatbot',
        debugShowCheckedModeBanner: false,
        theme: _buildTheme(Brightness.light),
        darkTheme: _buildTheme(Brightness.dark),
        home: const _Router(),
      ),
    );
  }

  ThemeData _buildTheme(Brightness brightness) {
    final scheme = brightness == Brightness.light
        ? const ColorScheme(
            brightness: Brightness.light,
            primary: Color(0xFF12609D),
            onPrimary: Color(0xFFFDFCF8),
            primaryContainer: Color(0xFFD3E4F2),
            onPrimaryContainer: Color(0xFF062A45),
            secondary: Color(0xFFF3A710),
            onSecondary: Color(0xFF020D15),
            secondaryContainer: Color(0xFFFBE4B4),
            onSecondaryContainer: Color(0xFF3D2900),
            tertiary: Color(0xFFFDA904),
            onTertiary: Color(0xFF020D15),
            tertiaryContainer: Color(0xFFFFE4A8),
            onTertiaryContainer: Color(0xFF402A00),
            error: Color(0xFFBF2612),
            onError: Color(0xFFFDFCF8),
            errorContainer: Color(0xFFF9D9D3),
            onErrorContainer: Color(0xFF410904),
            surface: Color(0xFFFDFCF8),
            onSurface: Color(0xFF020D15),
            surfaceContainerLowest: Color(0xFFFFFFFF),
            surfaceContainerLow: Color(0xFFFDFCF8),
            surfaceContainer: Color(0xFFF8F0E3),
            surfaceContainerHigh: Color(0xFFEFE8DA),
            surfaceContainerHighest: Color(0xFFDED8CE),
            onSurfaceVariant: Color(0xFF4A4942),
            outline: Color(0xFFBEB9B1),
            outlineVariant: Color(0xFFDED8CE),
            inverseSurface: Color(0xFF020D15),
            onInverseSurface: Color(0xFFFDFCF8),
            inversePrimary: Color(0xFF8AB8DA),
            shadow: Color(0xFF020D15),
            scrim: Color(0xFF020D15),
          )
        : const ColorScheme(
            brightness: Brightness.dark,
            primary: Color(0xFF8AB8DA),
            onPrimary: Color(0xFF062A45),
            primaryContainer: Color(0xFF0F4D7D),
            onPrimaryContainer: Color(0xFFD3E4F2),
            secondary: Color(0xFFFBC971),
            onSecondary: Color(0xFF3D2900),
            secondaryContainer: Color(0xFF5C4100),
            onSecondaryContainer: Color(0xFFFBE4B4),
            tertiary: Color(0xFFFFCE6F),
            onTertiary: Color(0xFF402A00),
            tertiaryContainer: Color(0xFF614200),
            onTertiaryContainer: Color(0xFFFFE4A8),
            error: Color(0xFFF1A799),
            onError: Color(0xFF690A02),
            errorContainer: Color(0xFF8E1C0A),
            onErrorContainer: Color(0xFFF9D9D3),
            surface: Color(0xFF111418),
            onSurface: Color(0xFFE8E6E0),
            surfaceContainerLowest: Color(0xFF0A0D11),
            surfaceContainerLow: Color(0xFF16191D),
            surfaceContainer: Color(0xFF1B1E22),
            surfaceContainerHigh: Color(0xFF24272B),
            surfaceContainerHighest: Color(0xFF2E3136),
            onSurfaceVariant: Color(0xFFCAC7BE),
            outline: Color(0xFF6B6A64),
            outlineVariant: Color(0xFF3C3B36),
            inverseSurface: Color(0xFFE8E6E0),
            onInverseSurface: Color(0xFF020D15),
            inversePrimary: Color(0xFF12609D),
            shadow: Color(0xFF000000),
            scrim: Color(0xFF000000),
          );
    // Per design spec:
    //  - Buttons: default = ink black, pressed = primary blue, disabled = warm gray;
    //    fully rounded (stadium), white label.
    //  - Inputs: outlined (no fill); border = outline gray; focused = ink black;
    //    error = error red.
    //  - Chat bubbles: see MessageBubble (incoming = green, outgoing = blue).
    final ink = brightness == Brightness.light
        ? const Color(0xFF020D15)
        : const Color(0xFFE8E6E0);
    final inkOn = brightness == Brightness.light
        ? const Color(0xFFFDFCF8)
        : const Color(0xFF020D15);

    WidgetStateProperty<Color> btnBg() => WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.disabled)) return scheme.outline;
          if (states.contains(WidgetState.pressed)) return scheme.primary;
          return ink;
        });

    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: scheme.surface,
      appBarTheme: AppBarTheme(
        backgroundColor: scheme.surface,
        foregroundColor: scheme.onSurface,
        elevation: 0,
        scrolledUnderElevation: 1,
        centerTitle: false,
        titleTextStyle: TextStyle(
          color: scheme.onSurface,
          fontSize: 20,
          fontWeight: FontWeight.w700,
        ),
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        color: scheme.surfaceContainerLow,
        margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: ButtonStyle(
          backgroundColor: btnBg(),
          foregroundColor: WidgetStatePropertyAll(inkOn),
          overlayColor: WidgetStatePropertyAll(scheme.primary.withValues(alpha: 0.12)),
          shape: const WidgetStatePropertyAll(StadiumBorder()),
          padding: const WidgetStatePropertyAll(
            EdgeInsets.symmetric(horizontal: 28, vertical: 16),
          ),
          minimumSize: const WidgetStatePropertyAll(Size(64, 52)),
          textStyle: const WidgetStatePropertyAll(
            TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
          ),
          elevation: const WidgetStatePropertyAll(0),
        ),
      ),
      floatingActionButtonTheme: FloatingActionButtonThemeData(
        backgroundColor: ink,
        foregroundColor: inkOn,
        elevation: 2,
        shape: const StadiumBorder(),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: false,
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: scheme.outline),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: scheme.outline),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: ink, width: 1.5),
        ),
        disabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: scheme.outlineVariant),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: scheme.error, width: 1.5),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: scheme.error, width: 1.5),
        ),
        hintStyle: TextStyle(color: scheme.onSurfaceVariant),
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        backgroundColor: scheme.inverseSurface,
        contentTextStyle: TextStyle(color: scheme.onInverseSurface),
      ),
      tabBarTheme: TabBarThemeData(
        labelColor: scheme.primary,
        unselectedLabelColor: scheme.onSurfaceVariant,
        indicatorColor: scheme.primary,
        dividerColor: Colors.transparent,
      ),
    );
  }
}

class _Router extends StatefulWidget {
  const _Router();

  @override
  State<_Router> createState() => _RouterState();
}

class _RouterState extends State<_Router> {
  StreamSubscription? _fcmSub;
  String? _initializedFor;

  @override
  void dispose() {
    _fcmSub?.cancel();
    super.dispose();
  }

  Future<void> _initNotifications(String userId) async {
    if (_initializedFor == userId) return;
    _initializedFor = userId;
    final notifications = context.read<NotificationsService>();
    await notifications.init(userId: userId);
    _fcmSub?.cancel();
    _fcmSub = notifications.onForegroundMessage?.listen((message) {
      if (!mounted) return;
      _handleFcmMessage(message.data);
    });
  }

  /// Route an FCM data payload to the right state. Called for both
  /// foreground messages and notification taps.
  void _handleFcmMessage(Map<String, dynamic> data) {
    final type = data['type']?.toString() ?? '';
    if (type == 'call_invitation') {
      context.read<IncomingCallState>().announce(
            IncomingCall.fromFcmData(data),
          );
      return;
    }
    // Default: a generic backend reply landed — refresh the user's groups so
    // unread badges etc. update.
    final session = context.read<Session>();
    final groups = context.read<GroupsState>();
    if (session.userId != null) {
      groups.refresh(session.userId!);
    }
  }

  Future<void> _initAgoraChat(String userId) async {
    final chatSession = context.read<AgoraChatSession>();
    final chat = context.read<ChatState>();
    try {
      await chatSession.signIn(userId);
      chat.attachListener();
    } catch (e) {
      // Don't block the app on chat init failure; the user can still browse
      // groups and call /api endpoints. Live updates just won't flow.
      debugPrint('Agora Chat sign-in failed: $e');
    }
  }

  Future<void> _initRtm(String userId) async {
    final rtm = context.read<RtmSession>();
    try {
      await rtm.signIn(userId);
    } catch (e) {
      // Same posture as Chat — presence is a nice-to-have, not load-bearing.
      debugPrint('RTM sign-in failed: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = context.watch<Session>();
    final api = context.read<ApiClient>();

    if (!session.isReady) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (!session.isAuthenticated) {
      api.token = null;
      _initializedFor = null;
      _fcmSub?.cancel();
      _fcmSub = null;
      context.read<AgoraChatSession>().signOut();
      context.read<RtmSession>().signOut();
      return const PhoneAuthScreen();
    }
    api.token = session.token;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _initNotifications(session.userId!);
      _initAgoraChat(session.userId!);
      _initRtm(session.userId!);
    });
    return const IncomingCallBanner(child: HomeScreen());
  }
}
