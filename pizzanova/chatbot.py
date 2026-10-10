import json
import os
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime

# Si hay una API key de OpenAI se usa OpenAI (para publicarlo en internet);
# si no, Ollama en este ordenador.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
if OPENAI_API_KEY:
    PROVEEDOR = "OpenAI"
    URL = "https://api.openai.com/v1/chat/completions"
    MODELO = os.environ.get("OPENAI_MODEL", "gpt-6-luna")
else:
    PROVEEDOR = "Ollama"
    URL = "http://localhost:11434/api/chat"
    MODELO = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")
MAX_MENSAJES = 20  # mensajes recientes que se envian al modelo
ARCHIVO_PEDIDOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pedidos.json")

MENU = {
    "Margherita": 12,
    "Pepperoni": 14,
    "Hawaiana": 13,
    "Cuatro Quesos": 15,
    "Vegetariana": 13,
    "Barbacoa": 15,
    "Mexicana": 15,
    "Napolitana": 13,
    "Carnivora": 16,
    "Pollo Pesto": 15,
}

texto_menu = "\n".join(f"- {pizza}: ${precio}" for pizza, precio in MENU.items())

# Cada turno tiene dos pasos:
#   1. El modelo decide que acciones hacer con el pedido, rellenando un JSON con formato fijo
#      (Ollama obliga a que la salida cumpla el esquema, asi que no puede salir mal escrita).
#   2. Python ejecuta las acciones y el modelo escribe la respuesta sabiendo el resultado real.

INSTRUCCIONES_ACCIONES = (
    "Eres el sistema de pedidos de la pizzeria Pizza Nova. Lee el ULTIMO mensaje del cliente "
    "y decide que cambios hay que hacer en el pedido.\n"
    f"Menu:\n{texto_menu}\n\n"
    "Acciones posibles:\n"
    '- "agregar": el cliente pide pizzas. Indica "pizza" y "cantidad".\n'
    '- "quitar": el cliente quiere quitar pizzas del pedido. Indica "pizza" y "cantidad" (1 si no lo dice).\n'
    '- "confirmar": el cliente ha terminado y ya dio su nombre. Indica "nombre" y, si es a domicilio, '
    '"direccion" (vacia si recoge en la tienda). Busca el nombre y la direccion en toda la conversacion.\n'
    "Reglas:\n"
    "- Solo acciones que pida el ULTIMO mensaje. Lo pedido en mensajes anteriores ya esta en el pedido actual.\n"
    "- Si el cliente solo pregunta, saluda o falta informacion, devuelve una lista vacia.\n"
    "- No confirmes si el cliente no ha dado su nombre, o si es a domicilio y falta la direccion.\n"
    "- No confirmes si el cliente parece querer seguir pidiendo, ni si el pedido actual esta vacio."
)

INSTRUCCIONES_RESPUESTA = (
    "Eres el asistente virtual de la pizzeria Pizza Nova. "
    "Responde siempre en el idioma del cliente, de forma breve y amable.\n"
    "Puedes informar sobre el menu y los precios, y tomar pedidos. Este es el menu completo:\n"
    f"{texto_menu}\n\n"
    "El sistema de pedidos ya ha procesado el ultimo mensaje del cliente. Usa SOLO los datos de "
    "'Estado del pedido' y 'Acciones realizadas' de abajo para hablar del pedido y del total; "
    "nunca calcules ni inventes totales. Si una accion dice 'Pedido CONFIRMADO', describe exactamente "
    "ese pedido (pizzas y total de esa accion), aunque el estado ahora este vacio, y di claramente "
    "que el pedido ya quedo confirmado (no preguntes si es correcto).\n"
    "Para confirmar un pedido hace falta el nombre del cliente y saber si es para recoger o a domicilio "
    "(con direccion). Si falta algo, pideselo. Si el pedido aun no esta confirmado, no digas que lo esta.\n"
    "No inventes pizzas, precios, promociones ni otros datos que no esten en el menu. "
    "Si te preguntan otra cosa, di amablemente que solo puedes ayudar con el menu y los pedidos."
)

