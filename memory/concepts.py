# concepts.py — VOCABULARIO DE CONCEPTOS de la memoria central (V2-013 T126). Substrato compartido:
#   • el ESCRITOR (nucleo/memory_agent._derive_concepts) lo usa como backstop determinista del etiquetado del LLM,
#   • el VISOR (memory/api.map) lo usa para derivar el MAPA CONCEPTUAL de CORTO PLAZO al vuelo (el corto no tiene
#     aristas de concepto persistidas — son píldoras efímeras; el largo sí las tiene en `edges`).
# Un solo sitio para la taxonomía → cero divergencia entre cómo se ESCRIBE y cómo se DIBUJA la organización.
import re

# (concepto, regex de keywords) — orden estable (define prioridad al recortar a 3).
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
    """Deriva 1..cap conceptos de un texto por keywords (determinista, barato). Backstop del etiquetado del LLM
    en la ESCRITURA y motor del mapa conceptual de CORTO en el VISOR."""
    t = text or ""
    out = [c for c, rx in CONCEPT_RES if rx.search(t)]
    return out[:cap]
