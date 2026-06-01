# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

This directory holds the project specification (`Mobile_Based_Student_Chatbot_Support_Platform (2).docx`) for a five-chapter thesis describing a planned system: a mobile-based student chatbot support platform that integrates with WhatsApp and supports collaborative study groups.

**There is no source code in this directory yet.** Any work begun here is greenfield. Before adding code, read the thesis docx — it is the spec of record and pins down the architecture, technology choices, feature scope, non-functional requirements, and evaluation methodology. Chapter 3 (Methodology) and Chapter 4 (Implementation) are the load-bearing sections for engineering decisions.

## Planned architecture (from Chapter 3 of the thesis)

Three-tier system:
- **Presentation layer:** WhatsApp itself, accessed via the WhatsApp Business API. No custom student-facing chat UI is planned. A Flutter companion app handles group/profile management and conversation history view only.
- **Logic layer:** Python + Flask backend exposing webhook endpoints. Contains the chatbot engine (intent dispatch, multi-turn context management, fallback handling) and the group management module. NLP is delegated to Google Dialogflow.
- **Data layer:** Firebase Firestore for users, groups, messages, and a ~200-entry FAQ knowledge base. The thesis describes mixed relational/document use within Firestore.

The chatbot is **reactive only** — WhatsApp Business API policies (template-message requirements, rate limits, 24-hour customer-service window) prevent unsolicited outbound messages. Design accordingly: do not assume push notifications via WhatsApp will work the way a generic notification channel would.

## Planned technology stack

- Backend: Python 3.10, Flask
- Mobile companion: Flutter (Android + iOS from one codebase)
- NLP: Google Dialogflow (intents, entities, training phrases)
- Database: Firebase Firestore
- Messaging: WhatsApp Business API via a cloud provider, webhook-driven
- Hosting: Google Cloud Platform, Docker-containerised
- VCS: Git

## Design constraints worth respecting

- **Fallback path is required.** The chatbot must gracefully hand off unanswerable queries (suggest an office, give a contact, or flag for human follow-up). Do not silently fail and do not fabricate an answer.
- **Multi-turn context is in scope.** "What time does it start?" must resolve against the prior turn ("when is the exam?"). The engine has to persist conversation state per user.
- **Group-aware bot.** When added to a WhatsApp group, the bot responds to mentions and broadcasts replies so every member benefits. A group code is the join mechanism described in Chapter 4.2.4.
- **Non-functional targets (Chapter 3.4.2):** < 3 s response under normal load, ≥ 500 concurrent users, 24/7 availability with a 99 % uptime target, encryption in transit, modular components.
- **Knowledge base is a first-class data asset.** The spec assumes ongoing curation by a dedicated maintainer. Treat the FAQ corpus as live content, not a static seed.

## What exists now (Sprints 1–7)