ESQUEMA_ACCIONES = {
    "type": "object",
    "properties": {
        "acciones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "accion": {"type": "string", "enum": ["agregar", "quitar", "confirmar"]},
                    "pizza": {"type": ["string", "null"]},
                    "cantidad": {"type": ["integer", "null"]},
                    "nombre": {"type": ["string", "null"]},
                    "direccion": {"type": ["string", "null"]},
                },
                # OpenAI exige que todos los campos esten en "required" (los que no apliquen van como null)
                "required": ["accion", "pizza", "cantidad", "nombre", "direccion"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["acciones"],
    "additionalProperties": False,
}

pedido = {}  # nombre de pizza -> cantidad
ultimo_confirmado = {}  # datos del ultimo pedido confirmado


def normalizar(texto):
    """Pasa a minusculas y quita tildes, para que 'Carnívora' encuentre 'Carnivora'."""
    texto = unicodedata.normalize("NFD", str(texto).lower().strip())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def buscar_pizza(nombre):
    """Devuelve el nombre exacto del menu que corresponde a 'nombre', o None."""
    buscado = normalizar(nombre).removeprefix("pizza ").strip()
    if not buscado:
        return None
    for pizza in MENU:
        if normalizar(pizza) == buscado:
            return pizza
    for pizza in MENU:
        if buscado in normalizar(pizza) or normalizar(pizza) in buscado:
            return pizza
    return None


def leer_cantidad(valor, por_defecto):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return por_defecto


def total_pedido():
    return sum(MENU[pizza] * cant for pizza, cant in pedido.items())


def resumen_pedido():
    if not pedido:
        return "El pedido esta vacio."
    lineas = [f"{cant}x {pizza} (${MENU[pizza] * cant})" for pizza, cant in pedido.items()]
    return "Pedido: " + ", ".join(lineas) + f". Total: ${total_pedido()}"


def agregar_pizza(pizza, cantidad=1):
    nombre = buscar_pizza(pizza)
    if nombre is None:
        return f"'{pizza}' no esta en el menu, no se agrego."
    cantidad = leer_cantidad(cantidad, 1)
    if cantidad < 1:
        return "La cantidad debe ser al menos 1."
    pedido[nombre] = pedido.get(nombre, 0) + cantidad
    return f"Agregado {cantidad}x {nombre}. {resumen_pedido()}"


def quitar_pizza(pizza, cantidad=1):
    nombre = buscar_pizza(pizza)
    if nombre is None or nombre not in pedido:
        return f"'{pizza}' no esta en el pedido. {resumen_pedido()}"
    cantidad = max(leer_cantidad(cantidad, 1), 1)
    pedido[nombre] -= cantidad
    if pedido[nombre] <= 0:
        del pedido[nombre]
    return f"Quitado {cantidad}x {nombre}. {resumen_pedido()}"


def lo_escribio_el_cliente(dato, texto_cliente):
    """True si todas las palabras de 'dato' aparecen en lo que escribio el cliente."""
    palabras = normalizar(dato).replace(",", " ").split()
    escrito = normalizar(texto_cliente).replace(",", " ").split()
    return bool(palabras) and all(p in escrito for p in palabras)


def confirmar_pedido(nombre, direccion="", texto_cliente=""):
    if not pedido:
        return "No se puede confirmar: el pedido esta vacio."
    nombre = str(nombre or "").strip()
    direccion = str(direccion or "").strip()
    # A veces el modelo pone "recoger" en la direccion
    if normalizar(direccion) in ("recoger", "recoger en tienda", "para recoger", "tienda", "ninguna", "none"):
        direccion = ""
    # El modelo podria inventarse datos ("no especificado", "Juan"...): solo vale lo que escribio el cliente
    if not lo_escribio_el_cliente(nombre, texto_cliente):
        return "No se puede confirmar: falta el nombre del cliente."
    if direccion and not lo_escribio_el_cliente(direccion, texto_cliente):
        return "No se puede confirmar: falta la direccion de entrega."
    entrega = "domicilio" if direccion else "recoger"

    registro = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "nombre": nombre,
        "entrega": entrega,
        "direccion": direccion,
        "pizzas": dict(pedido),
        "total": total_pedido(),
    }
    pedidos = []
    if os.path.exists(ARCHIVO_PEDIDOS):
        with open(ARCHIVO_PEDIDOS, encoding="utf-8") as f:
            pedidos = json.load(f)
    pedidos.append(registro)
    with open(ARCHIVO_PEDIDOS, "w", encoding="utf-8") as f:
        json.dump(pedidos, f, ensure_ascii=False, indent=2)

    ultimo_confirmado.clear()
    ultimo_confirmado.update(registro)
    donde = f"a domicilio en {direccion}" if direccion else "para recoger en la tienda"
    texto = f"Pedido CONFIRMADO a nombre de {registro['nombre']}, {donde}. {resumen_pedido()}"
    pedido.clear()
    return texto


