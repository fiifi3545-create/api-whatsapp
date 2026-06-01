import 'dart:convert';

import 'package:http/http.dart' as http;

import 'models.dart';

class ApiException implements Exception {
  final int statusCode;
  final String message;
  ApiException(this.statusCode, this.message);

  @override
  String toString() => 'ApiException($statusCode): $message';
}

class ApiClient {
  static const String _defaultBase = String.fromEnvironment(
    'API_BASE',
    defaultValue: 'http://10.0.2.2:8080',
  );

  final String baseUrl;
  final http.Client _http;

  /// Bearer token. Set by Session after successful OTP verification.
  String? token;

  ApiClient({String? baseUrl, http.Client? client})
      : baseUrl = baseUrl ?? _defaultBase,
        _http = client ?? http.Client();

  // ----- Auth --------------------------------------------------------
  /// Returns the OTP string when the backend echoes it (dev mode), otherwise null.
  Future<String?> requestOtp(String phoneNumber) async {
    final resp = await _http.post(
      _url('/api/auth/request-otp'),
      headers: _headers(json: true, auth: false),
      body: jsonEncode({'phone_number': phoneNumber}),
    );
    _ensureOk(resp);
    final body = jsonDecode(resp.body) as Map<String, dynamic>;
    return body['otp'] as String?;
  }

  /// Returns the issued JWT on success.
  Future<String> verifyOtp({required String phoneNumber, required String code}) async {
    final resp = await _http.post(
      _url('/api/auth/verify-otp'),
      headers: _headers(json: true, auth: false),
      body: jsonEncode({'phone_number': phoneNumber, 'code': code}),
    );
    _ensureOk(resp);
    final body = jsonDecode(resp.body) as Map<String, dynamic>;
    return body['token'] as String;
  }

  // ----- Users -------------------------------------------------------
  Future<AppUser?> getUser(String userId) async {
    final resp = await _http.get(_url('/api/users/$userId'), headers: _headers());
    if (resp.statusCode == 404) return null;
    _ensureOk(resp);
    return AppUser.fromJson(jsonDecode(resp.body));
  }

  Future<AppUser> upsertUserName(String userId, String name) async {
    final resp = await _http.patch(
      _url('/api/users/$userId'),
      headers: _headers(json: true),
      body: jsonEncode({'name': name}),
    );
    _ensureOk(resp);
    return AppUser.fromJson(jsonDecode(resp.body));
  }

