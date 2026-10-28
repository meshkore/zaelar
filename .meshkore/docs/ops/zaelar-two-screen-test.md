---
title: The two-screen test — every widget, with the agent open on a computer and a phone at once
category: ops
updated: 2026-10-25
status: current
---
# The two-screen test

One agent, one conversation, two screens: the operator's computer and phone are open on the same agent at the same
time (V2-792). Every widget declares how it lives across them, in its manifest:

| `"screens"` | What it is | What must happen |
|---|---|---|
| `shared` | a reflection of data — a calendar, contacts, a list, a map, results | open on any number of screens; it opens on the screen that asked and the others get an «open here» chip; every copy shows the same data live |
| `single` | it takes the device's sound or picture — a video, music, a recording | it lives on ONE screen; asking for it from another screen MOVES it (the old screen stops and closes it); pause/volume reach it wherever it plays |

`runtime.output` ⇒ `single` (the validator refuses the contradiction). Policy: `widgets/screen_policy.py`.

**A widget is not finished until it passes this test** — a new native widget, a user's own, or a change to either.

## 1 · Automatic: two browsers on one engine

```sh
./.venv/bin/python -m tests.widget_harness                          # contract, golden, render AND screens (declared, consistent)
./.venv/bin/python -m tests.widget_harness --two-screens <id>       # a desktop and a phone browser, the widget's policy checked
./.venv/bin/python -m tests.widget_harness --two-screens <id> --headed   # …with both windows on screen, to watch it
```

The two-screen pass (`tests/browser/e2e/mobile/two_screens.py`) opens a 1280-wide desktop page and a 390-wide phone
page, each with its own storage and event stream, against a preview of the engine's own routers. It pushes what a
real turn pushes through the real stream, asks for the widget from the computer and then from the phone, and reads
what each screen did. Node **4.270** runs it over the WHOLE catalogue (a widget added tomorrow is covered the moment
it exists); node **4.269** fails a built-in widget with no declaration; node **4.267** is the scenario test (typed chat
from the screen without the voice, the chips, a video moving to the phone).

What it cannot measure: a real phone, a real microphone, the sound, the widget's own painting. That is §2.

## 2 · Manual: the operator, with a real computer and a real phone

Print the steps for one widget (or all of them):

```sh
./.venv/bin/python -m tests.widget_harness --manual <id>
```

Before you start: the agent ON, the computer open at the desk, the phone open at `/m` (on a hosted
deployment, its own `/m`). Opening the phone takes the voice; the computer's orb turns to «voice elsewhere».

**A `shared` widget**
1. On the COMPUTER, ask for it. It opens on the computer; the phone shows «… · open on the computer — Open here» and
   does not open it.
2. On the PHONE, ask for it too. It opens on the phone and STAYS open on the computer.
3. Change something in it from one screen. The other one shows the change without a reload.
4. Type an order on the screen that does NOT hold the voice. It is answered, and the line shows on both chats.

**A `single` widget**
1. On the COMPUTER, ask for it and let it play. The phone shows «… · playing on the computer — Bring here» and plays
   nothing.
2. Open the phone app (or reload it). It does NOT start the widget again; the chip is there.
3. On the PHONE, ask for it with something new. The computer STOPS and closes it at once; the phone opens and plays
   it. Never both sounding.
4. From the phone, «pause» / «volume down». It obeys wherever it plays.
5. «Put it on the computer» (or tap «Bring here» on the computer). It moves back; the phone keeps the chip.
6. Tap the mic on the computer. The phone gives up the voice at once (mic and speaker off).

Write the result in the widget's `notes.md` (date, screens, pass/fail and what failed). A failure is a bug in the
widget's declaration or in the host, never something to explain to the operator.

**The agent's state on each screen** (every pass, whatever the widget — node 4.147 renders it)
1. Agent stopped: the grey ⏻ on both screens.
2. The phone holds the voice: the phone shows the grey orb (orange only while the agent talks); the computer shows
   the grey orb with the slashed mic — never the ⏻, never orange.
3. Tap the computer's orb: the voice comes to the computer (the phone turns to the slashed mic). The agent keeps
   running — a tap on «voice elsewhere» never stops anything.
4. Icons: lilac when on or open, grey when off or closed, on the computer (eye and bar) and on the phone.

## 3 · When an agent runs the live pass on the operator's engine

Only with the operator's go-ahead, because it turns his ⏻ on: microphone muted (`POST /api/mic {"muted":true}` and
in each page), two Chromium contexts with a fake microphone (`--use-fake-ui-for-media-stream
--use-fake-device-for-media-stream`; the app's built-in browser pane denies the microphone, so it cannot hold a voice
session), and the ⏻ put back as it was at the end. Measured this way on 2026-10-25: V2-792 §7.
