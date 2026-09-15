---
title: The widget header standard — two bars, and the door to the connectors
category: conventions
updated: 2026-09-15
owner: ricart
status: current
---

# Two bars, and the door to the connectors

**This is a house rule, not a suggestion.** Every widget that has a connector behind it wears the same two
bars, in the same order, with the same class shapes and the same behaviour. The operator's framing, which
is also the reason:

> «El widget de contactos tiene que ser como los demás widgets: mensajería, agenda, etc. […] Hay que
> estandarizar el formato del header y el subheader conforme a los otros. **Esto es un sistema operativo,
> con lo cual esas barras ya tienen un formato estándar y nos llevan al sistema de conectores.**»

A desktop where every window invents its own chrome is a pile of demos. The bars are how the product says
«this is one system», and the plug button is how a user learns, once, where every integration lives.

**Reference implementations:** `widgets/agenda/widget.js` (V2-679) and `widgets/contactos/widget.js`
(V2-699). Copy from those two; they are one-for-one on purpose.

---

## Bar 1 — the header

```
[◧]  Content title                         … widget-specific right slot …
```

| Part | Class | Rule |
|---|---|---|
| Brand disc | `.<pfx>brand` | 26 px, `--hb-r-s` radius, `--hb-accent` ground, the widget's own 15 px stroke icon inside. |
| Content title | `.<pfx>title` / `.<pfx>range` | **14 px / 600.** It is the CONTENT's title — the date range, the folder, the word «Contactos» — not the window's name. |
| Right slot | — | Whatever this widget's header needs: the agenda's ‹ Hoy ›, the search box, a count. |

⚠️ **The content title sits one step UNDER the window title, never over it.** A 15/700 range beside a
14/600 window name inverts the hierarchy it is supposed to express (measured, V2-691).

## Bar 2 — the subheader band

```
( Tab ) ( Tab ) ( Tab )              [icon][icon][icon]  [ ⚡ Conectores ]
────────────────────────────────────────────────────────────────────────  ← one hairline
```

| Part | Class | Rule |
|---|---|---|
| The band | `.<pfx>views` | One hairline `border-bottom` in `--hb-line-subtle`. Horizontal scroll, scrollbar hidden. |
| View tabs | `.<pfx>tab`, `.on` | Pill. Selected = accent-tinted chip **with an accent ring** (`color-mix` 18 % + inset ring 55 %). Never a filled near-white pill — that is a second filled language on the screen (V2-690). |
| Right cluster | `.<pfx>viewsright` | `margin-left:auto`. Provider icons first, then the Conectores button. |
| Provider icons | `.<pfx>connicon`, `.on`, `.off` | 28 px targets, a tooltip each, the provider's own brand colour. |
| Connectors button | `.<pfx>connbtn` | Plug icon + the word «Conectores». Toggles the connectors screen. |

**Disabled tabs stay at `opacity:.75`, not `.6`.** At .6 the effective ink measured 4.25:1, under the
floor; the tabs are still the map of where you are, so «unavailable» must not read as «absent» (V2-691).

### The tabs go quiet while the connectors screen is open

No view is the one on screen, so none is lit and none is clickable (`disabled`). The chosen view survives
underneath and comes back when the screen closes. His words: «se desactiva el foco o el botón activo».

## The provider icons — three states, and they are different sentences

| State | Looks like | Clicks |
|---|---|---|
| `connected` | full colour, `.on`, opacity 1 | → the connectors screen |
| `off` (built, not linked) | brand colour, dimmed to .72 | → the connectors screen (its Connect button) |
| `unavailable` (**no connector exists**) | `.off`, opacity .4, `disabled` | nothing |

⚠️ **«You have not linked it» and «we have not built it» are different sentences, and showing the first
when the second is true is the same class of lie as promising a view** (V2-540). A source with no
connector is VISIBLE and INERT — no button, no handler. Per INI-027, showing what we do not have yet is
the point rather than an embarrassment.

⚠️ **The list is a READ of the real inventory, never a hardcoded «off».** Each widget derives it from
`connectors/registry.py::descriptors()` filtered by its family, so the day a second provider is registered
it lights up with nothing else to change. See `widgets/agenda/gcal.py::calendars()` and
`widgets/contactos/gcontacts.py::providers()` — identical functions, deliberately.

## The connectors screen

