#!/usr/bin/env node
/**
 * Zaelar WhatsApp bridge (Baileys) — derived from an MIT bridge, see LICENSE and VENDORED_FROM.md
 *
 * Standalone Node.js process that connects to WhatsApp via Baileys
 * and exposes HTTP endpoints for the Python gateway adapter.
 *
 * Endpoints (matches gateway/platforms/whatsapp.py expectations):
 *   GET  /messages       - Long-poll for new incoming messages
 *   POST /send           - Send a message { chatId, message, replyTo? }
 *   POST /edit           - Edit a sent message { chatId, messageId, message }
 *   POST /send-media     - Send media natively { chatId, filePath, mediaType?, caption?, fileName? }
 *   POST /typing         - Send typing indicator { chatId }
 *   GET  /chat/:id       - Get chat info
 *   GET  /health         - Health check
 *
 * Usage:
 *   node bridge.js --port 3111 --session ~/.zaelar/whatsapp/session
 */

import { makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion, downloadMediaMessage } from '@whiskeysockets/baileys';
import express from 'express';
import { Boom } from '@hapi/boom';
import pino from 'pino';
import path from 'path';
import { mkdirSync, readFileSync, writeFileSync, existsSync, readdirSync, unlinkSync } from 'fs';
import { fileURLToPath } from 'url';
import { randomBytes, createHash } from 'crypto';
import { execSync } from 'child_process';
import { tmpdir } from 'os';
import qrcode from 'qrcode-terminal';
import QRCode from 'qrcode';  // ZAELAR-PATCH: render the pairing QR as a data-URI PNG for the web widget
import { matchesAllowedUser, parseAllowedUsers } from './allowlist.js';

// Parse CLI args
const args = process.argv.slice(2);
function getArg(name, defaultVal) {
  const idx = args.indexOf(`--${name}`);
  return idx !== -1 && args[idx + 1] ? args[idx + 1] : defaultVal;
}

const WHATSAPP_DEBUG =
  typeof process !== 'undefined' &&
  process.env &&
  typeof process.env.WHATSAPP_DEBUG === 'string' &&
  ['1', 'true', 'yes', 'on'].includes(process.env.WHATSAPP_DEBUG.toLowerCase());

const PORT = parseInt(getArg('port', '3000'), 10);
const SESSION_DIR = getArg('session', path.join(process.env.HOME || '~', '.zaelar', 'whatsapp', 'session'));
// Cache directories: the Python gateway passes the profile-aware paths via
// env (ZAELAR_*_CACHE_DIR).  Fall back to the
// hardcoded locations for bridges launched outside the gateway.
const IMAGE_CACHE_DIR = process.env.ZAELAR_IMAGE_CACHE_DIR
  || path.join(process.env.HOME || '~', '.zaelar', 'image_cache');
const DOCUMENT_CACHE_DIR = process.env.ZAELAR_DOCUMENT_CACHE_DIR
  || path.join(process.env.HOME || '~', '.zaelar', 'document_cache');
const AUDIO_CACHE_DIR = process.env.ZAELAR_AUDIO_CACHE_DIR
  || path.join(process.env.HOME || '~', '.zaelar', 'audio_cache');

// Self-hash of this script file.  Reported in /health so the Python gateway
// can detect a running bridge that predates the current bridge.js and
// restart it instead of silently reusing stale code (stale-bridge trap:
// an update writes bridge.js on disk but a long-lived bridge process
// keeps serving the old behavior forever).
let SCRIPT_HASH = '';
try {
  SCRIPT_HASH = createHash('sha256')
    .update(readFileSync(fileURLToPath(import.meta.url)))
    .digest('hex')
    .slice(0, 16);
} catch {}
const PAIR_ONLY = args.includes('--pair-only');
// ZAELAR-PATCH: how this linked device is named on the operator's phone.
const DEVICE_NAME = process.env.ZAELAR_DEVICE_NAME || 'Zaelar Agent';
const WHATSAPP_MODE = getArg('mode', process.env.WHATSAPP_MODE || 'self-chat'); // "bot" | "self-chat" | "observe" (ZAELAR-PATCH)
const ALLOWED_USERS = parseAllowedUsers(process.env.WHATSAPP_ALLOWED_USERS || '');
const DEFAULT_REPLY_PREFIX = '';
const REPLY_PREFIX = process.env.WHATSAPP_REPLY_PREFIX === undefined
  ? DEFAULT_REPLY_PREFIX
  : process.env.WHATSAPP_REPLY_PREFIX.replace(/\\n/g, '\n');
const MAX_MESSAGE_LENGTH = parseInt(process.env.WHATSAPP_MAX_MESSAGE_LENGTH || '4096', 10);
const CHUNK_DELAY_MS = parseInt(process.env.WHATSAPP_CHUNK_DELAY_MS || '300', 10);
// Per-call timeout for sock.sendMessage(). Baileys occasionally hangs forever
// when uploading media to WhatsApp servers (and, less often, on text sends),
// which pins the bridge's HTTP handler until the upstream aiohttp timeout
// fires. Fail fast instead so the gateway can surface a real error and retry.
const SEND_TIMEOUT_MS = parseInt(process.env.WHATSAPP_SEND_TIMEOUT_MS || '60000', 10);

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function sendWithTimeout(chatId, payload, timeoutMs = SEND_TIMEOUT_MS) {
  let timer;
  const timeoutPromise = new Promise((_, reject) => {
    timer = setTimeout(
      () => reject(new Error(`sendMessage timed out after ${timeoutMs / 1000}s`)),
      timeoutMs,
    );
  });
  return Promise.race([sock.sendMessage(chatId, payload), timeoutPromise])
    .finally(() => clearTimeout(timer));
}

function formatOutgoingMessage(message) {
  // In bot mode, messages come from a different number so the prefix is
  // redundant — the sender identity is already clear.  Only prepend in
  // self-chat mode where bot and user share the same number.
  if (WHATSAPP_MODE !== 'self-chat') return message;
  return REPLY_PREFIX ? `${REPLY_PREFIX}${message}` : message;
}

function splitLongMessage(message, maxLength = MAX_MESSAGE_LENGTH) {
  const text = String(message || '');
  if (!text) return [];
  if (!Number.isFinite(maxLength) || maxLength < 1 || text.length <= maxLength) {
    return [text];
  }

  const chunks = [];
  let remaining = text;
  while (remaining.length > maxLength) {
    let splitAt = remaining.lastIndexOf('\n', maxLength);
    if (splitAt < Math.floor(maxLength / 2)) {
      splitAt = remaining.lastIndexOf(' ', maxLength);
    }
    if (splitAt < 1) splitAt = maxLength;

    chunks.push(remaining.slice(0, splitAt).trimEnd());
    remaining = remaining.slice(splitAt).trimStart();
  }
  if (remaining) chunks.push(remaining);
  return chunks;
}