def mensaje_confirmacion(registro):
    """Mensaje fijo de confirmacion: lo escribe el codigo para que sea siempre exacto."""
    pizzas = ", ".join(f"{cant}x {pizza}" for pizza, cant in registro["pizzas"].items())
    if registro["entrega"] == "domicilio":
        entrega = f"Lo enviaremos a {registro['direccion']}."
    else:
        entrega = "Puedes pasar a recogerlo a la tienda."
    return (
        f"¡Listo, {registro['nombre']}! Tu pedido esta confirmado: {pizzas}. "
        f"Total: ${registro['total']}. {entrega} ¡Gracias por elegir Pizza Nova!"
    )


def ejecutar_accion(accion, texto_cliente):
    tipo = accion.get("accion")
    if tipo == "agregar":
        return agregar_pizza(accion.get("pizza") or "", accion.get("cantidad") or 1)
    if tipo == "quitar":
        return quitar_pizza(accion.get("pizza") or "", accion.get("cantidad") or 1)
    if tipo == "confirmar":
        return confirmar_pedido(accion.get("nombre") or "", accion.get("direccion") or "", texto_cliente)
    return f"Accion desconocida: {tipo}"


def trozos_ia(mensajes, formato=None):
    """Envia mensajes a la IA y va devolviendo la respuesta a trozos, segun llega."""
    if PROVEEDOR == "OpenAI":
        yield from trozos_openai(mensajes, formato)
    else:
        yield from trozos_ollama(mensajes, formato)


def trozos_ollama(mensajes, formato=None):
    datos = {
        "model": MODELO,
        "messages": mensajes,
        "stream": True,
        "options": {"temperature": 0},  # respuestas mas consistentes
    }
    if formato:
        datos["format"] = formato
    body = json.dumps(datos).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})

    with urllib.request.urlopen(req, timeout=300) as r:
        # Con stream=True, Ollama manda un objeto JSON por linea
        for linea in r:
            if not linea.strip():
                continue
            parte = json.loads(linea)
            if "error" in parte:
                raise RuntimeError(parte["error"])
            yield parte.get("message", {}).get("content", "")
            if parte.get("done"):
                break


def trozos_openai(mensajes, formato=None):
    datos = {"model": MODELO, "messages": mensajes, "stream": True}
    if formato:
        datos["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "acciones", "schema": formato, "strict": True},
        }
    body = json.dumps(datos).encode("utf-8")
    req = urllib.request.Request(
        URL,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"},
    )

    with urllib.request.urlopen(req, timeout=120) as r:
        # OpenAI manda lineas "data: {...}" y termina con "data: [DONE]"
        for linea in r:
            linea = linea.decode("utf-8").strip()
            if not linea.startswith("data:"):
                continue
            dato = linea[len("data:"):].strip()
            if dato == "[DONE]":
                break
            parte = json.loads(dato)
            if "error" in parte:
                raise RuntimeError(parte["error"].get("message", parte["error"]))
            for opcion in parte.get("choices", []):
                yield opcion.get("delta", {}).get("content") or ""


def llamar_ia(mensajes, formato=None, mostrar=False):
    """Envia mensajes a la IA y devuelve el texto de la respuesta.

    Con mostrar=True imprime la respuesta mientras llega."""
    respuesta = ""
    for trozo in trozos_ia(mensajes, formato):
        if mostrar:
            print(trozo, end="", flush=True)
        respuesta += trozo
    return respuesta


def para_modelo(historial, con_acciones):
    """Prepara los mensajes recientes para la IA.

    Con con_acciones=True, cada respuesta del bot lleva delante las acciones que ya se hicieron,
    para que el modelo no repita acciones de mensajes anteriores."""
    mensajes = []
    for m in historial[-MAX_MENSAJES:]:
        contenido = m["content"]
        if con_acciones and m["role"] == "assistant":
            hechas = " | ".join(m.get("acciones", [])) or "ninguna"
            contenido = f"[Acciones ya ejecutadas: {hechas}]\n{contenido}"
        mensajes.append({"role": m["role"], "content": contenido})
    return mensajes


