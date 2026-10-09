import json
import os
import time

from dotenv import load_dotenv
from flask import Flask, jsonify, request, render_template
from web3 import Web3

# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()



RPC_URL = "https://ethereum-sepolia-rpc.publicnode.com"

# flask --app app run --host=0.0.0.0 --port=5000 --debug
# smarthn contract https://eth-sepolia.blockscout.com/address/0xB304B0588AB62f87EffAe8e662E945F883334278?tab=contract.
PRIVATE_KEY = "c0b927c04c3dd08d8951923103450a528d8d786cb153985bb6dde7c1d02c1ddf"




CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "0xB304B0588AB62f87EffAe8e662E945F883334278")
CHAIN_ID = int(os.getenv("CHAIN_ID", "11155111"))
CASA_ID = os.getenv("CASA_ID", "casa01")

if not RPC_URL:
    raise RuntimeError("Falta RPC_URL en el archivo .env")

if not PRIVATE_KEY:
    raise RuntimeError("Falta PRIVATE_KEY en el archivo .env")

if not CONTRACT_ADDRESS:
    raise RuntimeError("Falta CONTRACT_ADDRESS en el archivo .env")

# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

@app.get("/view")
def ver_historial():
    return render_template("view.html")

# ============================================================
# WEB3
# ============================================================

w3 = Web3(Web3.HTTPProvider(RPC_URL))

if not w3.is_connected():
    raise RuntimeError("No se pudo conectar al nodo blockchain")

account = w3.eth.account.from_key(PRIVATE_KEY)

# ============================================================
# ABI DEL CONTRATO
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ABI_PATH = os.path.join(BASE_DIR, "casa.abi.json")

with open(ABI_PATH, "r", encoding="utf-8") as archivo:
    contrato_abi = json.load(archivo)

contrato = w3.eth.contract(
    address=Web3.to_checksum_address(CONTRACT_ADDRESS),
    abi=contrato_abi
)

# ============================================================
# RUTA PRINCIPAL
# ============================================================

@app.get("/")
def inicio():
    return jsonify({
        "ok": True,
        "servicio": "API Casa Inteligente + Blockchain",
        "wallet": account.address,
        "contrato": CONTRACT_ADDRESS,
        "chain_id": CHAIN_ID
    })

# ============================================================
# REGISTRAR EVENTO EN BLOCKCHAIN
# ============================================================

@app.post("/registrar")
def registrar():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "Se requiere un objeto JSON"}), 400

    casa = str(data.get("casa", CASA_ID)).strip()
    dispositivo = str(data.get("dispositivo", "")).strip()
    estado = str(data.get("estado", "")).strip()

    try:
        timestamp = int(data.get("timestamp", int(time.time())))
    except (TypeError, ValueError):
        timestamp = 0

    if not casa:
        return jsonify({
            "ok": False,
            "error": "Falta el campo casa"
        }), 400

    if not dispositivo:
        return jsonify({
            "ok": False,
            "error": "Falta el campo dispositivo"
        }), 400

    if not estado:
        return jsonify({
            "ok": False,
            "error": "Falta el campo estado"
        }), 400

    if timestamp <= 0:
        return jsonify({
            "ok": False,
            "error": "Timestamp invalido"
        }), 400

    try:
        nonce = w3.eth.get_transaction_count(
            account.address,
            "pending"
        )

        llamada = contrato.functions.registrarEvento(
            casa, dispositivo, estado, timestamp
        )
        gas_estimado = llamada.estimate_gas({"from": account.address})
        gas_limite = (gas_estimado * 120 + 99) // 100
        gas_precio = w3.eth.gas_price
        max_fee_wei = int(os.getenv("MAX_TX_FEE_WEI", "1000000000000"))
        if gas_limite * gas_precio > max_fee_wei:
            return jsonify({"ok": False, "error": "Gas supera el limite configurado"}), 422
        transaccion = llamada.build_transaction({
            "from": account.address,
            "nonce": nonce,
            "chainId": CHAIN_ID,
            "gas": gas_limite,
            "gasPrice": gas_precio
        })

        firmada = account.sign_transaction(transaccion)

        tx_hash = w3.eth.send_raw_transaction(
            firmada.raw_transaction
        )

        recibo = w3.eth.wait_for_transaction_receipt(
            tx_hash,
            timeout=120
        )

        if recibo.status != 1:
            return jsonify({
                "ok": False,
                "error": "La transaccion fue revertida",
                "transaction_hash": tx_hash.hex()
            }), 500

        return jsonify({
            "ok": True,
            "mensaje": "Evento registrado en blockchain",
            "transaction_hash": tx_hash.hex(),
            "block_number": recibo.blockNumber,
            "casa": casa,
            "dispositivo": dispositivo,
            "estado": estado,
            "timestamp": timestamp
        })

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500

# ============================================================
# CONSULTAR CANTIDAD TOTAL DE EVENTOS
# ============================================================

@app.get("/eventos/count")
def total_eventos():
    try:
        total = contrato.functions.obtenerTotalEventos().call()

        return jsonify({
            "ok": True,
            "total": total
        })

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500

# ============================================================
# CONSULTAR EVENTO POR ID
# ============================================================

@app.get("/eventos/<int:evento_id>")
def obtener_evento(evento_id):
    try:
        evento = contrato.functions.obtenerEvento(
            evento_id
        ).call()

        return jsonify({
            "ok": True,
            "id": evento_id,
            "evento": {
                "casa": evento[0],
                "dispositivo": evento[1],
                "estado": evento[2],
                "timestamp": evento[3],
                "registrado_por": evento[4]
            }
        })

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500

# ============================================================
# CONSULTAR TODOS LOS EVENTOS
# ============================================================

@app.get("/eventos")
def obtener_todos_eventos():
    try:
        eventos = contrato.functions.obtenerTodosLosEventos().call()

        resultado = []

        for indice, evento in enumerate(eventos):
            resultado.append({
                "id": indice,
                "casa": evento[0],
                "dispositivo": evento[1],
                "estado": evento[2],
                "timestamp": evento[3],
                "registrado_por": evento[4]
            })

        return jsonify({
            "ok": True,
            "total": len(resultado),
            "eventos": resultado
        })

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500

# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5001")),
        debug=False
    )
