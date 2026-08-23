"""The deterministic vault/secrets pre-flight, decided ONCE for both channels (V2-060 · F1 step 1, 2026-08-23).

Two intercepts that must run before the model sees the text, and for OPPOSITE reasons: a security-config command
(«no me digas los secretos por voz») because a non-reasoning model would rephrase or refuse it, and a spoken
secret because the value must never reach an LLM at all. Both were implemented twice — the voice side extracted
to `providers/vault_intercept.py` in V2-112, the probe side still carrying its own copy under three mirror markers.

They had ALREADY drifted, which is the whole argument: the probe's copy returned the parenthetical «(secreto
cifrado)» where voice said a real localized sentence, and V2-141 had to be fixed in both places separately —
its comment in `probe.py` said so out loud («este es el canal por el que corren los casos de uso, así que las
dos eran invisibles desde la voz»).

WHAT IS SHARED is the decision and the one side effect both channels need (encrypting the secret). WHAT IS NOT
is delivery: voice speaks the line through its turn closure and emits observability; probe puts it in its
response dict. `inspect()` returns a verdict and touches neither.

Two knobs instead of a channel flag, so the caller states its own truth rather than naming itself:
  · `enabled` — voice passes `not first_turn` (the kickoff greeting is not the operator talking); probe passes
    True. A channel-name parameter would have hidden that this is a rule about the TURN, not about the mouth.
  · `store`  — voice always persists; probe only when `ingest` is on, because a dry run must not write the
    operator's real secrets into the real vault.

The langs lookup is lazy and fail-soft, inherited from the probe's copy (the stricter of the two): a missing
locale must not turn «your secret is saved» into an exception on the path that just handled a password.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

_LOG = __import__("logging").getLogger("zaelar.turn.vault")


@dataclass
class VaultVerdict:
    """What the gate decided. `consumed` means the turn is OVER — the caller must deliver `line` and stop."""

    kind: str = ""                 # "" | "config" | "saved" | "need_vault" | "carried"
    consumed: bool = False
    text: str = ""                 # original when nothing applied, REDACTED once a secret was seen
    line: str = ""                 # the sentence to deliver ("" when there is nothing to say)
    config: tuple | None = None    # (key, value) of the security rule, for the caller's observability
    labels: list[str] = field(default_factory=list)
    has_vault: bool = False


def _secret_line(has_vault: bool) -> str:
    try:
        from voice.engine.core import langs
        lang = langs.current_language()
        return lang.secret_saved if has_vault else lang.secret_need_vault
    except Exception:
        return "Guardado." if has_vault else "Necesito que crees la bóveda primero."


async def inspect(text: str, *, enabled: bool = True, store: bool = True) -> VaultVerdict:
    """Run both intercepts over `text`. Never raises: every branch degrades to «nothing applied»."""
    if not enabled or not (text or "").strip():
        return VaultVerdict(text=text)

    # 1) SECURITY-CONFIG COMMAND — a hard user rule, applied deterministically and short-circuiting the turn.
    try:
        from nucleo.flash import vault_rules
        cfg = vault_rules.detect(text)
    except Exception:
        cfg = None
    if cfg is not None:
        line = ""
        try:
            line = vault_rules.apply(cfg) if store else "(config no aplicada: ingest=false)"
        except Exception as e:  # noqa: BLE001
            _LOG.warning(f"aplicar regla de seguridad falló: {e}")
        return VaultVerdict(kind="config", consumed=True, text="", line=line, config=cfg)

    # 2) A SPOKEN SECRET — encrypt it here; the value never travels on to the model.
    try:
        from memory import secrets as msecrets
        found = msecrets.detect(text)
    except Exception:
        return VaultVerdict(text=text)
    if not found:
        return VaultVerdict(text=text)

    has_vault = False
    try:
        from memory import vault
        has_vault = vault.exists()
    except Exception:
        vault = None                                     # type: ignore[assignment]
    if has_vault and store:
        for d in found:
            try:
                await asyncio.to_thread(vault.store_secret, d.label, d.value,
                                        slot=d.slot, sensitivity=d.sensitivity)
            except Exception as e:  # noqa: BLE001
                _LOG.warning(f"guardar secreto {d.label!r} falló: {e}")

    labels = [d.label for d in found]
    # V2-141 — the turn is only CONSUMED when the secret IS the turn. Nobody recites an IBAN for fun: they
    # recite it to pay something, and swallowing the turn loses the half that matters (and never reaches the
    # confirm-gate that lives further down, which is the one that would have stopped the payment).
    try:
        from nucleo.flash import vault_carrier
        whole = vault_carrier.secret_is_the_whole_turn(text, found)
    except Exception:
        whole = True                                     # fail CLOSED: never let a value continue by accident
    redacted, _ = msecrets.redact(text)
    if whole:
        return VaultVerdict(kind="saved" if has_vault else "need_vault", consumed=True,
                            text=redacted, line=_secret_line(has_vault),
                            labels=labels, has_vault=has_vault)
    return VaultVerdict(kind="carried", consumed=False, text=redacted, labels=labels, has_vault=has_vault)


# ── REVELAR un secreto guardado (V2-060 F1b) ─────────────────────────────────────────────────────────────────
# El tercero de la terna, y el que más cuidado pide: aquí SÍ existe un valor descifrado, y la frontera entre los
# dos canales no es de estilo sino de INVARIANTE. La voz puede decirlo (modo cómodo, decisión del operador, con
# la regla dura `secrets_voice` para apagarlo); el probe NO PUEDE NI VERLO — su respuesta viaja al arnés y a los
# logs de casos de uso, así que el valor lo sirve `/api/vault/reveal` al frontend y nunca esta ruta.
#
# Por eso lo compartido llega hasta el DESENLACE y sus filas de observabilidad, y la frase se queda en la voz:
# devolver una línea ya compuesta obligaría al probe a recibir el valor dentro para tirarlo después, que es
# justo la forma en que un invariante se convierte en una convención.


@dataclass
class RevealOutcome:
    """El desenlace de un `reveal_secret`. `events` son las filas que el llamante emite en su propio canal."""

    status: str = "error"          # ok | locked | no_vault | not_found | empty | error
    label: str = ""
    memory_id: object = None
    candidates: list = field(default_factory=list)
    value: str = ""                # SOLO para la voz. El probe nunca lo lee (hay un guarda que lo exige).
    events: list = field(default_factory=list)   # [(kind, label, extra_dict)]

    def as_probe_payload(self) -> dict:
        """Lo que el canal de texto puede devolver, por construcción sin el valor."""
        return {"status": self.status, "label": self.label,
                "memory_id": self.memory_id, "candidates": self.candidates}


async def reveal(label: str) -> RevealOutcome:
    """Resuelve la petición de un secreto guardado. Nunca lanza: cualquier fallo sale como `status="error"`,
    que los dos canales ya tratan como «no lo encuentro» — un reveal roto no puede tumbar el turno."""
    try:
        from nucleo.flash import vault_flow
        rv = await asyncio.to_thread(vault_flow.reveal, str(label or ""))
    except Exception as e:  # noqa: BLE001
        _LOG.warning(f"reveal_secret falló (el turno sigue): {e}")
        rv = {"status": "error"}

    st = rv.get("status") or "error"
    out = RevealOutcome(status=st, label=rv.get("label") or "", memory_id=rv.get("memory_id"),
                        candidates=list(rv.get("candidates") or []), value=rv.get("value") or "")
    # Las claves son `slabel`/`mid` y NO `label`/`id` a propósito: `label` pisaría el label del propio evento en
    # `observer.emit`. Es un detalle que ya costó una fila ilegible una vez.
    if st == "ok":
        out.events.append(("secret", "reveal", {"slabel": out.label, "mid": out.memory_id}))
    elif st == "locked":
        out.events.append(("secret", "locked", {"slabel": out.label, "mid": out.memory_id}))
    elif st == "no_vault":
        out.events.append(("secret", "no_vault", {}))
    return out


def voice_line(out: RevealOutcome) -> str:
    """La frase HABLADA. Vive aquí y no en el provider porque la decide el mismo desenlace, pero solo la llama
    quien tiene boca: es la única función de este módulo que puede devolver un valor descifrado, y lo hace solo
    cuando la regla dura del operador (`secrets_voice`, V2-060 F2) lo permite. Con ella apagada se nombra el
    secreto y se enseña en pantalla, nunca se dice."""
    try:
        from voice.engine.core import langs
        L = langs.current_language()
    except Exception:
        return "No he podido recuperarlo."
    if out.status == "ok":
        try:
            from memory import state as mstate
            speak_it = bool(mstate.security_flag("secrets_voice", True))
        except Exception:
            speak_it = True
        return (L.secret_reveal.format(label=out.label, value=out.value) if speak_it
                else L.secret_shown.format(label=out.label))
    if out.status == "locked":
        return L.secret_locked
    if out.status == "no_vault":
        return L.secret_no_vault
    if out.status == "not_found" and out.candidates:
        return L.secret_not_found + f" Tengo: {', '.join(out.candidates)}."
    return L.secret_not_found          # not_found sin candidatos, empty, error
