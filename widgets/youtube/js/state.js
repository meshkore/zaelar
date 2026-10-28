// youtube widget — module-lived state the client parts share (refactor2710-12 T-03). The module loads once, so
// these survive re-renders; ONE exported object because an ES import is a read-only binding.
export const Y = {
  // The playlist plays one after another because the PLAYER tells us the video ENDED (YouTube IFrame API over
  // postMessage, `listening` handshake — same mechanism musica uses). The handler filters by the handshake `id`:
  // both this widget and musica's hidden audio player listen on the same window, and without the filter one
  // player's ending would advance the OTHER's queue.
  ytEnded: null,
  ytError: null,   // V2-401: the player refusing to play (onError) is reported back, never swallowed
  ytQuality: null, // V2-604: the quality levels the video really HAS, reported back once per video
  qSeen: "",       // last videoId whose levels were reported (infoDelivery repeats several times a second)
  // V2-791 — the SOUND the player really has. `muted` in the store is what was ORDERED; whether the browser let a
  // cross-origin player be unmuted without a gesture is only known from the player's own `infoDelivery.muted`.
  ytAudio: null,   // per-render reporter: (playerMuted, videoId) → `player_audio` when it disagrees with the store
  audioSent: "",   // last report sent, so a stream that repeats several times a second reports once
  soundAsked: 0,   // when an unMute was last posted: a player still muted inside this grace is not yet a verdict
  plNow: null,     // the current player element, for the one-shot gesture unlock
  unlockArmed: false,
  // Module-lived screen state (the module loads once, so it survives re-renders — the messaging pattern):
  // null = normal faces · {view:"shelf"} = the video SOURCES. Connecting one is the ⚙ Conectores section's job.
  screen: null,
  // V2-632 — the active TAB. Module-lived like _screen; "" = derive from data at build (video → player,
  // none → inicio). selectTab is the ONLY writer and also clears _screen (the V2-626 rule: choosing a surface
  // is ONE state transition — a connectors screen left open would silently sit on top of the chosen tab).
  tab: "",
  // V2-742 — the last `show_tab` order this card has already obeyed. A SEQUENCE and not a flag:
  // he can ask for the same face twice in a row, and a flag the card consumed cannot fire again.
  gotoSeq: 0,
  syncAsked: 0,         // last time this card asked for a platform re-sync (guards against loops)
  connErr: "", connErrTip: "",          // why a source on the shelf cannot open — never a stale stored one (V2-582)
  // i18n seam (V2-613 / V2-694): `ctx.t`, set by render().
  T: null,
  // Module-lived like _tab: which channel page this page-life has already refreshed («cada vez que entremos …
  // lanzar un pequeño query de actualización»), what is loading right now, and the last sync ask.
  chEntered: "",        // id of the channel page refreshed since he last walked in
  chBusy: "",           // "" | "refresh" | "more" | "tab" — drives the loader lines
  chSyncAsked: 0,
};
