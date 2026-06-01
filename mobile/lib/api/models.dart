class AppUser {
  final String userId;
  final String name;
  final DateTime? createdAt;

  const AppUser({
    required this.userId,
    this.name = '',
    this.createdAt,
  });

  factory AppUser.fromJson(Map<String, dynamic> json) => AppUser(
        userId: json['user_id'] as String,
        name: (json['name'] as String?) ?? '',
        createdAt: _parseDate(json['created_at']),
      );
}

class Group {
  final String groupId;
  final String name;
  final String creatorId;
  final String joinCode;
  final DateTime? createdAt;
  final List<String> members;
  final String whatsappGroupId;

  const Group({
    required this.groupId,
    required this.name,
    required this.creatorId,
    required this.joinCode,
    required this.members,
    this.createdAt,
    this.whatsappGroupId = '',
  });

  factory Group.fromJson(Map<String, dynamic> json) => Group(
        groupId: json['group_id'] as String,
        name: json['name'] as String,
        creatorId: json['creator_id'] as String,
        joinCode: json['join_code'] as String,
        createdAt: _parseDate(json['created_at']),
        members: (json['members'] as List?)?.cast<String>() ?? const [],
        whatsappGroupId: (json['whatsapp_group_id'] as String?) ?? '',
      );
}

class GroupMember {
  final String userId;
  final String name;
  final bool isCreator;

  const GroupMember({
    required this.userId,
    required this.name,
    required this.isCreator,
  });

  String get displayName => name.isNotEmpty ? name : userId;

  factory GroupMember.fromJson(Map<String, dynamic> json) => GroupMember(
        userId: json['user_id'] as String,
        name: (json['name'] as String?) ?? '',
        isCreator: (json['is_creator'] as bool?) ?? false,
      );
}

class AppConfig {
  final String whatsappBotNumber;
  final bool otpDevMode;

  const AppConfig({
    this.whatsappBotNumber = '',
    this.otpDevMode = false,
  });

  factory AppConfig.fromJson(Map<String, dynamic> json) => AppConfig(
        whatsappBotNumber: (json['whatsapp_bot_number'] as String?) ?? '',
        otpDevMode: (json['otp_dev_mode'] as bool?) ?? false,
      );
}

enum MessageDirection { incoming, outgoing }

class Message {
  final String sessionKey;
  final String userId;
  final MessageDirection direction;
  final String text;
  final String? mediaUrl;
  final String? mediaType; // "image" | "document"
  final String? caption;
  final DateTime? createdAt;
  // For group chat: who sent the message. In 1:1 bot chat these may be empty
  // and `direction` is enough — `incoming` = from this user, `outgoing` = bot.
  final String senderId;
  final String senderName;

  const Message({
    required this.sessionKey,
    required this.userId,
    required this.direction,
    required this.text,
    this.mediaUrl,
    this.mediaType,
    this.caption,
    this.createdAt,
    this.senderId = '',
    this.senderName = '',
  });

  bool get hasImage => mediaType == 'image' && (mediaUrl?.isNotEmpty ?? false);
  bool get isFromBot => senderId == 'bot';

  /// True if this message was sent by [viewerId] (so it should render as
  /// "outgoing" in the chat UI regardless of the server-side direction
  /// label, which is bot-centric).
  bool isFromViewer(String viewerId) => senderId == viewerId;

  factory Message.fromJson(Map<String, dynamic> json) => Message(
        sessionKey: json['session_key'] as String,
        userId: json['user_id'] as String,
        direction: (json['direction'] as String) == 'in'
            ? MessageDirection.incoming
            : MessageDirection.outgoing,
        text: json['text'] as String,
        mediaUrl: json['media_url'] as String?,
        mediaType: json['media_type'] as String?,
        caption: json['caption'] as String?,
        createdAt: _parseDate(json['created_at']),
        senderId: (json['sender_id'] as String?) ?? '',
        senderName: (json['sender_name'] as String?) ?? '',
      );
}

/// Minted server-side; mobile uses these to init the Agora SDKs without
/// ever seeing the App Certificate.
class AgoraRtcToken {
  final String token;
  final String appId;
  final String channel;
  final int uid;
  final int role; // 1 = publisher, 2 = subscriber
  final int expiresAt;

  const AgoraRtcToken({
    required this.token,
    required this.appId,
    required this.channel,
    required this.uid,
    required this.role,
    required this.expiresAt,
  });

  factory AgoraRtcToken.fromJson(Map<String, dynamic> json) => AgoraRtcToken(
        token: json['token'] as String,
        appId: json['app_id'] as String,
        channel: json['channel'] as String,
        uid: (json['uid'] as num?)?.toInt() ?? 0,
        role: (json['role'] as num?)?.toInt() ?? 1,
        expiresAt: (json['expires_at'] as num).toInt(),
      );
}

class AgoraRtmToken {
  final String token;
  final String appId;
  final String userId;
  final int expiresAt;

  const AgoraRtmToken({
    required this.token,
    required this.appId,
    required this.userId,
    required this.expiresAt,
  });

  factory AgoraRtmToken.fromJson(Map<String, dynamic> json) => AgoraRtmToken(
        token: json['token'] as String,
        appId: json['app_id'] as String,
        userId: json['user_id'] as String,
        expiresAt: (json['expires_at'] as num).toInt(),
      );
}

class AgoraChatToken {
  final String token;
  final String appKey;
  final String restHost;
  final String userId;
  final int expiresAt;

  const AgoraChatToken({
    required this.token,
    required this.appKey,
    required this.restHost,
    required this.userId,
    required this.expiresAt,
  });

  factory AgoraChatToken.fromJson(Map<String, dynamic> json) => AgoraChatToken(
        token: json['token'] as String,
        appKey: json['app_key'] as String,
        restHost: json['rest_host'] as String,
        userId: json['user_id'] as String,
        expiresAt: (json['expires_at'] as num).toInt(),
      );
}

DateTime? _parseDate(Object? raw) {
  if (raw is String && raw.isNotEmpty) {
    return DateTime.tryParse(raw);
  }
  return null;
}
