from flask import Flask, request, jsonify, send_from_directory
import os
from openai import OpenAI

app = Flask(__name__)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
historial = []

sistema = {"role": "system", "content": "You are a bilingual virtual assistant for Pizza Nova pizzeria. Automatically detect the language the customer uses and always respond in that same language (English or Spanish). Be friendly, brief and clear. PIZZA MENU: 1) Margherita $12 - tomato sauce, mozzarella, fresh basil. 2) Pepperoni $14 - tomato sauce, mozzarella, pepperoni. 3) Hawaiian $13 - tomato sauce, mozzarella, ham, pineapple. 4) BBQ Chicken $15 - BBQ sauce, mozzarella, grilled chicken, red onion. 5) Four Cheese $14 - mozzarella, cheddar, parmesan, gorgonzola. 6) Vegetarian $13 - tomato sauce, mozzarella, peppers, mushrooms, olives, onion, tomato. 7) Diavola $15 - tomato sauce, mozzarella, spicy salami, chiles. 8) Napolitana $13 - tomato sauce, mozzarella, anchovies, olives, oregano. SIZES: Personal 20cm, Medium 30cm, Family 40cm. Base price applies to medium, personal -$3, family +$4. DRINKS: Coca-Cola $2, Pepsi $2, Sprite $2, Water $1, Orange juice $3, Lemonade $3, Beer $4. HOURS: Monday to Thursday 11am-10pm, Friday and Saturday 11am-12am, Sunday 12pm-9pm. DELIVERY available 7 days a week with $2 additional cost. Estimated delivery time 30-45 minutes."}

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
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=historial
    )
    respuesta = response.choices[0].message.content
    historial.append({"role": "assistant", "content": respuesta})
    return jsonify({"respuesta": respuesta})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