function trackSentMessageId(sent) {
  if (sent?.key?.id) {
    recentlySentIds.add(sent.key.id);
    if (recentlySentIds.size > MAX_RECENT_IDS) {
      recentlySentIds.delete(recentlySentIds.values().next().value);
    }
  }
}

function normalizeWhatsAppId(value) {
  if (!value) return '';
  return String(value).replace(':', '@');
}

function getMessageContent(msg) {
  const content = msg?.message || {};
  if (content.ephemeralMessage?.message) return content.ephemeralMessage.message;
  if (content.viewOnceMessage?.message) return content.viewOnceMessage.message;
  if (content.viewOnceMessageV2?.message) return content.viewOnceMessageV2.message;
  if (content.documentWithCaptionMessage?.message) return content.documentWithCaptionMessage.message;
  if (content.templateMessage?.hydratedTemplate) return content.templateMessage.hydratedTemplate;
  if (content.buttonsMessage) return content.buttonsMessage;
  if (content.listMessage) return content.listMessage;
  return content;
}

function getContextInfo(messageContent) {
  if (!messageContent || typeof messageContent !== 'object') return {};
  for (const value of Object.values(messageContent)) {
    if (value && typeof value === 'object' && value.contextInfo) {
      return value.contextInfo;
    }
  }
  return {};
}

mkdirSync(SESSION_DIR, { recursive: true });

// Build LID → phone reverse map from session files (lid-mapping-{phone}.json)
function buildLidMap() {
  const map = {};
  try {
    for (const f of readdirSync(SESSION_DIR)) {
      const m = f.match(/^lid-mapping-(\d+)\.json$/);
      if (!m) continue;
      const phone = m[1];
      const lid = JSON.parse(readFileSync(path.join(SESSION_DIR, f), 'utf8'));
      if (lid) map[String(lid)] = phone;
    }
  } catch {}
  return map;
}
let lidToPhone = buildLidMap();

const logger = pino({ level: 'warn' });

// Message queue for polling
const messageQueue = [];
// ZAELAR-PATCH: «load previous» pages of 50 land here too, so the queue must hold several polls' worth; at 100
// a page could push out the live messages waiting beside it.
const MAX_QUEUE_SIZE = 2000;
// ZAELAR-PATCH (V2-546): chats the operator read on another device, drained by GET /reads. Kept SEPARATE from
// messageQueue on purpose — a read receipt is not a message, and mixing them would put it through triage.
const readQueue = [];
// ZAELAR-PATCH: messages of the pairing history sync, drained by GET /sync into the archive.
const syncQueue = [];
const SYNC_QUEUE_MAX = 100000;
// ZAELAR-PATCH (V2-546): chats we have just asked the PHONE for history about, with an expiry. The phone answers
// with ordinary upserts, so without this the scrollback of a conversation would be triaged as if it had all
// just arrived — and the operator would be interrupted about messages from weeks ago because he pressed
// "load previous". Tagged `history:true`, the Python side routes them to the conversation and never notifies.
const historyWanted = new Map();
const HISTORY_WINDOW_MS = 60_000;

function wantsHistory(chatId) {
  const until = historyWanted.get(chatId);
  if (!until) return false;
  if (Date.now() > until) { historyWanted.delete(chatId); return false; }
  return true;
}

// Track recently sent message IDs to prevent echo-back loops with media
const recentlySentIds = new Set();
const MAX_RECENT_IDS = 50;

let sock = null;

// ZAELAR-PATCH (V2-645): a group message must carry the group's SUBJECT, never its bare numeric id.
// Measured live (2026-09-09): every group event shipped chatName = the id digits, so «el grupo del viaje»
// was unfindable BY NAME in every store downstream (thread store, communications archive). The metadata
// door already existed one screen down (GET /chat/:id uses sock.groupMetadata) — the events simply never
// walked through it. Cached per chat: subjects are stable, and one lookup per group per process is the
// right price. A failed lookup is NOT cached, so the next message retries.
const groupSubjects = new Map();

// ZAELAR-PATCH (V2-714): the ADDRESS BOOK. WhatsApp has no "give me every contact" call — Baileys learns
// them from the socket (`contacts.upsert` on the linked device's initial sync, `contacts.update` after
// that) and this is where they accumulate so `GET /contacts` can hand over what is known SO FAR. That
// "so far" is reported honestly: a count presented as a total when it is not is a promise the card cannot
// keep. Keyed by JID so an update refines the row rather than adding a second one.
const contactBook = new Map();

function rememberContact(c) {
  if (!c || !c.id) return;
  const prev = contactBook.get(c.id) || {};
  const next = { ...prev };
  for (const k of ['id', 'lid', 'phoneNumber', 'name', 'notify', 'verifiedName', 'imgUrl', 'status']) {
    if (c[k] !== undefined && c[k] !== null && c[k] !== '') next[k] = c[k];
  }
  contactBook.set(c.id, next);
}
// ZAELAR-PATCH (chat list): the CHATS this device knows, for a list of conversations that does not depend on
// what triage kept. WhatsApp tells a linked device its chats ONCE, in the history sync right after pairing
// (`messaging-history.set`); after that it only reports changes. So the book is persisted next to the session:
// a bridge restart that started empty would show an empty list until each chat happened to move again.
// Groups are also seeded from `groupFetchAllParticipating` on connect, which WhatsApp does answer at any time.
const CHAT_BOOK_FILE = path.join(SESSION_DIR, 'zaelar-chats.json');
const chatBook = new Map();
try {
  for (const r of JSON.parse(readFileSync(CHAT_BOOK_FILE, 'utf8')) || []) {
    if (r && r.id) chatBook.set(r.id, r);
  }
} catch {}
let chatBookTimer = null;
let groupsSeeded = false;

function saveChatBookSoon() {
  if (chatBookTimer) return;
  chatBookTimer = setTimeout(() => {
    chatBookTimer = null;
    try { writeFileSync(CHAT_BOOK_FILE, JSON.stringify(Array.from(chatBook.values()))); }
    catch (err) { console.error('[bridge] chat book not saved:', err.message); }
  }, 2000);
}

function isListedChat(id) {
  return !!id && !id.includes('status') && !id.endsWith('@newsletter') && !id.endsWith('@broadcast');
}

