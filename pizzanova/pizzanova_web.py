"""Pagina web de chat para el chatbot de Pizza Nova.

Uso en tu Mac (con Ollama):
    ./iniciar_demo.sh

En Streamlit Community Cloud se usa OpenAI: pon OPENAI_API_KEY en los "Secrets" de la app.
"""
import json
import os
import threading
import urllib.error

import streamlit as st

# En Streamlit Cloud la API key esta en los Secrets; se pasa a chatbot.py como variable de entorno
try:
    if "OPENAI_API_KEY" in st.secrets:
        os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
    if "OPENAI_MODEL" in st.secrets:
        os.environ["OPENAI_MODEL"] = st.secrets["OPENAI_MODEL"]
except FileNotFoundError:
    pass  # sin archivo de secrets: se usa Ollama

import chatbot  # noqa: E402  (despues de leer los secrets)

st.set_page_config(page_title="Pizza Nova", page_icon="🍕", layout="wide")

# Limites para que la pagina publica no se use para gastar la API
MAX_LETRAS = 500
MAX_MENSAJES_VISITA = 40

BIENVENIDA = (
    "¡Hola! 👋 Bienvenido a **Pizza Nova**. Puedo enseñarte el menú y tomar tu pedido, "
    "para recoger o a domicilio. ¿Qué te apetece hoy?"
)


# chatbot.py guarda el pedido en variables globales. Cada visitante tiene el suyo en
# st.session_state y este candado evita que dos visitantes procesen mensajes a la vez.
@st.cache_resource
def candado():
    return threading.Lock()


st.markdown(
    """
    <style>
    .titulo { font-size: 2.4rem; font-weight: 800; color: #c0392b; margin-bottom: 0; }
    .subtitulo { color: #7f8c8d; margin-top: 0; }
    .precio { float: right; font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)

ss = st.session_state
if "historial" not in ss:
    ss.historial = []  # lo que ve el modelo (chatbot.py)
    ss.chat = [{"role": "assistant", "content": BIENVENIDA}]  # lo que se ve en pantalla
    ss.pedido = {}
    ss.ultimo_confirmado = {}


def leer_pedidos():
    if not os.path.exists(chatbot.ARCHIVO_PEDIDOS):
        return []
    with open(chatbot.ARCHIVO_PEDIDOS, encoding="utf-8") as f:
        return json.load(f)


# ---------- Barra lateral: menu, pedido actual y panel de la pizzeria ----------
with st.sidebar:
    st.header("🍕 Menú")
    for pizza, precio in chatbot.MENU.items():
        st.markdown(f"{pizza} <span class='precio'>${precio}</span>", unsafe_allow_html=True)

    st.divider()
    st.header("🛒 Tu pedido")
    if ss.pedido:
        for pizza, cant in ss.pedido.items():
            st.markdown(
                f"{cant}x {pizza} <span class='precio'>${chatbot.MENU[pizza] * cant}</span>",
                unsafe_allow_html=True,
            )
        total = sum(chatbot.MENU[p] * c for p, c in ss.pedido.items())
        st.markdown(f"**Total** <span class='precio'>${total}</span>", unsafe_allow_html=True)
    else:
        st.caption("Todavía no has pedido nada.")

    if st.button("🔄 Empezar de nuevo", use_container_width=True):
        for clave in ("historial", "chat", "pedido", "ultimo_confirmado"):
            del ss[clave]
        st.rerun()

    st.divider()
    pedidos = leer_pedidos()
    with st.expander(f"📋 Panel de la pizzería ({len(pedidos)} pedidos)"):
        if not pedidos:
            st.caption("Aún no hay pedidos confirmados.")
        for p in reversed(pedidos):
            pizzas = ", ".join(f"{c}x {n}" for n, c in p["pizzas"].items())
            entrega = f"🛵 {p['direccion']}" if p["entrega"] == "domicilio" else "🏪 Recoger"
            st.markdown(f"**{p['nombre']}** · ${p['total']}  \n{pizzas}  \n{entrega} · {p['fecha'][11:16]}")

# ---------- Chat ----------
st.markdown("<p class='titulo'>Pizza Nova</p>", unsafe_allow_html=True)
st.markdown("<p class='subtitulo'>Asistente virtual de pedidos</p>", unsafe_allow_html=True)

if ss.pop("celebrar", False):
    st.balloons()

for m in ss.chat:
    with st.chat_message(m["role"], avatar="🍕" if m["role"] == "assistant" else "🙂"):
        st.markdown(m["content"])

mensajes_enviados = sum(1 for m in ss.chat if m["role"] == "user")
if mensajes_enviados >= MAX_MENSAJES_VISITA:
    st.info("Has llegado al límite de mensajes de esta demo. Pulsa 🔄 Empezar de nuevo para seguir.")
    pregunta = None
else:
    pregunta = st.chat_input("Escribe tu mensaje… (ej: quiero 2 pepperoni)", max_chars=MAX_LETRAS)
if pregunta:
    pregunta = pregunta.strip()[:MAX_LETRAS]
    ss.chat.append({"role": "user", "content": pregunta})
    with st.chat_message("user", avatar="🙂"):
        st.markdown(pregunta)

    ss.historial.append({"role": "user", "content": pregunta})
    with st.chat_message("assistant", avatar="🍕"):
        try:
            with candado():
                # Se usa el pedido de este visitante
                chatbot.pedido = ss.pedido
                chatbot.ultimo_confirmado = ss.ultimo_confirmado
                with st.spinner("Pensando…"):
                    resultados = chatbot.ejecutar_acciones(ss.historial)
                confirmado = chatbot.hay_confirmacion(resultados)
                if confirmado:
                    respuesta = chatbot.mensaje_confirmacion(ss.ultimo_confirmado)
                    st.markdown(respuesta)
                else:
                    respuesta = st.write_stream(
                        chatbot.trozos_ia(chatbot.mensajes_respuesta(ss.historial, resultados))
                    )
        except urllib.error.HTTPError as e:
            ss.historial.pop()
            ss.chat.pop()
            if e.code == 401:
                st.error("La API key de OpenAI no es válida. Revísala en los Secrets de la app.")
            elif e.code == 429:
                st.error("La IA está saturada o se acabó el saldo de la API. Inténtalo en un momento.")
            else:
                st.error(f"Error de {chatbot.PROVEEDOR} ({e.code}). Inténtalo de nuevo.")
            st.stop()
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            ss.historial.pop()
            ss.chat.pop()
            if chatbot.PROVEEDOR == "Ollama":
                st.error("No pude conectar con la IA. Comprueba que Ollama esté abierto (`ollama serve`).")
            else:
                st.error("No pude conectar con OpenAI. Inténtalo de nuevo en un momento.")
            st.stop()
        except (RuntimeError, json.JSONDecodeError) as e:
            ss.historial.pop()
            ss.chat.pop()
            st.error(f"Ha ocurrido un error: {e}. Inténtalo de nuevo.")
            st.stop()

    ss.historial.append({"role": "assistant", "content": respuesta, "acciones": resultados})
    ss.chat.append({"role": "assistant", "content": respuesta})
    if confirmado:
        # Pedido terminado: se empieza de cero para que el modelo no repita ese pedido
        ss.historial = [{"role": "assistant", "content": "(El pedido anterior ya esta confirmado y cerrado.)"}]
        ss.celebrar = True
    st.rerun()  # actualiza la barra lateral con el pedido nuevo
