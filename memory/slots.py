"""memory/slots.py — REGISTRO CANÓNICO de slots (auditoría de memoria 2026-07-14, cierre del retest V2-038).

UN solo sitio para el vocabulario de hechos SINGULARES. Antes había TRES listas parciales que divergían — el
prompt del procesador (`nucleo/mem_processor`), los mapas `_PATCH_TO_SLOT`/`_IDENTITY_SLOTS` del agente
(`nucleo/memory_agent`) y el mapa de alias del writer (`memory/writer._SLOT_ALIASES`) — y esa deriva produjo
linajes paralelos del mismo hecho (4 píldoras de ubicación vigentes A LA VEZ en el retest). Este módulo es la
fuente de verdad que consumen los tres:

  - el **writer** normaliza TODO slot entrante con `canonical()` (único punto de paso de las escrituras);
  - el **agente de memoria** deriva de aquí sus mapas slot↔campo-de-state y el conjunto de IDENTIDAD que
    protege el gate anti-garble (V2-033 P0b);
  - el **prompt del procesador LLM** se genera con `prompt_catalog()` — el catálogo que ve el modelo y el que
    valida el host son EL MISMO por construcción (no pueden divergir).

Los slots con NAMESPACE de otras piezas (`cluster:<cluster>:<peer>`, `navegador.session.<sitio>`,
`<widget>:<clave>` de los widgets en background) NO se registran aquí: pasan por `canonical()` solo con
lowercase/trim (convención global desde V2-038) y conservan su semántica de supersede por clave exacta.

Stdlib puro, sin dependencias del resto del paquete (importable desde cualquier capa sin ciclos).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SlotSpec:
    key: str                          # clave canónica ("operator.location")
    desc: str                         # qué guarda (para el prompt del procesador)
    state_field: str | None = None    # campo de `state` que refleja este hecho (None = sin reflejo en el ESTADO)
    identity: bool = False            # hecho SINGULAR de identidad → protegido por el gate anti-garble (P0b)
    garble_guard: bool = True         # False = PREFERENCIA que evoluciona reformulándose (trato…): el gate P0b no
    #                                   la cuarentena (auditoría 2026-07-19: operator.treatment acabó 4 filas /
    #                                   0 vigentes — cada reformulación legítima "contradecía" a la anterior)
    aliases: tuple = field(default_factory=tuple)   # variantes que emiten los modelos → colapsan al canónico


# El vocabulario CERRADO de hechos singulares del operador. Añadir un slot = añadir UNA entrada aquí
# (el writer, el agente y el prompt del procesador lo recogen solos).
SLOTS: dict[str, SlotSpec] = {s.key: s for s in (
    SlotSpec("operator.name", "nombre del operador", state_field="operator_name", identity=True,
             aliases=("name", "nombre", "operator_name", "operator.nombre")),
    SlotSpec("operator.location", "dónde vive", state_field="location", identity=True,
             aliases=("location", "ubicacion", "ubicación", "city", "ciudad", "operator_location")),
    SlotSpec("operator.treatment", "trato preferido", state_field="treatment", identity=True, garble_guard=False,
             aliases=("treatment", "trato")),
    # hardware/coche/trabajo: hechos de VIDA que cambian re-declarándose con naturalidad ("mi coche es un Skoda"
    # tras tener otro) — batería v1 2026-07-20: el gate P0b los cuarentenaba como garble y el dato VIEJO sobrevivía
    # en state. garble_guard=False → supersede normal (identity=True se mantiene: los workers siguen vetados).
    SlotSpec("operator.hardware", "su equipo/hardware principal", state_field="hardware", identity=True,
             garble_guard=False, aliases=("hardware", "equipo")),
    SlotSpec("operator.car", "su coche", state_field="car", identity=True,
             garble_guard=False, aliases=("car", "coche")),
    SlotSpec("operator.job", "su trabajo/empresa", state_field="job", identity=True,
             garble_guard=False, aliases=("job", "trabajo", "empleo", "empresa")),
    SlotSpec("operator.birthday", "su fecha de nacimiento", identity=True,
             aliases=("birthday", "cumpleanos", "cumpleaños", "nacimiento")),
    SlotSpec("operator.phone", "su teléfono", identity=True,
             aliases=("phone", "telefono", "teléfono")),
    SlotSpec("operator.email", "su correo electrónico", identity=True,
             aliases=("email", "correo", "e-mail", "mail", "correo electronico", "correo electrónico")),
    SlotSpec("operator.address", "su dirección postal", identity=True,
             aliases=("address", "direccion", "dirección", "domicilio")),
    SlotSpec("operator.diet", "el patrón dietético ELEGIDO (vegetariano/vegano/keto…), NUNCA alergias",
             identity=True, aliases=("diet", "dieta")),
    SlotSpec("goal.current", "el objetivo VITAL/profesional actual del operador", state_field="objetivo",
             # V2-050: el CORAZÓN LLM namespacea por analogía con operator.name → 'operator.goal'/'operator.objetivo'
             # se escapaban del registro (canon passthrough → state_field None → objetivo vacío + LINAJES PARALELOS,
             # bot v2 #25/#26). Se colapsan al canónico.
             identity=True, aliases=("goal", "objetivo", "goal_current", "operator.goal", "operator.objetivo",
                                     "meta", "operator.meta")),
    SlotSpec("project.current", "su proyecto de trabajo actual", state_field="proyecto", identity=True,
             aliases=("project", "proyecto", "project_current", "operator.project", "operator.proyecto")),
    # 2026-08-17 (auditoría en vivo): "hijos", "pareja", "padres" no tenían slot — solo píldoras `long/fact`
    # sueltas (slot=None), alcanzables NADA MÁS que por recall semántico probabilístico. Norma del operador: los
    # familiares cercanos son un hecho ACTIVO/imperturbable, mismo trato que operator.car/hardware/job — un
    # resumen en TEXTO que se restablece por reformulación (garble_guard=False), no una lista estructurada nueva.
    SlotSpec("operator.family", "sus familiares cercanos (hijos, pareja, padres…) — nombre y/o relación",
             state_field="familia", identity=True, garble_guard=False,
             aliases=("family", "familia", "hijos", "hijo", "hija", "pareja")),
)}

_ALIASES: dict[str, str] = {a: s.key for s in SLOTS.values() for a in s.aliases}
_IDENTITY: frozenset = frozenset(k for k, s in SLOTS.items() if s.identity)
_STATE_FIELD: dict[str, str] = {k: s.state_field for k, s in SLOTS.items() if s.state_field}
_FIELD_TO_SLOT: dict[str, str] = {v: k for k, v in _STATE_FIELD.items()}


def canonical(slot: str | None) -> str | None:
    """Slot canónico: lowercase + trim + alias→canónico. ÚNICA normalización del sistema (la aplica el writer
    a toda escritura). Un slot desconocido/namespaced pasa lowercased/stripped tal cual.

    V2-050: el CORAZÓN LLM DOBLE-namespacea por analogía con `operator.name` → emite `operator.goal.current`,
    `operator.objetivo`, etc., que se escapaban del registro (canon passthrough → sin state_field → objetivo vacío
    + linaje paralelo, bot v1 #20/#28). Fallback DETERMINISTA: si el slot no se reconoce pero empieza por
    `operator.`, se prueba el resto; si ESE resuelve a un slot CONOCIDO, se usa (nunca inventa un slot nuevo)."""
    s = (slot or "").strip().lower()
    if not s:
        return None
    if s in _ALIASES:
        return _ALIASES[s]
    if s in SLOTS:
        return s
    if s.startswith("operator."):
        rest = s[len("operator."):]
        if rest in _ALIASES:
            return _ALIASES[rest]
        if rest in SLOTS:
            return rest
    return s


def equivalent_keys(slot: str | None) -> list[str]:
    """TODAS las variantes literales (canónica + sus alias) que designan el MISMO hecho singular. El writer expande
    con esto el SELECT del supersede → colapsa por SLOT aunque en la BD haya una clave LEGACY/alias sin normalizar
    (p. ej. una píldora vieja `location` conviviendo con `operator.location`), sin esperar al sueño del consolidador
    (auditoría de memoria 2026-07-14 · residuo del retest V2-038). Un slot desconocido/namespaced → solo él mismo."""
    c = canonical(slot)
    if not c:
        return []
    spec = SLOTS.get(c)
    return [c, *spec.aliases] if spec else [c]


def identity_slots() -> frozenset:
    """Slots de IDENTIDAD singular — los que protege el gate anti-garble (V2-033 P0b)."""
    return _IDENTITY


def state_field(slot: str | None) -> str | None:
    """Campo de `state` que refleja este slot (None si el slot no se proyecta al ESTADO)."""
    return _STATE_FIELD.get(canonical(slot) or "")


def slot_for_state_field(fld: str) -> str | None:
    """Inverso: slot canónico de un campo de `state` (para la heurística de perfil del agente)."""
    return _FIELD_TO_SLOT.get((fld or "").strip())


def garble_guard_slots() -> frozenset:
    """Slots que SÍ protege el gate anti-garble P0b (identidad singular garble-able). Las preferencias que
    evolucionan reformulándose (garble_guard=False) supersedan con normalidad."""
    return frozenset(k for k, sp in SLOTS.items() if sp.identity and sp.garble_guard)


def patch_to_slot() -> dict[str, str]:
    """Mapa campo-de-state → slot canónico (lo consume `memory_agent`)."""
    return dict(_FIELD_TO_SLOT)


def prompt_catalog() -> str:
    """Catálogo para el prompt del procesador LLM: la lista de claves canónicas con su significado, generada
    del registro (el modelo y el host no pueden divergir)."""
    return ", ".join(f'"{k}" ({s.desc})' for k, s in SLOTS.items())
