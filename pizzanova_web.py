"""Pagina web de chat para el chatbot de Pizza Nova.

Uso:
    ollama serve
    ~/.venvs/pizzanova/bin/streamlit run pizzanova_web.py
"""
import json
import os
import threading
import urllib.error

import streamlit as st

import chatbot

st.set_page_config(page_title="Pizza Nova", page_icon="🍕", layout="wide")

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

pregunta = st.chat_input("Escribe tu mensaje… (ej: quiero 2 pepperoni)")
if pregunta:
    pregunta = pregunta.strip()
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
                        chatbot.trozos_ollama(chatbot.mensajes_respuesta(ss.historial, resultados))
                    )
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            ss.historial.pop()
            ss.chat.pop()
            st.error("No pude conectar con la IA. Comprueba que Ollama esté abierto (`ollama serve`).")
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