Located in `backend/`:
- Flask app factory in `app/__init__.py`, gunicorn entrypoint in `wsgi.py`, runs on port 8080.
- `GET /health` and `GET/POST /webhooks/whatsapp` blueprints.
- `app/chatbot.py` — `ChatbotEngine` orchestrating NLP → KB lookup → fallback, with per-session multi-turn history and a confidence-threshold gate. `make_nlp_client_from_env()` picks the NLP backend based on `CHATBOT_NLP_BACKEND` (`dialogflow` default, `gemma` or `gemini` opt-in). Dialogflow/Gemma only *classify* the intent — the answer text comes from `faqs.json` (no hallucinated fee deadlines or office contacts). A backend that exposes `generate_reply` (currently `GeminiClient`) is treated as direct-answer mode: the engine skips KB lookup and uses the LLM's reply verbatim. Empty replies still fall through to the canned fallback so the webhook never 500s.
- `app/dialogflow.py` — `DialogflowClient` that degrades to a keyword-stub when `GOOGLE_APPLICATION_CREDENTIALS` / `DIALOGFLOW_PROJECT_ID` are unset, so the app boots locally without GCP.
- `app/gemma.py` — `GemmaClient` talks to a local Ollama (`http://localhost:11434` by default) and asks Gemma 3 4B to return JSON `{intent, confidence}`. Hallucinated intent names (not in the catalog from `dialogflow_intents.json`) and any transport/parse failure fall through to an empty `IntentResult`, so the chatbot's existing fallback path is what students see — never a 500. To activate: `ollama pull gemma3:4b && ollama serve`, then set `CHATBOT_NLP_BACKEND=gemma` (optionally `OLLAMA_BASE_URL`, `OLLAMA_MODEL`) in `backend/.env`.
- `app/agora.py` + `app/agora_routes.py` — Agora server-side foundation. `AgoraClient` mints **RTC** (voice/video), **RTM** (signalling), and **Chat** (messaging) tokens from `AGORA_APP_ID` + `AGORA_APP_CERTIFICATE`. RTC/RTM use `agora-token-builder`; Chat is a JWT with `chatUserName` claim per Agora's auth spec. `AgoraChatRestClient` is a REST helper for admin actions: `ensure_user`, `send_text`, `send_to_group`, `create_chat_group`, `add_member`, `remove_member`, `delete_chat_group`. On `create_app` boot we best-effort `ensure_user("bot")` so the bot account exists. Endpoints: `POST /api/agora/{rtc,rtm,chat}-token` — JWT-authed, tokens bound to the JWT subject. Returns 503 when creds are missing. App Certificate never leaves the server.
- `app/agora_webhook.py` — `POST /webhooks/agora` is the post-send callback that Agora Chat calls for every message. Validates `Signature` header against `AGORA_CHAT_WEBHOOK_SECRET` (empty = dev mode, check skipped). Dispatches: 1:1 to `bot` → `ChatbotEngine.handle` → reply via `send_text(from='bot', to=sender)`. Group msg with `@bot` mention → reply via `send_to_group(from='bot', group_id)`. All inbound + outbound messages persisted to Store with `sender_id`/`sender_name` so `/api/users/<id>/messages` and `/api/groups/<id>/messages` stay the history source of truth. Self-messages from `bot` are ignored (loop guard).
- `app/groups.py` — `GroupService` now takes an optional `ChatGroupMirror` (the Agora Chat REST client). When supplied, `create`/`join`/`delete` mirror lifecycle into Agora Chat and store the `agora_chat_group_id` on the `Group` so the mobile SDK can subscribe. Mirroring is best-effort — REST failures are logged, the local change still wins.
- `POST /api/calls/notify` (in `app/api.py`) — body `{group_id}`. JWT-authed; verifies caller is a member, then FCM-pushes every *other* group member with data `{type: "call_invitation", group_id, group_name, initiator_id, initiator_name}`. Mobile fires this when the caller opens `GroupCallScreen`, so members get a system push (works in background/closed) plus an in-app banner if the app is foregrounded. Returns `{notified: N}`.
- Mobile (`mobile/lib/agora/agora_session.dart`, `mobile/lib/agora/agora_chat_session.dart`, `mobile/lib/agora/rtm_session.dart`, `mobile/lib/state/chat_state.dart`, `mobile/lib/state/presence_state.dart`, `mobile/lib/state/incoming_call_state.dart`, `mobile/lib/widgets/incoming_call_banner.dart`, `mobile/lib/screens/group_call_screen.dart`) — Agora **RTC**, **RTM**, and **Chat** are fully wired, plus call-start ringing. `IncomingCallState` holds the pending invitation (auto-dismissed after 45 s); fed by the FCM foreground listener in `_Router._handleFcmMessage` which routes `type=call_invitation` data messages. `IncomingCallBanner` wraps `HomeScreen` and renders a primary-coloured banner with Join/Decline buttons when there's a pending call — Join fetches the full group via REST and pushes `GroupCallScreen`. `AgoraSession` owns RTC engine + RTM/Chat tokens. `AgoraChatSession` initializes the Chat SDK and `loginWithToken` once per sign-in. `RtmSession` does the same for RTM and exposes `subscribeToGroup`/`unsubscribeFromGroup` (channel = `g_<groupId>` with `withPresence: true`). `PresenceState` folds `PresenceEvent`s (snapshot, interval, remoteJoinChannel, remoteLeaveChannel, remoteTimeout) into a `Map<groupId, Set<userId>>` of online members. `ChatState` lives over Agora Chat: live messages flow from `ChatClient.chatManager`'s event handler; history backfill still goes through `ApiClient.listUserMessages`/`listGroupMessages` (which the Agora webhook keeps current). `sendToBot`/`sendToGroup` call `ChatMessage.createTxtSendMessage` + `chatManager.sendMessage`. Group screen subscribes its `group_id` for live presence on `initState` and unsubscribes on `dispose`; members tab shows a green dot on each online member's avatar plus an "N online" pill in the header. Group screen video-camera icon → `GroupCallScreen` joins the RTC channel using `group_id` as the channel name.
- `app/gemini.py` — `GeminiClient` calls the Google Gemini REST API (`generativelanguage.googleapis.com/v1beta`, `gemini-flash-latest` by default — `gemini-2.0-flash` has no free-tier quota under Vertex AI Express keys) and returns the full chat reply, not just an intent. Exposes `generate_reply(session, text, history)`, which is what flags this backend as direct-answer in `ChatbotEngine`. Last 4 turns of history are forwarded as `contents` with alternating `user`/`model` roles; the system instruction (overridable via `GEMINI_SYSTEM_INSTRUCTION`) caps replies near 100 words and tells the model to admit it doesn't know rather than invent dates/contacts. Missing `GEMINI_API_KEY`, network errors, non-JSON bodies, or empty candidates all yield `""`, which the engine maps to the canned fallback. To activate: get a key at https://aistudio.google.com/apikey, then set `CHATBOT_NLP_BACKEND=gemini` and `GEMINI_API_KEY` in `backend/.env` (optionally `GEMINI_MODEL`).
- `app/whatsapp.py` — `parse_incoming` extracts text, image, and document messages (other types skipped). Image/document carry `media_id`/`media_type`/`caption`; the text field falls back to the caption or a `[image]`/`[document]` placeholder so chatbot routing still has something to work with. Group messages populate `group_id` from `messages[].context.group_id`. `is_bot_mentioned()` / `strip_mention()` gate group replies on a configurable `BOT_MENTION_NAME`. `WhatsAppClient.send_text` (no-op if access token unset). `WhatsAppClient.fetch_media(media_id)` performs the two-step Graph API exchange (metadata → signed CDN URL → bytes) used by the media proxy.
- `app/security.py` — `verify_meta_signature` for `X-Hub-Signature-256` HMAC check. Applied to `POST /webhooks/whatsapp`. **If `META_APP_SECRET` is empty the check is skipped — dev-only escape hatch, never deploy with it empty.**
- `app/store.py` — `Store` protocol with `InMemoryStore` and `FirestoreStore` implementations covering users, groups, and messages. `make_store_from_env()` returns `FirestoreStore` when both `FIRESTORE_PROJECT_ID` and (`GOOGLE_APPLICATION_CREDENTIALS` or `FIRESTORE_EMULATOR_HOST`) are set; otherwise `InMemoryStore`. The store is stashed on `app.extensions["store"]` and is injectable through `create_app(store=...)` for tests.
- `app/groups.py` — `GroupService` thin layer over the Store. Generates `group_id` and `join_code` via `secrets`; creator auto-joined; delete is creator-only.
- `app/api.py` — REST blueprint at `/api/*` for the Flutter companion app. All routes require a Bearer JWT; routes with a `<user_id>` path param enforce that the JWT subject matches.
- `app/auth.py` — `OtpStore` (in-process, 5-min TTL, 5-attempt cap), JWT helpers (HS256), `@require_auth` decorator with optional path-param enforcement, and the `/api/auth/*` blueprint (request-otp, verify-otp).
- `app/push.py` — `FcmPusher` over `firebase-admin`. Degrades to a logging no-op when `FCM_PROJECT_ID` or `GOOGLE_APPLICATION_CREDENTIALS` is unset, or when `firebase-admin` init fails. Called after every outbound chatbot reply in the webhook; pushes to all registered devices for the recipient.
- `knowledge_base/faqs.json` — 5 seed FAQs keyed by intent.
- `knowledge_base/dialogflow_intents.json` — canonical training-phrases source for the Dialogflow agent. Every intent here must have a matching entry in `faqs.json`, and vice versa (enforced by `tests/test_dialogflow_import.py::test_repo_kb_and_intents_are_in_sync`).
- `app/dialogflow_import.py` + `scripts/import_dialogflow_intents.py` — idempotent CLI that upserts the JSON intent set into a real Dialogflow ES agent via `IntentsClient`. Pulls answer text from `faqs.json` so the agent's `fulfillment_text` matches what the chatbot serves from the KB. Run with `python backend/scripts/import_dialogflow_intents.py [--project-id … --dry-run]`. `--dry-run` works offline (no credentials needed).
- `tests/` — 80 passing tests covering health, webhook verify/inbound, signature verification (valid/missing/tampered/dev-skip), confidence-threshold gating, store CRUD for users/groups/messages/devices, `GroupService` rules, webhook persistence + push side-effects, the full REST surface, OTP issuance/verify (happy path, wrong code, single-use), JWT enforcement (missing/malformed/expired/wrong-subject), device registration (happy path, bad platform, missing token, subject-mismatch, idempotency), FCM stub no-op behavior, and media parsing (image with/without caption, document filename fallback, unsupported types skipped, end-to-end persistence of media fields).