// `unread` is ABSOLUTE (history sync, read marks); `unreadDelta` is what a live message adds.
function rememberChat(id, patch) {
  if (!isListedChat(id)) return;
  const prev = chatBook.get(id) || { id, isGroup: id.endsWith('@g.us') };
  const next = { ...prev };
  for (const k of ['name', 'archived', 'pinned', 'muted']) {
    if (patch[k] !== undefined && patch[k] !== null && patch[k] !== '') next[k] = patch[k];
  }
  if (typeof patch.unread === 'number') next.unread = Math.max(0, patch.unread);
  if (typeof patch.unreadDelta === 'number') next.unread = Math.max(0, (next.unread || 0) + patch.unreadDelta);
  // The last message only moves FORWARD: a history page arriving after a live message must not repaint the row
  // with something older.
  const ts = Number(patch.ts) || 0;
  if (ts && ts >= (Number(prev.ts) || 0)) {
    next.ts = ts;
    if (patch.preview !== undefined) next.preview = String(patch.preview || '').slice(0, 160);
    if (patch.mediaType !== undefined) next.mediaType = patch.mediaType || '';
    if (patch.fromMe !== undefined) next.fromMe = !!patch.fromMe;
    if (patch.lastId) {
      // The whole last message, so a chat opened from the list can show it: the phone answers a history
      // request with what came BEFORE the anchor, never the anchor itself. Not sent with /chats pages.
      next.lastId = patch.lastId;
      next.last = { body: String(patch.preview || '').slice(0, 4000), mediaType: patch.mediaType || '',
                    fromMe: !!patch.fromMe, sender: patch.sender || '', ts };
    }
  }
  chatBook.set(id, next);
  saveChatBookSoon();
}

// ZAELAR-PATCH: a message timestamp as unix seconds. History-sync messages carry protobuf Longs ({low, high}),
// which JSON turns into an object the Python side cannot read — it fell back to «now» and filed two-year-old
// messages as just received.
function tsNum(v) {
  if (typeof v === 'number') return v;
  if (v && typeof v.toNumber === 'function') return v.toNumber();
  if (v && typeof v === 'object' && 'low' in v) return (v.low >>> 0) + (v.high >>> 0) * 4294967296;
  return Number(v) || 0;
}

// Text and media kind of one message WITHOUT downloading anything: what a list row or a scrollback line needs.
function messageGist(msg) {
  const c = getMessageContent(msg);
  const text = c.conversation || c.extendedTextMessage?.text || '';
  for (const [key, kind] of [['imageMessage', 'image'], ['videoMessage', 'video'], ['pttMessage', 'ptt'],
                             ['audioMessage', 'audio'], ['documentMessage', 'document'],
                             ['stickerMessage', 'sticker']]) {
    if (c[key]) {
      const mediaType = key === 'audioMessage' && c[key].ptt ? 'ptt' : kind;
      return { body: c[key].caption || '', mediaType };
    }
  }
  return { body: text, mediaType: '' };
}

async function seedGroups() {
  if (groupsSeeded || !sock) return;
  try {
    const all = await sock.groupFetchAllParticipating();
    for (const g of Object.values(all || {})) {
      if (!g?.id) continue;
      if (g.subject) groupSubjects.set(g.id, g.subject);
      rememberChat(g.id, { name: g.subject || '' });
    }
    groupsSeeded = true;
  } catch (err) {
    console.error('[bridge] group list not fetched:', err.message);
  }
}

async function groupSubject(chatId) {
  if (groupSubjects.has(chatId)) return groupSubjects.get(chatId);
  try {
    const md = await sock.groupMetadata(chatId);
    const subject = (md && md.subject) || '';
    if (subject) groupSubjects.set(chatId, subject);
    return subject;
  } catch { return ''; }
}
let connectionState = 'disconnected';
let currentQR = null;  // ZAELAR-PATCH: latest pairing QR as a data-URI PNG (null once connected)

