# concepts.py — central-memory CONCEPT VOCABULARY (V2-013 T126). Shared substrate:
#   • the WRITER (nucleo/memory_agent._derive_concepts) uses it as deterministic backstop for LLM labeling,
#   • the VIEWER (memory/api.map) uses it to derive the SHORT-TERM CONCEPT MAP on the fly (short-term has no
#     persisted concept edges — those are ephemeral pills; long-term does have them in `edges`).
# One place for the taxonomy -> zero divergence between how organization is WRITTEN and DRAWN.
import re

# (concept, keyword regex) — stable order (defines priority when trimming to 3).
CONCEPT_MAP: list[tuple[str, str]] = [
    ("trabajo", r"trabaj|curro|jef[ae]|oficina|empresa|ascend|becari|compañer|n[oó]mina|despid|contrat|reuni[oó]n|colega|carrera profesional|proyecto empresarial|negocio|emprend|startup|cliente"),
    ("salud", r"salud|m[eé]dic|enferm|al[eé]rg|operaci[oó]n|\boperad[oa]\b|\boperaron\b|cirug[íi]a|quir[úu]rg|dolor|tensi[oó]n|hospital|anal[ií]tica|dentista|pastilla|lesi[oó]n|coraz[oó]n|s[ií]ntoma|receta m[eé]dica|fisio|rehabilit|espalda|vacuna|cita m[eé]dica|h[aá]bito saludable|descanso|dormir"),
    ("finanzas", r"dinero|euro|banco|hipoteca|ahorr|invers|fondo|factura|deuda|impuesto|sueldo|renta|pagar|préstamo|prestamo|nómina|cripto|bitcoin"),
    ("familia", r"familia|madre|padre|mam[aá]|pap[aá]|herman[oa]|sobrin|prim[oa]|t[íi][oa]|abuel|hij[oa]|pareja|mujer|marido|novi[oa]|boda|cuñad"),
    ("deporte", r"deporte|p[aá]del|f[uú]tbol|gimnasio|correr|tenis|baloncesto|entrena|partido|marat[oó]n|nadar|bici|yoga|buceo|escalada|surf"),
    ("vivienda", r"\bcasa\b|piso|mudan|mudad|direcci[oó]n|\bcalle\b|barrio|reforma|mueble|alquiler|casero|vecin"),
    ("viajes", r"viaj|vuelo|hotel|maleta|turism|vacacion|escapada|excursi[oó]n|refugio|destino"),
    ("estudios", r"estudi|examen|universidad|\bcurso\b|m[aá]ster|máster|aprend|idioma|jap[oó]n[eé]s|ingl[eé]s|derecho|formaci[oó]n|certificad"),
    ("ocio", r"pel[ií]cula|serie|concierto|m[uú]sica|\blibro\b|leer|vinilo|hobby|afici|jazz|techno|guitarra|videojueg|ocio"),
    ("comida", r"restaurante|\bcena\b|\bcenar\b|cocina|vegetarian|vegano|dieta|receta|desayun|t[aá]per|"
               r"comida familiar|cel[íi]ac|gluten|intoleran|lactosa|alimentari|\bcomer\b|alcohol|\bbeb[eo]"),
    ("tecnología", r"python|c[oó]digo|programa|ordenador|m[oó]vil|\bapp\b|software|widget|script|servidor|ia\b|modelo"),
    ("mascotas", r"perro|gato|mascota"),
    ("objetivos", r"objetivo|\bmeta\b|sue[ñn]o de|prop[oó]sito|aspiraci[oó]n|quiero lograr|me gustar[íi]a llegar|a[ñn]o que viene|a futuro|ilusi[oó]n"),
    ("mensajes", r"whatsapp|telegram|mensaje|chat|escrib[ií]|me ha dicho|contact[oó]"),
    ("agenda", r"agenda|cita|reuni[oó]n|recu[eé]rda|recordatorio|calendario|ma[ñn]ana a las|cron|programad"),
]
CONCEPT_RES = [(c, re.compile(p, re.I)) for c, p in CONCEPT_MAP]


def derive_concepts(text: str, cap: int = 3) -> list[str]:
    """Derive 1..cap concepts from text by keywords (deterministic, cheap). Backstop for LLM labeling on WRITE and
    engine for the SHORT-term concept map in the VIEWER."""
    t = text or ""
    out = [c for c, rx in CONCEPT_RES if rx.search(t)]
    return out[:cap]
