#
# EGRESS DE MODELOS — a dónde sale de verdad una llamada de LLM y con qué credencial.
#
# UN SOLO CÓDIGO, DOS DESPLIEGUES. Quien se auto-hospeda habla con los proveedores directamente y con
# SUS propias claves: es su cuenta, su gasto y su decisión, y este módulo no le cambia nada. En el
# despliegue gestionado la salida está mediada, y este módulo es la costura donde eso ocurre — un
# PUERTO, no un caso especial repartido por diez ficheros.
#
# Lo que se describe aquí es el MECANISMO: si el entorno declara un egress mediado, se usa; si no, se
# habla directo. La política de por qué un despliegue elige una cosa u otra no vive en este repo.
#
# LA INVERSIÓN QUE IMPORTA. Sin esto, cada call site elegía endpoint Y llevaba la credencial. Con esto,
# el call site declara qué QUIERE (un modelo) y el egress decide POR DÓNDE sale. Mientras un proceso
# pueda nombrar el endpoint y tenga la clave, la clave tiene que estar de su lado — que es justo lo que
# se quiere dejar de hacer.
#
# FAIL-CLOSED, Y A PROPÓSITO. Si el despliegue declara egress mediado y falta la credencial para
# usarlo, esto NO se cae hacia atrás a hablar directo con el proveedor. Un fallback silencioso
# convertiría un despliegue incompleto en una fuga que funciona — el mismo patrón
# «guarded-until-configured» que dejó una superficie abierta nueve días. Prefiere romper y decirlo.
#
from __future__ import annotations

import os

from loguru import logger

# El endpoint mediado y la credencial con la que este proceso se identifica ante él.
_URL_ENV = "ZAELAR_GATEWAY_URL"
_TOKEN_ENV = "CONTROL_PLANE_SERVICE_TOKEN"

# base_url del proveedor → nombre corto que entiende el egress mediado. Es un MAPA DE ROUTING, no una
# credencial: dice «esta llamada iba dirigida a tal familia», y quien tenga la clave decidirá.
_PROVIDER_BY_HOST = (
    ("aimlapi.com", "aimlapi"),
    ("api.x.ai", "xai"),
    ("api.z.ai", "zai"),
    ("mistral.ai", "mistral"),
)


def mediated() -> bool:
    """¿Este despliegue saca las llamadas por un egress mediado?"""
    from nucleo import cloud_account
    return cloud_account.is_cloud_account() and bool((os.getenv(_URL_ENV) or "").strip())


def is_local_endpoint(base_url: str) -> bool:
    u = (base_url or "").lower()
    return "11434" in u or "localhost" in u or "127.0.0.1" in u


def provider_of(base_url: str) -> str:
    u = (base_url or "").lower()
    for needle, name in _PROVIDER_BY_HOST:
        if needle in u:
            return name
    return ""


def route(base_url: str, api_key: str) -> tuple[str, str, dict]:
    """`(base_url, api_key, headers_extra)` efectivos para esta llamada.

    Sin egress mediado devuelve lo que le dan, tal cual — self-host queda byte-idéntico. Un endpoint
    LOCAL (Ollama) tampoco se toca nunca: no cuesta dinero y no hay nada que mediar.
    """
    if is_local_endpoint(base_url) or not mediated():
        return base_url, api_key, {}

    token = (os.getenv(_TOKEN_ENV) or "").strip()
    if not token:
        # Ver la nota de fail-closed en la cabecera. Se avisa fuerte y se devuelve el destino mediado
        # SIN credencial: la llamada fallará con 401 en el egress, que es un fallo visible y acotado,
        # en vez de salir por la puerta de atrás con la clave del proveedor.
        logger.error(
            f"llm_egress: egress mediado declarado pero sin {_TOKEN_ENV} — la llamada fallará. "
            "NO se cae hacia atrás a hablar directo con el proveedor: eso convertiría un despliegue "
            "incompleto en una fuga que funciona."
        )
    return (os.getenv(_URL_ENV) or "").strip().rstrip("/"), token, _headers(base_url)


def _headers(base_url: str) -> dict:
    """La familia a la que iba dirigida la llamada. Va en cabecera y NO en el cuerpo para que el
    egress pueda enrutar sin abrir el JSON, y porque el cuerpo lo compone el modelo — no queremos que
    lo que un modelo escriba pueda cambiar a qué proveedor se factura."""
    p = provider_of(base_url)
    return {"X-Zaelar-Provider": p} if p else {}


def bills_upstream() -> bool:
    """¿Quién apunta el gasto en el ledger?

    Con egress mediado, el que hizo la llamada de verdad — no este proceso. Contarlo también aquí
    duplicaría el cargo, y un cliente que paga el doble por turno es un fallo peor que no cobrar.
    Lo que este proceso SÍ sigue haciendo es descontar de su arriendo local (`energy_lease`): ese
    contador es un techo de seguridad, no una factura, y tiene que seguir funcionando aunque el enlace
    con la nube esté caído.
    """
    return mediated()