async function startSocket() {
  const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);
  const { version } = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    version,
    auth: state,
    logger,
    printQRInTerminal: false,
    // ZAELAR-PATCH: the name the operator's phone shows for this linked device («Google Chrome (Zaelar Agent)»).
    browser: [DEVICE_NAME, 'Chrome', '120.0'],
    syncFullHistory: false,
    markOnlineOnConnect: false,
    // Required for Baileys 7.x: without this, incoming messages that need
    // E2EE session re-establishment are silently dropped (msg.message === null)
    getMessage: async (key) => {
      // We don't maintain a message store, so return a placeholder.
      // This is enough for Baileys to complete the retry handshake.
      return { conversation: '' };
    },
  });

  sock.ev.on('creds.update', () => { saveCreds(); lidToPhone = buildLidMap(); });

  sock.ev.on('connection.update', (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log('\n📱 Scan this QR code with WhatsApp on your phone:\n');
      qrcode.generate(qr, { small: true });
      console.log('\nWaiting for scan...\n');
      // ZAELAR-PATCH: also expose the QR as a data-URI PNG so the zaelar
      // widget can render it in the canvas (the operator scans it there, not in a terminal).
      QRCode.toDataURL(qr, { margin: 1, width: 320 })
        .then((uri) => { currentQR = uri; })
        .catch(() => {});
    }

    if (connection === 'close') {
      const reason = new Boom(lastDisconnect?.error)?.output?.statusCode;
      connectionState = 'disconnected';

      if (reason === DisconnectReason.loggedOut) {
        console.log('❌ Logged out. Delete session and restart to re-authenticate.');
        process.exit(1);
      } else {
        // 515 = restart requested (common after pairing). Always reconnect.
        if (reason === 515) {
          console.log('↻ WhatsApp requested restart (code 515). Reconnecting...');
        } else {
          console.log(`⚠️  Connection closed (reason: ${reason}). Reconnecting in 3s...`);
        }
        setTimeout(startSocket, reason === 515 ? 1000 : 3000);
      }
    } else if (connection === 'open') {
      connectionState = 'connected';
      currentQR = null;  // ZAELAR-PATCH: clear the QR once paired
      console.log('✅ WhatsApp connected!');
      seedGroups();      // ZAELAR-PATCH (chat list)
      if (PAIR_ONLY) {
        console.log('✅ Pairing complete. Credentials saved.');
        // Give Baileys a moment to flush creds, then exit cleanly
        setTimeout(() => process.exit(0), 2000);
      }
    }
  });

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    // In self-chat mode, your own messages commonly arrive as 'append' rather
    // than 'notify'. Accept both and filter agent echo-backs below.
    if (type !== 'notify' && type !== 'append') return;

    const botIds = Array.from(new Set([
      normalizeWhatsAppId(sock.user?.id),
      normalizeWhatsAppId(sock.user?.lid),
    ].filter(Boolean)));

    for (const msg of messages) {
      if (!msg.message) continue;

      const chatId = msg.key.remoteJid;
      // ZAELAR-PATCH (chat list): every real message moves its chat, groups and our own included — the filters
      // below decide what is FORWARDED, not what the operator's chat list shows.
      {
        const g = messageGist(msg);
        if (g.body || g.mediaType) {
          rememberChat(chatId, {
            ts: tsNum(msg.messageTimestamp), preview: g.body, mediaType: g.mediaType, fromMe: !!msg.key.fromMe,
            lastId: msg.key.id, sender: msg.key.fromMe ? '' : (msg.pushName || ''),
            name: !chatId.endsWith('@g.us') && !msg.key.fromMe ? msg.pushName : undefined,
          });
        }
      }
      if (WHATSAPP_DEBUG) {
        try {
          console.log(JSON.stringify({
            event: 'upsert', type,
            fromMe: !!msg.key.fromMe, chatId,
            senderId: msg.key.participant || chatId,
            messageKeys: Object.keys(msg.message || {}),
          }));
        } catch {}
      }
      const senderId = msg.key.participant || chatId;
      const isGroup = chatId.endsWith('@g.us');
      const senderNumber = senderId.replace(/@.*/, '');

      // Handle fromMe messages based on mode
      if (msg.key.fromMe) {
        if (isGroup || chatId.includes('status')) continue;

        if (WHATSAPP_MODE === 'bot') {
          // Bot mode: separate number. ALL fromMe are echo-backs of our own replies — skip.
          continue;
        }

        // ZAELAR-PATCH (V2-546): observe mode now DOES forward our own outgoing messages, tagged
        // `direction:'out'`. Baileys has always delivered them — a message sent from the operator's phone
        // arrives here as an upsert with fromMe:true — and the first version of this patch dropped them on the floor, which is why a
        // chat he had already answered elsewhere kept looking pending in the widget. They never reach triage
        // or notification on the Python side: they join the conversation and mark that chat as seen.
        // Groups and status broadcasts stay out, as before (the `continue` above).
        if (WHATSAPP_MODE !== 'observe') {
          // Self-chat mode: only allow messages in the user's own self-chat
          // WhatsApp now uses LID (Linked Identity Device) format: 67427329167522@lid
          // AND classic format: 34600000000@s.whatsapp.net
          // sock.user has both: { id: "number:10@s.whatsapp.net", lid: "lid_number:10@lid" }
          const myNumber = (sock.user?.id || '').replace(/:.*@/, '@').replace(/@.*/, '');
          const myLid = (sock.user?.lid || '').replace(/:.*@/, '@').replace(/@.*/, '');
          const chatNumber = chatId.replace(/@.*/, '');
          const isSelfChat = (myNumber && chatNumber === myNumber) || (myLid && chatNumber === myLid);
          if (!isSelfChat) continue;
        }
      }

      // Handle !fromMe messages (from other people) based on mode.
      // Self-chat mode only responds to the user's own messages to
      // themselves — stranger DMs / group pings must never reach the
      // Python gateway, otherwise a pairing-code reply fires in response
      // to arbitrary incoming messages (#8389).
      if (!msg.key.fromMe) {
        // ZAELAR-PATCH: observe mode forwards ALL inbound to /messages
        // (no self-chat filter, no allowlist) so zaelar can triage the full stream.
        // The bridge never auto-replies; suppression of responses is zaelar-side
        // (it simply does not call POST /send in read-only + mark-read mode).
        if (WHATSAPP_MODE !== 'observe') {
          if (WHATSAPP_MODE === 'self-chat') {
            try {
              console.log(JSON.stringify({
                event: 'ignored',
                reason: 'self_chat_mode_rejects_non_self',
                chatId,
                senderId,
              }));
            } catch {}
            continue;
          }
          if (!matchesAllowedUser(senderId, ALLOWED_USERS, SESSION_DIR)) {
            try {
              console.log(JSON.stringify({
                event: 'ignored',
                reason: 'allowlist_mismatch',
                chatId,
                senderId,
              }));
            } catch {}
            continue;
          }
        }
      }

      const messageContent = getMessageContent(msg);
      const contextInfo = getContextInfo(messageContent);
      const mentionedIds = Array.from(new Set((contextInfo?.mentionedJid || []).map(normalizeWhatsAppId).filter(Boolean)));
      const quotedMessageId = contextInfo?.stanzaId || null;
      const quotedParticipant = normalizeWhatsAppId(contextInfo?.participant || '') || null;
      const quotedRemoteJid = normalizeWhatsAppId(contextInfo?.remoteJid || '') || null;
      const hasQuotedMessage = !!contextInfo?.quotedMessage;

      // Extract message body
      let body = '';
      let hasMedia = false;
      let mediaType = '';
      const mediaUrls = [];

      if (messageContent.conversation) {
        body = messageContent.conversation;
      } else if (messageContent.extendedTextMessage?.text) {
        body = messageContent.extendedTextMessage.text;
      } else if (messageContent.imageMessage) {
        body = messageContent.imageMessage.caption || '';
        hasMedia = true;
        mediaType = 'image';
        try {
          const buf = await downloadMediaMessage(msg, 'buffer', {}, { logger, reuploadRequest: sock.updateMediaMessage });
          const mime = messageContent.imageMessage.mimetype || 'image/jpeg';
          const extMap = { 'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp', 'image/gif': '.gif' };
          const ext = extMap[mime] || '.jpg';
          mkdirSync(IMAGE_CACHE_DIR, { recursive: true });
          const filePath = path.join(IMAGE_CACHE_DIR, `img_${randomBytes(6).toString('hex')}${ext}`);
          writeFileSync(filePath, buf);
          mediaUrls.push(filePath);
        } catch (err) {
          console.error('[bridge] Failed to download image:', err.message);
        }
      } else if (messageContent.videoMessage) {
        body = messageContent.videoMessage.caption || '';
        hasMedia = true;
        mediaType = 'video';
        try {
          const buf = await downloadMediaMessage(msg, 'buffer', {}, { logger, reuploadRequest: sock.updateMediaMessage });
          const mime = messageContent.videoMessage.mimetype || 'video/mp4';
          const ext = mime.includes('mp4') ? '.mp4' : '.mkv';
          mkdirSync(DOCUMENT_CACHE_DIR, { recursive: true });
          const filePath = path.join(DOCUMENT_CACHE_DIR, `vid_${randomBytes(6).toString('hex')}${ext}`);
          writeFileSync(filePath, buf);
          mediaUrls.push(filePath);
        } catch (err) {
          console.error('[bridge] Failed to download video:', err.message);
        }
      } else if (messageContent.audioMessage || messageContent.pttMessage) {
        hasMedia = true;
        mediaType = messageContent.pttMessage ? 'ptt' : 'audio';
        try {
          const audioMsg = messageContent.pttMessage || messageContent.audioMessage;
          const buf = await downloadMediaMessage(msg, 'buffer', {}, { logger, reuploadRequest: sock.updateMediaMessage });
          const mime = audioMsg.mimetype || 'audio/ogg';
          const ext = mime.includes('ogg') ? '.ogg' : mime.includes('mp4') ? '.m4a' : '.ogg';
          mkdirSync(AUDIO_CACHE_DIR, { recursive: true });
          const filePath = path.join(AUDIO_CACHE_DIR, `aud_${randomBytes(6).toString('hex')}${ext}`);
          writeFileSync(filePath, buf);
          mediaUrls.push(filePath);
        } catch (err) {
          console.error('[bridge] Failed to download audio:', err.message);
        }
      } else if (messageContent.documentMessage) {
        body = messageContent.documentMessage.caption || '';
        hasMedia = true;
        mediaType = 'document';
        const fileName = messageContent.documentMessage.fileName || 'document';
        try {
          const buf = await downloadMediaMessage(msg, 'buffer', {}, { logger, reuploadRequest: sock.updateMediaMessage });
          mkdirSync(DOCUMENT_CACHE_DIR, { recursive: true });
          const safeFileName = path.basename(fileName).replace(/[^a-zA-Z0-9._-]/g, '_');
          const filePath = path.join(DOCUMENT_CACHE_DIR, `doc_${randomBytes(6).toString('hex')}_${safeFileName}`);
          writeFileSync(filePath, buf);
          mediaUrls.push(filePath);
        } catch (err) {
          console.error('[bridge] Failed to download document:', err.message);
        }
      }

      // For media without caption, use a placeholder so the API message is never empty
      if (hasMedia && !body) {
        body = `[${mediaType} received]`;
      }

      // Ignore the agent's own reply messages in self-chat mode to avoid loops.
      // ZAELAR-PATCH (V2-546): NOT in observe mode. There the loop is impossible by construction — an outgoing
      // message is published on a topic that feeds neither triage nor any reply path — and a reply the operator
      // dictated to zaelar is precisely something he should see in the conversation afterwards.
      if (WHATSAPP_MODE !== 'observe' &&
          msg.key.fromMe && ((REPLY_PREFIX && body.startsWith(REPLY_PREFIX)) || recentlySentIds.has(msg.key.id))) {
        if (WHATSAPP_DEBUG) {
          try { console.log(JSON.stringify({ event: 'ignored', reason: 'agent_echo', chatId, messageId: msg.key.id })); } catch {}
        }
        continue;
      }

      // Skip empty messages
      if (!body && !hasMedia) {
        if (WHATSAPP_DEBUG) {
          try { 
            console.log(JSON.stringify({ event: 'ignored', reason: 'empty', chatId, messageKeys: Object.keys(msg.message || {}) })); 
          } catch (err) {
            console.error('Failed to log empty message event:', err);
          }
        }
        continue;
      }

      const event = {
        messageId: msg.key.id,
        chatId,
        senderId,
        senderName: msg.pushName || senderNumber,
        // ZAELAR-PATCH (V2-645): the group's real subject; the id digits only as the last resort.
        chatName: isGroup ? ((await groupSubject(chatId)) || chatId.split('@')[0]) : (msg.pushName || senderNumber),
        isGroup,
        body,
        hasMedia,
        mediaType,
        mediaUrls,
        mentionedIds,
        quotedMessageId,
        quotedParticipant,
        quotedRemoteJid,
        hasQuotedMessage,
        botIds,
        timestamp: tsNum(msg.messageTimestamp),
        // ZAELAR-PATCH (V2-546): which WAY this message went. The Python side routes on it — "in" is triaged
        // and may interrupt the operator, "out" only joins the conversation and marks the chat as seen.
        direction: msg.key.fromMe ? 'out' : 'in',
        // ZAELAR-PATCH (V2-546): this is scrollback the phone sent because we asked, not something that just
        // happened. It must never be triaged or announced.
        history: type === 'append' && wantsHistory(chatId),
      };

      messageQueue.push(event);
      if (messageQueue.length > MAX_QUEUE_SIZE) {
        messageQueue.shift();
      }
    }
  });

  // ZAELAR-PATCH (V2-546): the operator opened a chat on his PHONE. WhatsApp syncs that to every linked device,
  // so Baileys sees the chat's unread counter drop — this is the only signal a linked client gets for "read
  // elsewhere", and nothing was listening to it. Queued as a read event rather than a message; the Python side
  // clears that chat's pending items without telling WhatsApp anything back (it is the one that just told US).
  //
  // It is a WHOLE-CHAT signal: WhatsApp reports the counter, not a per-message watermark, so this is only
  // emitted when the counter reaches zero — a partial drop cannot say WHICH messages were read, and guessing
  // would hide mail the operator has not seen.
  // ZAELAR-PATCH (V2-714): both shapes. `contacts.upsert` is the bulk the device sends on sync;
  // `contacts.update` is the drip afterwards, and it is PARTIAL — merging rather than replacing is what
  // keeps a name we already had from being wiped by an update that only carries a status.
  sock.ev.on('contacts.upsert', (rows) => { (rows || []).forEach(rememberContact); });
  sock.ev.on('contacts.update', (rows) => { (rows || []).forEach(rememberContact); });

  // ZAELAR-PATCH (chat list): the history sync. Right after pairing it carries the device's chats (absolute
  // unread counters, names, archive/pin state); later, with syncType ON_DEMAND, it is how the PHONE answers
  // `fetchMessageHistory` — those messages never arrive as upserts, so «load previous» was only ever an
  // acknowledgement until this listened. On-demand messages are forwarded as `history:true` scrollback.
  sock.ev.on('messaging-history.set', ({ chats, contacts, messages, syncType }) => {
    console.log(JSON.stringify({ event: 'history', syncType, chats: (chats || []).length,
                                 messages: (messages || []).length }));
    (contacts || []).forEach(rememberContact);
    for (const c of chats || []) {
      const last = c.messages?.[0]?.message;
      const g = last ? messageGist(last) : null;
      rememberChat(c.id, {
        name: c.name || c.displayName || '', unread: typeof c.unreadCount === 'number' ? c.unreadCount : undefined,
        archived: c.archived === true ? true : undefined, pinned: c.pinned ? true : undefined,
        muted: c.muteEndTime && Number(c.muteEndTime) > Date.now() / 1000 ? true : undefined,
        ts: tsNum(c.conversationTimestamp) || (last ? tsNum(last.messageTimestamp) : 0) || 0,
        preview: g ? g.body : undefined, mediaType: g ? g.mediaType : undefined,
        fromMe: last ? !!last.key?.fromMe : undefined, lastId: last?.key?.id, sender: last?.pushName || '',
      });
    }
    if (syncType !== 6) {
      // ZAELAR-PATCH: the sync the phone sends at PAIRING (bootstrap / recent) — the account's past as WhatsApp
      // offers it, once, with no notification per page. Its messages go to the archive (GET /sync), never to the
      // inbox or the conversations on screen.
      for (const m of messages || []) {
        const chatId = m?.key?.remoteJid;
        if (!m?.message || !isListedChat(chatId)) continue;
        const g = messageGist(m);
        if (!g.body && !g.mediaType) continue;
        syncQueue.push({
          messageId: m.key.id, chatId, isGroup: chatId.endsWith('@g.us'),
          chatName: chatId.endsWith('@g.us') ? (groupSubjects.get(chatId) || '') : (chatBook.get(chatId)?.name || ''),
          senderName: m.key.fromMe ? '' : (m.pushName || (m.key.participant || chatId).replace(/@.*/, '')),
          body: g.body || `[${g.mediaType} received]`, mediaType: g.mediaType,
          timestamp: tsNum(m.messageTimestamp), direction: m.key.fromMe ? 'out' : 'in',
        });
      }
      if (syncQueue.length > SYNC_QUEUE_MAX) syncQueue.splice(0, syncQueue.length - SYNC_QUEUE_MAX);
      return;
    }
    for (const m of messages || []) {
      const chatId = m?.key?.remoteJid;
      if (!m?.message || !isListedChat(chatId)) continue;
      const g = messageGist(m);
      if (!g.body && !g.mediaType) continue;
      const isGroup = chatId.endsWith('@g.us');
      const senderId = m.key.participant || chatId;
      messageQueue.push({
        messageId: m.key.id, chatId, senderId,
        senderName: m.pushName || senderId.replace(/@.*/, ''),
        chatName: isGroup ? (groupSubjects.get(chatId) || chatId.split('@')[0]) : (chatBook.get(chatId)?.name || ''),
        isGroup, body: g.body || `[${g.mediaType} received]`, hasMedia: !!g.mediaType, mediaType: g.mediaType,
        mediaUrls: [], mentionedIds: [], botIds: [], timestamp: tsNum(m.messageTimestamp),
        direction: m.key.fromMe ? 'out' : 'in', history: true,
      });
      if (messageQueue.length > MAX_QUEUE_SIZE) messageQueue.shift();
    }
  });

  sock.ev.on('chats.upsert', (rows) => {
    for (const c of rows || []) rememberChat(c.id, { name: c.name || '', ts: tsNum(c.conversationTimestamp) });
  });

  sock.ev.on('chats.update', (updates) => {
    for (const u of updates || []) {
      const chatId = u?.id;
      if (!chatId || chatId.includes('status')) continue;
      // ZAELAR-PATCH (chat list): a live message reports +1 here; a read mark reports 0, «mark as unread» -1.
      if (u.unreadCount === 0) rememberChat(chatId, { unread: 0 });
      else if (u.unreadCount === -1) rememberChat(chatId, { unread: Math.max(1, chatBook.get(chatId)?.unread || 0) });
      else if (typeof u.unreadCount === 'number' && u.unreadCount > 0) rememberChat(chatId, { unreadDelta: u.unreadCount });
      if (u.archived !== undefined || u.pinned !== undefined) {
        rememberChat(chatId, { archived: u.archived === true ? true : undefined, pinned: u.pinned ? true : undefined });
        const row = chatBook.get(chatId);
        if (row && u.archived === false) { delete row.archived; saveChatBookSoon(); }
      }
      const unread = u?.unreadCount;
      if (unread === 0 || unread === null) {
        readQueue.push({ chatId, at: Math.floor(Date.now() / 1000) });
        if (readQueue.length > MAX_QUEUE_SIZE) readQueue.shift();
      }
    }
  });
}