## REST API surface (`/api/*`)

All `/api/*` routes except `/api/auth/*` require `Authorization: Bearer <jwt>`. Tokens come from `POST /api/auth/verify-otp`. Subject (`sub` claim) is enforced to equal `<user_id>` on routes that have that path param; on group routes the route logic itself enforces creator-only / member-only access.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/request-otp` | Body: `{phone_number}`. Issues a 6-digit OTP (5-min TTL, 5-attempt cap). In dev (`OTP_ECHO_IN_RESPONSE=true`) the code is returned in the response; in production it must be delivered via WhatsApp. |
| POST | `/api/auth/verify-otp` | Body: `{phone_number, code}`. Returns `{token, user_id, expires_in_days}` on success; 401 on invalid/expired code. OTP is single-use. |
| GET | `/api/users/<user_id>` | Fetch user profile (404 if unknown). |
| PATCH | `/api/users/<user_id>` | Upsert profile name (idempotent). |
| GET | `/api/users/<user_id>/groups` | Groups the user is a member of. |
| GET | `/api/users/<user_id>/messages?limit=N` | 1:1 conversation history, oldest-first, limit clamped to [1,100]. |
| POST | `/api/groups` | Body: `{name, creator_id}`. `creator_id` must equal JWT subject (403 otherwise). → 201 with `join_code`. |
| GET | `/api/groups/<group_id>` | Group details + member list. |
| DELETE | `/api/groups/<group_id>` | Creator-only (checked against JWT subject); 403 otherwise. |
| POST | `/api/groups/join` | Body: `{code, user_id}`. `user_id` must equal JWT subject. → 404 on bad code. |
| GET | `/api/groups/<group_id>/messages?limit=N` | Members-only (checked against JWT subject); 403 otherwise. |
| POST | `/api/users/<user_id>/devices` | Register FCM token; body: `{fcm_token, platform}` where platform ∈ {android, ios, web}. Idempotent. |
| DELETE | `/api/users/<user_id>/devices/<fcm_token>` | Unregister a device (e.g. on sign-out). |
| GET | `/api/media/<media_id>` | Proxy WhatsApp media bytes through the backend (Graph API signed URLs need the WABA bearer token, so the mobile client can't fetch them directly). Returns 503 if `WHATSAPP_ACCESS_TOKEN` is unset, 404 if the media id is unknown, 502 on upstream errors. |

End-to-end flow: WhatsApp webhook persists every turn → mobile app reads them via the API. Both code paths share the same `Store` instance on `app.extensions["store"]`.

## Flutter companion app (`mobile/`)

Bootstrapped with `flutter create --project-name companion --org com.studentchatbot --platforms=android,ios`. Flutter 3.38.5, Dart 3.10.4, Material 3.

Structure under `mobile/lib/`:
- `main.dart` — entry; runs `CompanionApp`.
- `app.dart` — `MultiProvider` wires `ApiClient` (singleton), `Session` (loads on construction), and `GroupsState` (proxy on `ApiClient`). `_Router` shows the setup screen until `Session.hasIdentity`, then the home screen.
- `api/models.dart` — `AppUser`, `Group`, `Message` (+ `MessageDirection` enum) with `fromJson` factories matching the backend's JSON shape exactly.
- `api/client.dart` — `ApiClient` over `package:http`. Base URL controlled by `--dart-define=API_BASE=...`; default `http://10.0.2.2:8080` (Android emulator → host loopback). For iOS simulator use `http://localhost:8080`; for a physical device use the host machine's LAN IP.
- `state/session.dart` — `ChangeNotifier` with JWT in `flutter_secure_storage` and `user_id`/`display_name` cached in `SharedPreferences`. `isAuthenticated` gates the router. `setAuthenticated()` is called by the OTP flow; `signOut()` clears both stores.
- `screens/phone_auth_screen.dart` + `screens/otp_screen.dart` — sign-in flow. Phone screen calls `request-otp`; OTP screen calls `verify-otp` and, on success, writes the JWT into `Session` and the in-memory `ApiClient.token`. In dev mode the OTP is echoed back by the backend and prefilled in the OTP field for convenience.
- `notifications/notifications_service.dart` — wraps `firebase_core` + `firebase_messaging`. `init(userId)` requests permission, fetches the FCM token, posts it to `/api/users/<id>/devices`, and listens for token refresh. Foreground `RemoteMessage` events trigger a `GroupsState.refresh`. **Requires `flutterfire configure` to actually receive pushes** — without `firebase_options.dart` and the platform config files (`google-services.json` / `GoogleService-Info.plist`), `Firebase.initializeApp()` throws and the service degrades to a no-op. The rest of the app still runs.
- `state/groups_state.dart` — `ChangeNotifier` holding the groups list with `refresh/create/join/delete`.
- `screens/` — `home_screen`, `group_screen`, `create_group_screen`, `join_group_screen`, `messages_screen`, `settings_screen`. The settings screen handles display-name updates and sign-out; first-run identity setup is the phone+OTP flow.
- `widgets/` — `GroupTile`, `MessageBubble`. Bubble renders image (`Image.network` with loading + error fallback), document affordance (paperclip + filename), or plain text depending on `Message.mediaType`. Incoming = right-aligned/primary container (= "from the user"), outgoing = left-aligned/surface container (= "from the bot").