def ejecutar_acciones(historial):
    """Paso 1: el modelo decide las acciones (JSON con formato fijo) y Python las ejecuta.

    Devuelve la lista de resultados."""
    sistema_acciones = INSTRUCCIONES_ACCIONES + f"\n\nPedido actual: {resumen_pedido()}"
    decision = llamar_ia(
        [{"role": "system", "content": sistema_acciones}] + para_modelo(historial, con_acciones=True),
        formato=ESQUEMA_ACCIONES,
    )
    acciones = json.loads(decision).get("acciones", [])

    texto_cliente = "\n".join(m["content"] for m in historial if m["role"] == "user")
    return [ejecutar_accion(accion, texto_cliente) for accion in acciones]


def hay_confirmacion(resultados):
    return any(r.startswith("Pedido CONFIRMADO") for r in resultados)


def mensajes_respuesta(historial, resultados):
    """Paso 2: mensajes para que el modelo escriba la respuesta con los datos reales."""
    sistema_respuesta = (
        INSTRUCCIONES_RESPUESTA
        + f"\n\nEstado del pedido: {resumen_pedido()}"
        + "\nAcciones realizadas con el ultimo mensaje: "
        + (" | ".join(resultados) if resultados else "ninguna")
        + "\nIMPORTANTE: el pedido NO esta confirmado todavia. No digas que esta confirmado; "
        "si el cliente ya pidio pizzas, pidele su nombre y si es para recoger o a domicilio."
    )
    return [{"role": "system", "content": sistema_respuesta}] + para_modelo(historial, con_acciones=False)


def responder(historial):
    """Procesa el ultimo mensaje del cliente: ejecuta las acciones y escribe la respuesta.

    Devuelve (respuesta, resultados_de_las_acciones)."""
    resultados = ejecutar_acciones(historial)
    for resultado in resultados:
        print(f"  [{resultado}]")

    if hay_confirmacion(resultados):
        respuesta = mensaje_confirmacion(ultimo_confirmado)
        print(f"Bot: {respuesta}", end="")
        return respuesta, resultados

    print("Bot: ", end="", flush=True)
    respuesta = llamar_ia(mensajes_respuesta(historial, resultados), mostrar=True)
    return respuesta, resultados


def main():
    historial = []
    print(f"Chatbot Pizza Nova listo ({PROVEEDOR}, modelo: {MODELO}). Escribe 'salir' para terminar.")
    print("Puedes preguntar por el menu o hacer tu pedido.\n")

    while True:
        try:
            pregunta = input("Tu: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not pregunta:
            continue
        if pregunta.lower() in ("salir", "exit", "quit", "adios"):
            break

        historial.append({"role": "user", "content": pregunta})
        print()
        try:
            respuesta, resultados = responder(historial)
        except KeyboardInterrupt:
            print("\n[Respuesta cancelada]\n")
            historial.pop()
            continue
        except urllib.error.HTTPError as e:
            print(f"\n[Error de {PROVEEDOR} {e.code}: {e.read().decode('utf-8', 'ignore')}]")
            if PROVEEDOR == "Ollama":
                print(f"[Comprueba que el modelo existe: ollama pull {MODELO}]")
            print()
            historial.pop()
            continue
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            print(f"\n[No pude conectar con {PROVEEDOR}: {e}]")
            if PROVEEDOR == "Ollama":
                print("[Comprueba que este corriendo con: ollama serve]")
            print()
            historial.pop()
            continue
        except (RuntimeError, json.JSONDecodeError) as e:
            print(f"\n[Error: {e}]\n")
            historial.pop()
            continue

        historial.append({"role": "assistant", "content": respuesta, "acciones": resultados})
        print("\n")
        # Pedido terminado: se empieza de cero para que el modelo no repita ese pedido
        if hay_confirmacion(resultados):
            historial[:] = [{"role": "assistant", "content": "(El pedido anterior ya esta confirmado y cerrado.)"}]

    if pedido:
        print(f"Tu pedido no se confirmo y se descarto ({resumen_pedido()}).")
    print("¡Gracias por visitar Pizza Nova! Hasta pronto.")


if __name__ == "__main__":
    main()