// HTTP server
const app = express();
app.use(express.json());

// Host-header validation — defends against DNS rebinding.
// The bridge binds loopback-only (127.0.0.1) but a victim browser on
// the same machine could be tricked into fetching from an attacker
// hostname that TTL-flips to 127.0.0.1. Reject any request whose Host
// header doesn't resolve to a loopback alias.
// See GHSA-ppp5-vxwm-4cf7.
const _ACCEPTED_HOST_VALUES = new Set([
  'localhost',
  '127.0.0.1',
  '[::1]',
  '::1',
]);

app.use((req, res, next) => {
  const raw = (req.headers.host || '').trim();
  if (!raw) {
    return res.status(400).json({ error: 'Missing Host header' });
  }
  // Strip port suffix: "localhost:3000" → "localhost"
  const hostOnly = (raw.includes(':')
    ? raw.substring(0, raw.lastIndexOf(':'))
    : raw
  ).replace(/^\[|\]$/g, '').toLowerCase();
  if (!_ACCEPTED_HOST_VALUES.has(hostOnly)) {
    return res.status(400).json({
      error: 'Invalid Host header. Bridge accepts loopback hosts only.',
    });
  }
  next();
});

// Poll for new messages (long-poll style)
app.get('/messages', (req, res) => {
  const msgs = messageQueue.splice(0, messageQueue.length);
  res.json(msgs);
});