Run: `cd mobile && flutter pub get && flutter run --dart-define=API_BASE=http://10.0.2.2:8080`
Analyze: `cd mobile && flutter analyze` (currently clean)
Test: `cd mobile && flutter test` (12 tests — model parsing, MessageBubble rendering for text/image/document, GroupTile pluralization + tap, PhoneAuthScreen submit + empty-state)

The Flutter project's `pubspec.yaml` was rewritten to drop the generated boilerplate comments and add: `http`, `shared_preferences`, `provider`, `intl`. `flutter pub get` was already run; the `pubspec.lock` is committed.

The webhook now persists every inbound and outbound message via the Store and upserts the sender as a `User` on first contact. `ChatbotEngine._history` remains as a fast in-process context cache; the Store is the source of truth for the mobile companion UI.

Run: `pip install -r backend/requirements.txt && cp backend/.env.example backend/.env && python backend/wsgi.py`
Test: `cd backend && python -m pytest -q`

## What does not exist yet

- **Real Dialogflow agent.** The importer (`backend/scripts/import_dialogflow_intents.py`) is in place but won't run until you create a Dialogflow ES agent and provide `DIALOGFLOW_PROJECT_ID` + `GOOGLE_APPLICATION_CREDENTIALS`. Until then `DialogflowClient` continues to use the keyword stub.
- **Production OTP delivery.** Today the OTP is logged server-side and (in dev) echoed in the response. Before production, route OTP delivery through `WhatsAppClient.send_text` with an approved template message, and set `OTP_ECHO_IN_RESPONSE=false`.
- **OTP store durability.** `OtpStore` is in-process — won't survive worker restarts or scale across replicas. Swap for Redis or a Firestore TTL collection before going multi-process.
- **Firebase project configuration.** The mobile FCM code is in place but inert until you run `flutterfire configure` (or manually drop `firebase_options.dart` + `google-services.json` / `GoogleService-Info.plist`) and set `FCM_PROJECT_ID` + a service-account JSON on the backend.
- CI pipeline, deployment manifests beyond the Dockerfile.
- Outbound template messages (required for unsolicited notifications under WhatsApp Business API policy).
- FirestoreStore integration tests — code path is exercised only when a real Firestore (or emulator) is reachable; CI today runs InMemoryStore only.
- Pagination on `/messages` endpoints — currently `limit` only, no cursor.
- Widget tests in the Flutter app — only model-parsing unit tests exist.

The thesis order from section 3.3 is now complete: Flask backend (done) → Dialogflow + signature verification (done) → group module persistence (done) → REST surface for mobile (done) → Flutter companion app (done). Subsequent work should focus on the authentication gap, then real-time updates, then media support.

## Other files in this directory

- `Untitled` — task list from an unrelated project (mentions Suppliers, payroll, Raw Materials). Not part of the chatbot project. Ignore unless the user says otherwise.

## Git context

The casa/ workspace lives inside the user's home directory (`C:\Users\CODEWITHFIIFI`), which is also the git root for this checkout. `git status` from anywhere under casa/ will surface noise from many unrelated projects in sibling directories. Scope any staging to paths under `Desktop/casa/APPP/` and avoid `git add -A` / `git add .` from above this folder.
