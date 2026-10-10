#!/bin/zsh
# Inicia la demo de Pizza Nova: Ollama + pagina web de chat.
cd "$(dirname "$0")"

if ! curl -s -m 2 localhost:11434/api/tags >/dev/null; then
    echo "Iniciando Ollama..."
    ollama serve >/dev/null 2>&1 &
    for i in {1..15}; do
        curl -s -m 1 localhost:11434/api/tags >/dev/null && break
        sleep 1
    done
fi

echo "Abriendo Pizza Nova en el navegador (para cerrarla pulsa Ctrl+C)..."
~/.venvs/pizzanova/bin/streamlit run pizzanova_web.py --server.headless false --browser.gatherUsageStats false