// ZAELAR-PATCH (V2-714): the address book known so far, plus the groups we have a subject for.
//
// NOT drained like /messages: this is a SNAPSHOT of what the socket has taught us, and the widget's import
// is idempotent (it never overwrites a row that already exists), so handing the same rows twice costs
// nothing and losing them to a drain would cost the whole book.
app.get('/contacts', (req, res) => {
  res.json({
    contacts: Array.from(contactBook.values()),
    groups: Array.from(groupSubjects.entries()).map(([id, subject]) => ({ id, subject })),
    // What "partial" means here: WhatsApp cannot be ASKED for everything. Empty is not proof of an empty
    // address book — it is proof the device has not synced one yet.
    partial: true,
  });
});

// ZAELAR-PATCH (chat list): one page of the chat book, newest first. `before` (unix seconds) walks backwards;
// `kind` is person | group. A chat WhatsApp never told this device about cannot be listed: `complete` only
// means the book has nothing older, and the book itself starts at pairing.
app.get('/chats', (req, res) => {
  const before = Number(req.query.before) || Infinity;
  const limit = Math.max(1, Math.min(2000, Number(req.query.limit) || 20));
  const kind = String(req.query.kind || '');
  const rows = Array.from(chatBook.values())
    .filter((c) => (Number(c.ts) || 0) < before)
    .filter((c) => !kind || (kind === 'group' ? c.isGroup : !c.isGroup))
    .sort((a, b) => (Number(b.ts) || 0) - (Number(a.ts) || 0));
  const page = rows.slice(0, limit).map((c) => {
    const contact = contactBook.get(c.id) || {};
    const name = c.isGroup ? (groupSubjects.get(c.id) || c.name)
                           : (contact.name || c.name || contact.notify || contact.verifiedName);
    const { last, ...row } = c;
    // ZAELAR-PATCH (V2-850): a @lid chat carries the phone its session mapping knows — the key that links it to
    // the person he already has in his address book (contacts are linked by phone or email, never by name).
    const lid = c.id.endsWith('@lid') ? c.id.split('@')[0] : '';
    const phoneNumber = contact.phoneNumber || (lid && lidToPhone[lid]) || '';
    return { ...row, name: name || c.id.split('@')[0], ...(phoneNumber ? { phoneNumber } : {}) };
  });
  res.json({ chats: page, complete: rows.length <= limit, known: chatBook.size });
});

