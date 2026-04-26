from flask import Flask, request, jsonify, send_from_directory
import urllib.request
import json

app = Flask(__name__)
historial = []
sistema = {"role": "system", "content": "Eres un asistente virtual de la pizzeria Pizza Nova. Responde solo preguntas sobre el menu, ingredientes, bebidas y horarios. Se amable, breve y claro. MENU DE PIZZAS: 1) Margherita $12 - salsa de tomate, mozzarella, albahaca fresca. 2) Pepperoni $14 - salsa de tomate, mozzarella, pepperoni. 3) Hawaiana $13 - salsa de tomate, mozzarella, jamon, pina. 4) BBQ Chicken $15 - salsa BBQ, mozzarella, pollo a la parrilla, cebolla morada. 5) Cuatro Quesos $14 - mozzarella, cheddar, parmesano, gorgonzola. 6) Vegetariana $13 - salsa de tomate, mozzarella, pimientos, champiñones, aceitunas, cebolla, tomate. 7) Diavola $15 - salsa de tomate, mozzarella, salami picante, chiles. 8) Napolitana $13 - salsa de tomate, mozzarella, anchoas, aceitunas, oregano. TAMAÑOS: Personal 20cm, Mediana 30cm, Familiar 40cm. Precio base aplica a mediana, personal -$3, familiar +$4. BEBIDAS: Coca-Cola $2, Pepsi $2, Sprite $2, Agua $1, Jugo de naranja $3, Limonada $3, Cerveza $4. HORARIOS: Lunes a Jueves 11am-10pm, Viernes y Sabado 11am-12am, Domingo 12pm-9pm. DELIVERY disponible de Lunes a Domingo con costo adicional de $2. Tiempo estimado de entrega 30-45 minutos."}

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/chat", methods=["POST"])
def chat():
    global historial
    datos = request.json
    pregunta = datos.get("mensaje", "")
    if not historial:
        historial = [sistema]
    historial.append({"role": "user", "content": pregunta})
    url = "http://localhost:11434/api/chat"
    body = json.dumps({"model": "llama3.2", "messages": historial, "stream": False}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        resultado = json.loads(r.read())
        respuesta = resultado["message"]["content"]
    historial.append({"role": "assistant", "content": respuesta})
    return jsonify({"respuesta": respuesta})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