**It replaces the content area. It is never a floating overlay.**

```
Conectores                                              ‹ Contactos
┌────────────────────────────────────────────────────────────────┐
│ [G]  Google Contacts        ● conectado      [ Desconectar ]   │
├────────────────────────────────────────────────────────────────┤
│  ⟳  Sincronización                                             │
│     ⇄  Google y zaelar se mantienen iguales.                   │
│     [ Sincronizar contactos ]        Última vez: … · 12 nuevos │
└────────────────────────────────────────────────────────────────┘
│ []  iCloud (Apple)          ○ aún no disponible                │   ← dimmed, no button
```

- a back crumb that always says where «back» goes — to the widget, never out of it;
- one row per source: mark, label, a status dot, and **at most one button**;
- the connected source's own panel (sync box, default calendar, whatever it owns) directly under its row.

## Connecting: `ctx.connect(...)`, never a window of your own (V2-700)

```js
const r = await ctx.connect("connect", {origin: location.origin},
                            {family: "contactos", onDone: () => { busy = false; }});
if (!(r && r.ok)) showError(r && r.error);
```

That is the whole of it. The canvas opens the window **inside the click** (a `window.open()` after an
`await` is outside the user gesture and every mainstream browser blocks it in SILENCE — V2-603 paid for
this), with a features string so it is a **popup on the desktop** and a **tab on a narrow screen**, and
then it watches for the connection landing.

⚠️ **Do NOT hand-roll this.** Five widgets did, and by 2026-09-15 they had drifted into two different
behaviours for one idea — a popup in the agenda, a whole tab in contacts — which is exactly what the
operator reported. `test_no_widget_hand_rolls_its_own_consent_window` is the ratchet: a `window.open("")`
inside a `widget.js` fails the suite.

### How the card NOTICES — three signals, and none of them is believed

His report: *«cuando volvemos a la pantalla […] ya automáticamente desaparece la opción de conectar y se
marca como conectado. Eso sigue sin suceder y se tiene que estar detectando en tiempo real. Si no, el
usuario está confundido y podría volver a iniciar indefinidamente la conexión.»*

1. **The callback page posts to its opener** (`connectors/oauth_callback.py`) — instant, and the only one
   that fires while he is still looking at the window.
2. **The server emits `widget/data`** for the family's widget (`oauth_callback.announce`) — this is the
   path that already worked for everything else and that OAuth was missing. A widget's own store goes
   through `widgets/store.py::save`, which emits it and makes the open card re-fetch itself; that is why
   the messaging card notices a Telegram QR being scanned **with no polling at all**. OAuth tokens live in
   a `SecureJsonStore`, which emits nothing.
3. **A bounded poll** in `_watchConnect` — covers a window that was never ours to watch (a mobile tab with
   no opener) and a message a reused window ate.

⚠️ **Every one of them ends in `refreshData`, which re-reads state from the ENGINE.** The postMessage is a
HINT to go and look, never the answer — which is what makes it safe to accept it loosely, and why a forged
message buys a refresh and nothing more. A surface that believed the flag would paint «conectado» over an
account that is not.

**A new connector gets all of this for free** by returning `oauth_callback.page(..., family=...)` from its
callback route and calling `oauth_callback.announce(family)` on success AND on disconnect — unlinking is a
state change too, and a card that goes on saying «conectado» is the same lie in reverse.

**By voice this cannot be completed**: the consent is a click. The action leaves the card ON the connectors
screen and the manifest tells the model to say «pulsa Conectar» (V2-686).

## The checklist for the next widget

1. `.<pfx>bar` with the brand disc and a 14/600 content title.
2. `.<pfx>views` band, one hairline, tabs as accent-tinted chips, `disabled` while a screen is open.
3. `.<pfx>viewsright` with the provider icons and the Conectores button.
4. A `providers()` reading `registry.descriptors()` by family — never a hardcoded list of states.
5. A connectors SCREEN, not an overlay, with a back crumb.
6. Connect opens the window synchronously.
7. **No second door to the same thing.** An «Import from X» button somewhere else in the widget is a
   second place to keep in sync and a second vocabulary for one idea — exactly what was removed from the
   contacts sidebar the day this standard was written.
8. Rendered tests for all of it: see
   `tests/browser/unit/contactos/test_a_contact_card_looks_like_a_contact_card.py` (testmap **4.176**).