// ZAELAR-PATCH (groups): create a group with these participants, as the phone's «New group» does.
app.post('/group', async (req, res) => {
  if (!sock || connectionState !== 'connected') {
    return res.status(503).json({ error: 'Not connected to WhatsApp' });
  }
  const { subject, participants } = req.body || {};
  const people = (participants || []).filter((p) => typeof p === 'string' && p.includes('@'));
  if (!subject || !people.length) {
    return res.status(400).json({ error: 'subject and at least one participant are required' });
  }
  try {
    const md = await sock.groupCreate(String(subject).slice(0, 100), people);
    groupSubjects.set(md.id, md.subject || subject);
    rememberChat(md.id, { name: md.subject || subject, ts: Math.floor(Date.now() / 1000) });
    res.json({ id: md.id, subject: md.subject || subject });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ZAELAR-PATCH: up to 2000 messages of the pairing history sync per call, oldest first.
app.get('/sync', (req, res) => {
  res.json(syncQueue.splice(0, 2000));
});

// ZAELAR-PATCH (V2-546): chats read on another device, since the last poll.
app.get('/reads', (req, res) => {
  res.json(readQueue.splice(0, readQueue.length));
});

// ZAELAR-PATCH (V2-546): OLDER messages of one chat ("load previous"), on demand.
//
// This is the honest one of the three platforms. WhatsApp keeps history on the PHONE, not on a server: a linked
// client can only ASK the phone to send it, and whether it answers depends on the phone being reachable and on
// what it still holds. So this endpoint may legitimately return an empty list, and says so with `available`
// instead of pretending the conversation starts where our copy does.
app.post('/history', async (req, res) => {
  if (!sock || connectionState !== 'connected') {
    return res.status(503).json({ error: 'Not connected to WhatsApp' });
  }
  const { chatId, oldestId, oldestTs, limit, oldestFromMe, includeAnchor } = req.body || {};
  if (!chatId || !oldestId) {
    return res.status(400).json({ error: 'chatId and oldestId are required' });
  }
  if (typeof sock.fetchMessageHistory !== 'function') {
    return res.json({ available: false, requested: 0,
                      error: 'this Baileys build has no fetchMessageHistory' });
  }
  try {
    const count = Math.max(1, Math.min(100, Number(limit) || 30));
    historyWanted.set(chatId, Date.now() + HISTORY_WINDOW_MS);
    const book = chatBook.get(chatId);
    if (includeAnchor && book?.last && book.lastId === oldestId) {
      const isGroup = chatId.endsWith('@g.us');
      messageQueue.push({
        messageId: oldestId, chatId, senderId: chatId, senderName: book.last.sender || book.name || '',
        chatName: isGroup ? (groupSubjects.get(chatId) || book.name || '') : (book.name || ''), isGroup,
        body: book.last.body || `[${book.last.mediaType} received]`, hasMedia: !!book.last.mediaType,
        mediaType: book.last.mediaType, mediaUrls: [], mentionedIds: [], botIds: [],
        timestamp: book.last.ts, direction: book.last.fromMe ? 'out' : 'in', history: true,
      });
    }
    // The phone answers ASYNCHRONOUSLY, as ordinary upserts of type 'append' — they land in messageQueue
    // through the handler above and reach the widget on the next poll. There is nothing to return here but
    // the acknowledgement that we asked.
    // ZAELAR-PATCH: the phone expects the anchor's time in MILLISECONDS; callers speak unix seconds.
    const ts = Number(oldestTs) || 0;
    await sock.fetchMessageHistory(count, { remoteJid: chatId, id: oldestId, fromMe: !!oldestFromMe },
                                   ts && ts < 1e12 ? Math.round(ts * 1000) : ts);
    res.json({ available: true, requested: count });
  } catch (err) {
    res.status(500).json({ available: false, error: err.message });
  }
});

// Send a message
app.post('/send', async (req, res) => {
  if (!sock || connectionState !== 'connected') {
    return res.status(503).json({ error: 'Not connected to WhatsApp' });
  }

  const { chatId, message, replyTo } = req.body;
  if (!chatId || !message) {
    return res.status(400).json({ error: 'chatId and message are required' });
  }

  try {
    const chunks = splitLongMessage(formatOutgoingMessage(message));
    const messageIds = [];
    for (let i = 0; i < chunks.length; i += 1) {
      const sent = await sendWithTimeout(chatId, { text: chunks[i] });
      trackSentMessageId(sent);
      if (sent?.key?.id) messageIds.push(sent.key.id);
      if (chunks.length > 1 && i < chunks.length - 1) {
        await sleep(CHUNK_DELAY_MS);
      }
    }

    res.json({
      success: true,
      messageId: messageIds[messageIds.length - 1],
      messageIds,
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Edit a previously sent message
app.post('/edit', async (req, res) => {
  if (!sock || connectionState !== 'connected') {
    return res.status(503).json({ error: 'Not connected to WhatsApp' });
  }

  const { chatId, messageId, message } = req.body;
  if (!chatId || !messageId || !message) {
    return res.status(400).json({ error: 'chatId, messageId, and message are required' });
  }

  try {
    const key = { id: messageId, fromMe: true, remoteJid: chatId };
    const chunks = splitLongMessage(formatOutgoingMessage(message));
    const messageIds = [];

    await sendWithTimeout(chatId, { text: chunks[0], edit: key });
    if (chunks.length > 1) {
      for (let i = 1; i < chunks.length; i += 1) {
        const sent = await sendWithTimeout(chatId, { text: chunks[i] });
        trackSentMessageId(sent);
        if (sent?.key?.id) messageIds.push(sent.key.id);
        if (i < chunks.length - 1) {
          await sleep(CHUNK_DELAY_MS);
        }
      }
    }

    res.json({ success: true, messageIds });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// MIME type map and media type inference for /send-media
const MIME_MAP = {
  jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png',
  webp: 'image/webp', gif: 'image/gif',
  mp4: 'video/mp4', mov: 'video/quicktime', avi: 'video/x-msvideo',
  mkv: 'video/x-matroska', '3gp': 'video/3gpp',
  pdf: 'application/pdf',
  doc: 'application/msword',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
};

function inferMediaType(ext) {
  if (['jpg', 'jpeg', 'png', 'webp', 'gif'].includes(ext)) return 'image';
  if (['mp4', 'mov', 'avi', 'mkv', '3gp'].includes(ext)) return 'video';
  if (['ogg', 'opus', 'mp3', 'wav', 'm4a'].includes(ext)) return 'audio';
  return 'document';
}

// Send media (image, video, document) natively
app.post('/send-media', async (req, res) => {
  if (!sock || connectionState !== 'connected') {
    return res.status(503).json({ error: 'Not connected to WhatsApp' });
  }

  const { chatId, filePath, mediaType, caption, fileName } = req.body;
  if (!chatId || !filePath) {
    return res.status(400).json({ error: 'chatId and filePath are required' });
  }

  try {
    if (!existsSync(filePath)) {
      return res.status(404).json({ error: `File not found: ${filePath}` });
    }

    const buffer = readFileSync(filePath);
    const ext = filePath.toLowerCase().split('.').pop();
    const type = mediaType || inferMediaType(ext);
    let msgPayload;

    switch (type) {
      case 'image':
        msgPayload = { image: buffer, caption: caption || undefined, mimetype: MIME_MAP[ext] || 'image/jpeg' };
        break;
      case 'video':
        msgPayload = { video: buffer, caption: caption || undefined, mimetype: MIME_MAP[ext] || 'video/mp4' };
        break;
      case 'audio': {
        // WhatsApp only renders a native voice bubble (ptt) when the file is ogg/opus.
        // If the caller passes mp3, wav, m4a etc. (e.g. from Edge TTS / NeuTTS),
        // silently convert to ogg/opus via ffmpeg so ptt is always honoured.
        let audioBuffer = buffer;
        let audioExt = ext;
        const needsConversion = !['ogg', 'opus'].includes(ext);
        let tmpPath = null;
        if (needsConversion) {
          tmpPath = path.join(tmpdir(), `zaelar_voice_${randomBytes(6).toString('hex')}.ogg`);
          try {
            execSync(
              `ffmpeg -y -i ${JSON.stringify(filePath)} -ar 48000 -ac 1 -c:a libopus ${JSON.stringify(tmpPath)}`,
              { timeout: 30000, stdio: 'pipe' }
            );
            audioBuffer = readFileSync(tmpPath);
            audioExt = 'ogg';
          } catch (convErr) {
            // ffmpeg not available or conversion failed — fall back to original format
            console.warn('[bridge] ffmpeg conversion failed, sending as file attachment:', convErr.message);
          } finally {
            try { if (tmpPath && existsSync(tmpPath)) unlinkSync(tmpPath); } catch (_) {}
          }
        }
        const audioMime = (audioExt === 'ogg' || audioExt === 'opus') ? 'audio/ogg; codecs=opus' : 'audio/mpeg';
        msgPayload = { audio: audioBuffer, mimetype: audioMime, ptt: audioExt === 'ogg' || audioExt === 'opus' };
        break;
      }
      case 'document':
      default:
        msgPayload = {
          document: buffer,
          fileName: fileName || path.basename(filePath),
          caption: caption || undefined,
          mimetype: MIME_MAP[ext] || 'application/octet-stream',
        };
        break;
    }

    const sent = await sendWithTimeout(chatId, msgPayload);

    trackSentMessageId(sent);

    res.json({ success: true, messageId: sent?.key?.id });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Typing indicator
app.post('/typing', async (req, res) => {
  if (!sock || connectionState !== 'connected') {
    return res.status(503).json({ error: 'Not connected' });
  }

  const { chatId } = req.body;
  if (!chatId) return res.status(400).json({ error: 'chatId required' });

  try {
    await sock.sendPresenceUpdate('composing', chatId);
    res.json({ success: true });
  } catch (err) {
    res.json({ success: false });
  }
});

// ZAELAR-PATCH: mark conversation(s) as read. Upstream has no such
// endpoint. Accepts { chatId, messageId, senderId? } or { keys: [{chatId,
// messageId, senderId?}, ...] } and calls sock.readMessages() with reconstructed
// Baileys message keys (remoteJid = chatId, id = messageId, participant = senderId
// for group messages). zaelar calls this ONLY for messages already surfaced in a
// digest, so the operator's unread state reflects "already triaged".
app.post('/mark-read', async (req, res) => {
  if (!sock || connectionState !== 'connected') {
    return res.status(503).json({ error: 'Not connected' });
  }

  const raw = Array.isArray(req.body?.keys)
    ? req.body.keys
    : (req.body?.chatId ? [req.body] : []);
  if (raw.length === 0) {
    return res.status(400).json({ error: 'chatId+messageId or keys[] required' });
  }

  const keys = [];
  for (const k of raw) {
    if (!k || !k.chatId || !k.messageId) continue;
    const isGroup = String(k.chatId).endsWith('@g.us');
    const key = { remoteJid: k.chatId, id: k.messageId, fromMe: false };
    if (isGroup && k.senderId) key.participant = k.senderId;
    keys.push(key);
  }
  if (keys.length === 0) {
    return res.status(400).json({ error: 'no valid keys (need chatId+messageId)' });
  }

  try {
    await sock.readMessages(keys);
    res.json({ success: true, marked: keys.length });
  } catch (err) {
    res.status(500).json({ success: false, error: String(err?.message || err) });
  }
});

// ZAELAR-PATCH: put a chat back to UNREAD, as the phone's «Mark as unread» does. WhatsApp marks the CHAT, anchored
// on its last message.
app.post('/mark-unread', async (req, res) => {
  if (!sock || connectionState !== 'connected') {
    return res.status(503).json({ error: 'Not connected' });
  }
  const { chatId, messageId, senderId, ts } = req.body || {};
  if (!chatId || !messageId) return res.status(400).json({ error: 'chatId and messageId are required' });
  const key = { remoteJid: chatId, id: messageId, fromMe: false };
  if (String(chatId).endsWith('@g.us') && senderId) key.participant = senderId;
  try {
    await sock.chatModify({ markRead: false, lastMessages: [{ key, messageTimestamp: Number(ts) || Math.floor(Date.now() / 1000) }] }, chatId);
    rememberChat(chatId, { unread: Math.max(1, chatBook.get(chatId)?.unread || 0) });
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ success: false, error: String(err?.message || err) });
  }
});

// Chat info
app.get('/chat/:id', async (req, res) => {
  const chatId = req.params.id;
  const isGroup = chatId.endsWith('@g.us');

  if (isGroup && sock) {
    try {
      const metadata = await sock.groupMetadata(chatId);
      return res.json({
        name: metadata.subject,
        isGroup: true,
        participants: metadata.participants.map(p => p.id),
      });
    } catch {
      // Fall through to default
    }
  }

  res.json({
    name: chatId.replace(/@.*/, ''),
    isGroup,
    participants: [],
  });
});

// Health check
app.get('/health', (req, res) => {
  res.json({
    status: connectionState,
    queueLength: messageQueue.length,
    uptime: process.uptime(),
    scriptHash: SCRIPT_HASH,
    qr: currentQR,  // ZAELAR-PATCH: data-URI PNG of the pairing QR (null once connected)
  });
});

// Start
if (PAIR_ONLY) {
  // Pair-only mode: just connect, show QR, save creds, exit. No HTTP server.
  console.log('📱 WhatsApp pairing mode');
  console.log(`📁 Session: ${SESSION_DIR}`);
  console.log();
  startSocket();
} else {
  app.listen(PORT, '127.0.0.1', () => {
    console.log(`🌉 WhatsApp bridge listening on port ${PORT} (mode: ${WHATSAPP_MODE})`);
    console.log(`📁 Session stored in: ${SESSION_DIR}`);
    if (ALLOWED_USERS.size > 0) {
      console.log(`🔒 Allowed users: ${Array.from(ALLOWED_USERS).join(', ')}`);
    } else if (WHATSAPP_MODE === 'self-chat') {
      console.log(`🔒 Self-chat mode — only your own messages to yourself are processed.`);
    } else {
      console.log(`🔒 No WHATSAPP_ALLOWED_USERS set — incoming messages are rejected.`);
      console.log(`   Set WHATSAPP_ALLOWED_USERS=<phone> to authorize specific users,`);
      console.log(`   or WHATSAPP_ALLOWED_USERS=* for an explicit open bot.`);
    }
    console.log();
    startSocket();
  });
}