  Future<List<Group>> listUserGroups(String userId) async {
    final resp = await _http.get(_url('/api/users/$userId/groups'), headers: _headers());
    _ensureOk(resp);
    final body = jsonDecode(resp.body) as Map<String, dynamic>;
    return ((body['groups'] as List?) ?? const [])
        .map((e) => Group.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Send a chat message to the bot via the in-app channel (instead of WhatsApp).
  /// Returns the two new messages: the user's question + the bot's reply.
  Future<List<Message>> sendChatMessage(String userId, String text) async {
    final resp = await _http.post(
      _url('/api/users/$userId/chat'),
      headers: _headers(json: true),
      body: jsonEncode({'text': text}),
    );
    _ensureOk(resp);
    final body = jsonDecode(resp.body) as Map<String, dynamic>;
    return ((body['messages'] as List?) ?? const [])
        .map((e) => Message.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<Message>> listUserMessages(String userId, {int limit = 50}) async {
    final resp = await _http.get(
      _url('/api/users/$userId/messages?limit=$limit'),
      headers: _headers(),
    );
    _ensureOk(resp);
    final body = jsonDecode(resp.body) as Map<String, dynamic>;
    return ((body['messages'] as List?) ?? const [])
        .map((e) => Message.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  // ----- Groups ------------------------------------------------------
  Future<Group> createGroup({required String name, required String creatorId}) async {
    final resp = await _http.post(
      _url('/api/groups'),
      headers: _headers(json: true),
      body: jsonEncode({'name': name, 'creator_id': creatorId}),
    );
    if (resp.statusCode != 201) _ensureOk(resp);
    return Group.fromJson(jsonDecode(resp.body));
  }

  Future<Group?> getGroup(String groupId) async {
    final resp = await _http.get(_url('/api/groups/$groupId'), headers: _headers());
    if (resp.statusCode == 404) return null;
    _ensureOk(resp);
    return Group.fromJson(jsonDecode(resp.body));
  }

  Future<bool> deleteGroup({required String groupId, required String requesterId}) async {
    final resp = await _http.delete(_url('/api/groups/$groupId'), headers: _headers());
    if (resp.statusCode == 403 || resp.statusCode == 404) return false;
    _ensureOk(resp);
    return true;
  }

  Future<Group?> joinGroup({required String code, required String userId}) async {
    final resp = await _http.post(
      _url('/api/groups/join'),
      headers: _headers(json: true),
      body: jsonEncode({'code': code, 'user_id': userId}),
    );
    if (resp.statusCode == 404) return null;
    _ensureOk(resp);
    return Group.fromJson(jsonDecode(resp.body));
  }

  Future<List<GroupMember>> listGroupMembers(String groupId) async {
    final resp = await _http.get(
      _url('/api/groups/$groupId/members'),
      headers: _headers(),
    );
    _ensureOk(resp);
    final body = jsonDecode(resp.body) as Map<String, dynamic>;
    return ((body['members'] as List?) ?? const [])
        .map((e) => GroupMember.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<AppConfig> getConfig() async {
    final resp = await _http.get(_url('/api/config'), headers: _headers(auth: false));
    _ensureOk(resp);
    return AppConfig.fromJson(jsonDecode(resp.body));
  }

  // ----- Agora token endpoints --------------------------------------
  Future<AgoraRtcToken> fetchRtcToken({
    required String channel,
    int uid = 0,
    String role = 'publisher',
    int ttlSeconds = 3600,
  }) async {
    final resp = await _http.post(
      _url('/api/agora/rtc-token'),
      headers: _headers(json: true),
      body: jsonEncode({
        'channel': channel,
        'uid': uid,
        'role': role,
        'ttl_seconds': ttlSeconds,
      }),
    );
    _ensureOk(resp);
    return AgoraRtcToken.fromJson(jsonDecode(resp.body));
  }

  Future<AgoraRtmToken> fetchRtmToken({int ttlSeconds = 86400}) async {
    final resp = await _http.post(
      _url('/api/agora/rtm-token'),
      headers: _headers(json: true),
      body: jsonEncode({'ttl_seconds': ttlSeconds}),
    );
    _ensureOk(resp);
    return AgoraRtmToken.fromJson(jsonDecode(resp.body));
  }

  Future<AgoraChatToken> fetchChatToken({int ttlSeconds = 86400}) async {
    final resp = await _http.post(
      _url('/api/agora/chat-token'),
      headers: _headers(json: true),
      body: jsonEncode({'ttl_seconds': ttlSeconds}),
    );
    _ensureOk(resp);
    return AgoraChatToken.fromJson(jsonDecode(resp.body));
  }

  Future<List<Message>> listGroupMessages(String groupId, {int limit = 50}) async {
    final resp = await _http.get(
      _url('/api/groups/$groupId/messages?limit=$limit'),
      headers: _headers(),
    );
    _ensureOk(resp);
    final body = jsonDecode(resp.body) as Map<String, dynamic>;
    return ((body['messages'] as List?) ?? const [])
        .map((e) => Message.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Ring the other members of a group when starting an Agora RTC call.
  /// Returns the number of members the backend pushed to.
  Future<int> notifyCallStart(String groupId) async {
    final resp = await _http.post(
      _url('/api/calls/notify'),
      headers: _headers(json: true),
      body: jsonEncode({'group_id': groupId}),
    );
    _ensureOk(resp);
    final body = jsonDecode(resp.body) as Map<String, dynamic>;
    return (body['notified'] as num?)?.toInt() ?? 0;
  }

  // ----- Devices (FCM) ----------------------------------------------
  Future<void> registerDevice({
    required String userId,
    required String fcmToken,
    required String platform,
  }) async {
    final resp = await _http.post(
      _url('/api/users/$userId/devices'),
      headers: _headers(json: true),
      body: jsonEncode({'fcm_token': fcmToken, 'platform': platform}),
    );
    if (resp.statusCode != 201) _ensureOk(resp);
  }

  Future<void> unregisterDevice({
    required String userId,
    required String fcmToken,
  }) async {
    final resp = await _http.delete(
      _url('/api/users/$userId/devices/$fcmToken'),
      headers: _headers(),
    );
    if (resp.statusCode == 404) return;
    _ensureOk(resp);
  }

  /// Full URL for the media-proxy endpoint that resolves a WhatsApp media id
  /// to the binary bytes. The mobile client passes the JWT via `mediaHeaders()`.
  String mediaProxyUrl(String mediaId) =>
      '$baseUrl/api/media/${Uri.encodeComponent(mediaId)}';

  /// Headers to attach to image/document requests against the media proxy.
  Map<String, String> mediaHeaders() => _headers();

  Uri _url(String path) => Uri.parse('$baseUrl$path');

  Map<String, String> _headers({bool json = false, bool auth = true}) {
    final headers = <String, String>{};
    if (json) headers['Content-Type'] = 'application/json';
    if (auth && token != null && token!.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }

  void _ensureOk(http.Response resp) {
    if (resp.statusCode >= 400) {
      throw ApiException(resp.statusCode, resp.body);
    }
  }

  void close() => _http.close();
}
