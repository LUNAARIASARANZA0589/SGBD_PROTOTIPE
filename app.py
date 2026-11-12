
"""Interfaz web (Flask) del Gestor de Orientación. Reutiliza gestor.py.
Ejecutar:  python app.py   →  abrir http://localhost:5000
"""
import getpass
import io
import os
import re
import secrets
import sys
import tempfile
import time
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

from bson import ObjectId
from flask import (Flask, jsonify, redirect, render_template, request, send_file,
                   session, url_for)
from pymongo import DESCENDING
from werkzeug.security import check_password_hash, generate_password_hash

from gestor import (CAMPOS_ALUMNO, CAMPOS_CANALIZACION, DIR_PDF, a_fecha_iso,
                    conectar, construir_filtro, generar_pdf, importar, limpiar)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB
db = conectar()
db.usuarios.create_index("usuario", unique=True)

# ---------------- Seguridad: sesiones y llave secreta ----------------
def llave_secreta():
    if os.getenv("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    f = Path(".secret_key")  # se crea una vez y se conserva entre reinicios
    if not f.exists():
        f.write_text(secrets.token_hex(32))
        try:
            f.chmod(0o600)
        except OSError:
            pass
    return f.read_text().strip()


app.secret_key = llave_secreta()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  PERMANENT_SESSION_LIFETIME=8 * 3600)  # la sesión dura 8 horas
INTENTOS = {}  # ip -> (fallos, bloqueado_hasta)  — freno a contraseñas adivinadas
MAX_FALLOS, BLOQUEO_SEG = 5, 300


def crear_usuario(usuario, clave, rol="orientador"):
    db.usuarios.update_one({"usuario": usuario.strip().lower()},
                           {"$set": {"clave": generate_password_hash(clave), "rol": rol}}, upsert=True)


@app.before_request
def exigir_sesion():
    if request.endpoint in ("login", "static") or "usuario" in session:
        return None
    if request.path.startswith(("/api/", "/pdf")):
        return jsonify({"error": "Sesión vencida. Inicia sesión de nuevo."}), 401
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        ip = request.remote_addr
        fallos, hasta = INTENTOS.get(ip, (0, 0))
        if hasta > time.time():
            error = f"Demasiados intentos. Espera {int((hasta - time.time()) // 60) + 1} minuto(s)."
        else:
            u = db.usuarios.find_one({"usuario": request.form.get("usuario", "").strip().lower()})
            if u and check_password_hash(u["clave"], request.form.get("clave", "")):
                INTENTOS.pop(ip, None)
                session.clear()
                session.permanent = True
                session["usuario"], session["rol"] = u["usuario"], u.get("rol", "orientador")
                return redirect(url_for("inicio"))
            fallos += 1
            INTENTOS[ip] = (fallos, time.time() + BLOQUEO_SEG if fallos >= MAX_FALLOS else 0)
            error = "Usuario o contraseña incorrectos."
    return render_template("login.html", error=error)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def limpio(doc):
    doc["_id"] = str(doc["_id"])
    return doc


@app.get("/")
def inicio():
    return render_template("index.html", usuario=session["usuario"])


@app.get("/api/autocompletar")
def autocompletar():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    cur = db.alumnos.find({"numero_control": {"$regex": "^" + re.escape(q)}},
                          {"_id": 0, "numero_control": 1, "nombre": 1,
                           "apellido_paterno": 1, "apellido_materno": 1}).limit(8)
    return jsonify(list(cur))


@app.get("/api/alumno/<control>")
def alumno(control):
    a = db.alumnos.find_one({"numero_control": control}, {"_id": 0})
    if not a:
        return jsonify({"encontrado": False})
    a["canalizaciones_anteriores"] = db.canalizaciones.count_documents({"numero_control": control})
    return jsonify({"encontrado": True, "alumno": a})


@app.post("/api/canalizaciones")
def crear():
    d = request.get_json(force=True)
    control = limpiar(d.get("numero_control"))
    if not control:
        return jsonify({"error": "Falta el número de control"}), 400
    datos = {k: limpiar(d.get(k)) for k in CAMPOS_ALUMNO + CAMPOS_CANALIZACION}
    datos["numero_control"] = control
    datos["fecha_atencion"] = a_fecha_iso(datos["fecha_atencion"]) or date.today().isoformat()
    datos["canalizaciones_anteriores"] = db.canalizaciones.count_documents({"numero_control": control})
    datos["registrado_por"] = session["usuario"]  # quién capturó la canalización
    db.alumnos.update_one({"numero_control": control},
                          {"$set": {k: datos[k] for k in CAMPOS_ALUMNO}}, upsert=True)
    res = db.canalizaciones.insert_one(datos)
    return jsonify({"id": str(res.inserted_id), "anteriores": datos["canalizaciones_anteriores"]})


@app.get("/api/canalizaciones")
def listar():
    filtro = construir_filtro([f"{k}={v}" for k, v in request.args.items() if v.strip()])
    docs = db.canalizaciones.find(filtro).sort("fecha_atencion", DESCENDING).limit(300)
    return jsonify([limpio(d) for d in docs])


@app.post("/api/importar")
def api_importar():
    f = request.files.get("archivo")
    if not f or not f.filename.lower().endswith((".xls", ".xlsx")):
        return jsonify({"error": "Sube un archivo .xls o .xlsx"}), 400
    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / Path(f.filename).name
        f.save(ruta)
        salida = io.StringIO()
        with redirect_stdout(salida):
            importar(db, [str(ruta)])
    return jsonify({"mensaje": salida.getvalue().strip()})


@app.get("/pdf/<id>")
def pdf_uno(id):
    d = db.canalizaciones.find_one({"_id": ObjectId(id)}, {"_id": 0})
    if not d:
        return "No encontrada", 404
    ruta = generar_pdf([d], f"canalizacion_{d['numero_control']}_{d['fecha_atencion']}.pdf")
    return send_file(Path(ruta).resolve(), as_attachment=True)


@app.get("/pdf-lote")
def pdf_lote():
    filtro = construir_filtro([f"{k}={v}" for k, v in request.args.items() if v.strip()])
    docs = list(db.canalizaciones.find(filtro, {"_id": 0}).sort("apellido_paterno", 1))
    if not docs:
        return "Sin resultados", 404
    ruta = generar_pdf(docs, f"lote_{date.today().isoformat()}.pdf")
    return send_file(Path(ruta).resolve(), as_attachment=True)


def primer_usuario():
#Ya cree un usuario administrador, pero si no existiera, este código permite crear uno.
#Usuario: arinn, contraseña: arinndev
    print("No hay usuarios. Crea el administrador.")
    while True:
        u = input("Usuario: ").strip()
        c = getpass.getpass("Contraseña (mínimo 8 caracteres): ")
        if u and len(c) >= 8 and c == getpass.getpass("Repite la contraseña: "):
            crear_usuario(u, c, "admin")
            return
        print("Datos inválidos o contraseñas distintas. Intenta de nuevo.\n")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "crear-usuario":  
        u = input("Usuario: ").strip()
        c = getpass.getpass("Contraseña (mínimo 8 caracteres): ")
        if not u or len(c) < 8:
            sys.exit("Usuario vacío o contraseña demasiado corta.")
        crear_usuario(u, c, input("Rol (admin/orientador) [orientador]: ").strip() or "orientador")
        sys.exit("Usuario guardado.")
    if db.usuarios.count_documents({}) == 0:
        primer_usuario()
    app.run(host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "5000")), debug=False)
