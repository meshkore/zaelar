"""Documentation translated to English."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SlotSpec:
    key: str                          # translated implementation note
    desc: str                         # translated implementation note
    state_field: str | None = None    # translated implementation note
    identity: bool = False            # translated implementation note
    garble_guard: bool = True         # translated implementation note
    # translated implementation note
    # translated implementation note
    aliases: tuple = field(default_factory=tuple)   # translated implementation note


# translated implementation note
# translated implementation note
SLOTS: dict[str, SlotSpec] = {s.key: s for s in (
    SlotSpec("operator.name", "nombre del operador", state_field="operator_name", identity=True,
             aliases=("name", "nombre", "operator_name", "operator.nombre")),
    SlotSpec("operator.location", "dónde vive", state_field="location", identity=True,
             aliases=("location", "ubicacion", "ubicación", "city", "ciudad", "operator_location")),
    SlotSpec("operator.treatment", "trato preferido", state_field="treatment", identity=True, garble_guard=False,
             aliases=("treatment", "trato")),
    # translated implementation note
    # translated implementation note
    # translated implementation note
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
             # translated implementation note
             # translated implementation note
             # translated implementation note
             identity=True, aliases=("goal", "objetivo", "goal_current", "operator.goal", "operator.objetivo",
                                     "meta", "operator.meta")),
    SlotSpec("project.current", "su proyecto de trabajo actual", state_field="proyecto", identity=True,
             aliases=("project", "proyecto", "project_current", "operator.project", "operator.proyecto")),
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    SlotSpec("operator.family", "sus familiares cercanos (hijos, pareja, padres…) — nombre y/o relación",
             state_field="familia", identity=True, garble_guard=False,
             aliases=("family", "familia", "hijos", "hijo", "hija", "pareja")),
)}

_ALIASES: dict[str, str] = {a: s.key for s in SLOTS.values() for a in s.aliases}
_IDENTITY: frozenset = frozenset(k for k, s in SLOTS.items() if s.identity)
_STATE_FIELD: dict[str, str] = {k: s.state_field for k, s in SLOTS.items() if s.state_field}
_FIELD_TO_SLOT: dict[str, str] = {v: k for k, v in _STATE_FIELD.items()}


def canonical(slot: str | None) -> str | None:
    """Documentation translated to English."""
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
    """Documentation translated to English."""
    c = canonical(slot)
    if not c:
        return []
    spec = SLOTS.get(c)
    return [c, *spec.aliases] if spec else [c]


def identity_slots() -> frozenset:
    """Documentation translated to English."""
    return _IDENTITY


def state_field(slot: str | None) -> str | None:
    """Documentation translated to English."""
    return _STATE_FIELD.get(canonical(slot) or "")


def slot_for_state_field(fld: str) -> str | None:
    """Documentation translated to English."""
    return _FIELD_TO_SLOT.get((fld or "").strip())


def garble_guard_slots() -> frozenset:
    """Documentation translated to English."""
    return frozenset(k for k, sp in SLOTS.items() if sp.identity and sp.garble_guard)


def patch_to_slot() -> dict[str, str]:
    """Documentation translated to English."""
    return dict(_FIELD_TO_SLOT)


def prompt_catalog() -> str:
    """Documentation translated to English."""
    return ", ".join(f'"{k}" ({s.desc})' for k, s in SLOTS.items())
