import os
import sqlite3
import uuid
from flask import Flask, redirect, render_template_string, request, session, url_for
from google_oauth_modulo import OAUTH_CONFIGURADO, google_bp, init_google_oauth

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia-esta-clave-en-produccion")

ARCHIVO_DB = os.environ.get("ARCHIVO_DB", "tienda.db")
ADMIN_CLAVE = os.environ.get("ADMIN_CLAVE", "admin123")

app.register_blueprint(google_bp)
init_google_oauth(app)


def db():
    c = sqlite3.connect(ARCHIVO_DB)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = db()
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            apellido TEXT NOT NULL,
            pais TEXT NOT NULL,
            edad INTEGER NOT NULL,
            email TEXT UNIQUE NOT NULL,
            metodo TEXT NOT NULL,
            confirmado INTEGER DEFAULT 0,
            token TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            precio REAL NOT NULL,
            descripcion TEXT DEFAULT ''
        )
    """)
    count = c.execute("SELECT COUNT(*) AS n FROM productos").fetchone()["n"]
    if count == 0:
        c.executemany(
            "INSERT INTO productos (nombre, precio, descripcion) VALUES (?, ?, ?)",
            [
                ("Tiny Lamp LED", 15.0, "Lámpara recargable personalizada"),
                ("Acrílico Grabado QR", 20.0, "Decoración personalizada con enlace o canción"),
                ("Camiseta Personalizada", 18.0, "Estampado de alta definición"),
            ],
        )
    c.commit()
    c.close()


init_db()


@app.route("/")
def inicio():
    msg = request.args.get("msg", "")
    err = request.args.get("err", "")
    c = db()
    productos = c.execute("SELECT * FROM productos").fetchall()
    usuario = None
    if session.get("uid"):
        usuario = c.execute("SELECT * FROM usuarios WHERE id=?", (session["uid"],)).fetchone()
    c.close()

    carrito = session.get("carrito", {})
    total_items = sum(carrito.values())
    total_precio = sum(
        float(p["precio"]) * int(carrito.get(str(p["id"]), 0)) for p in productos
    )

    html = """
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>Tiny Company</title>
      <style>
        body{font-family:system-ui;background:#0f172a;color:#f8fafc;margin:0;padding:16px}
        .wrap{max-width:760px;margin:auto}
        .top{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:16px}
        a{color:#38bdf8;text-decoration:none;font-weight:700}
        .msg{background:#064e3b;color:#a7f3d0;padding:10px;border-radius:10px;margin-bottom:12px}
        .err{background:#7f1d1d;color:#fecaca;padding:10px;border-radius:10px;margin-bottom:12px}
        .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
        .card{background:#1e293b;padding:14px;border-radius:12px}
        button{background:#059669;color:#fff;border:none;padding:8px 12px;border-radius:8px;font-weight:700;cursor:pointer}
        .box{background:#1e293b;padding:14px;border-radius:12px;margin-top:16px}
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="top">
          <div>
            <h2 style="margin:0">Tiny Company</h2>
            <small style="color:#94a3b8">Ilumine su espacio con estilo</small>
          </div>
          <div>
            {% if usuario %}
              <span>{{ usuario["nombre"] }} ({{ usuario["email"] }})</span> |
              <a href="/salir">Salir</a>
            {% else %}
              <a href="/registro">Registro / Acceso (+18)</a>
            {% endif %}
            | <a href="/admin">Admin</a>
          </div>
        </div>

        {% if msg %}<div class="msg">{{ msg }}</div>{% endif %}
        {% if err %}<div class="err">{{ err }}</div>{% endif %}

        <div class="grid">
          {% for p in productos %}
          <div class="card">
            <h3 style="margin-top:0">{{ p["nombre"] }}</h3>
            <p style="color:#cbd5e1;font-size:14px">{{ p["descripcion"] }}</p>
            <p style="font-weight:800;color:#34d399">${{ "%.2f"|format(p["precio"]) }}</p>
            <form method="POST" action="/carrito/agregar/{{ p['id'] }}">
              <button type="submit">Agregar al carrito</button>
            </form>
          </div>
          {% endfor %}
        </div>

        <div class="box">
          <strong>Carrito:</strong> {{ total_items }} artículo(s) — <strong>Total:</strong> ${{ "%.2f"|format(total_precio) }}
          {% if total_items > 0 %}
            <form method="POST" action="/carrito/vaciar" style="display:inline;margin-left:10px">
              <button type="submit" style="background:#dc2626">Vaciar</button>
            </form>
          {% endif %}
        </div>
      </div>
    </body>
    </html>
    """
    return render_template_string(
        html,
        productos=productos,
        usuario=usuario,
        msg=msg,
        err=err,
        total_items=total_items,
        total_precio=total_precio,
    )


@app.route("/carrito/agregar/<int:pid>", methods=["POST"])
def agregar_carrito(pid):
    carrito = session.get("carrito", {})
    key = str(pid)
    carrito[key] = int(carrito.get(key, 0)) + 1
    session["carrito"] = carrito
    return redirect("/?msg=Producto+agregado+al+carrito.")


@app.route("/carrito/vaciar", methods=["POST"])
def vaciar_carrito():
    session.pop("carrito", None)
    return redirect("/?msg=Carrito+vaciado.")


@app.route("/registro", methods=["GET", "POST"])
def registro():
    err = request.args.get("err", "")
    enlace_confirmacion = None

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        apellido = request.form.get("apellido", "").strip()
        pais = request.form.get("pais", "").strip()
        edad = int(request.form.get("edad", "0") or 0)
        email = request.form.get("email", "").strip().lower()

        if not nombre or not apellido or not pais or not email:
            err = "Completa todos los campos obligatorios."
        elif edad < 18:
            err = "Solo se permite el registro a mayores de 18 años."
        else:
            token = uuid.uuid4().hex
            c = db()
            existente = c.execute("SELECT * FROM usuarios WHERE email=?", (email,)).fetchone()
            if existente:
                c.execute(
                    "UPDATE usuarios SET nombre=?, apellido=?, pais=?, edad=?, token=? WHERE email=?",
                    (nombre, apellido, pais, edad, token, email),
                )
                uid = existente["id"]
            else:
                cur = c.cursor()
                cur.execute(
                    "INSERT INTO usuarios (nombre,apellido,pais,edad,email,metodo,confirmado,token) VALUES (?,?,?,?,?,?,0,?)",
                    (nombre, apellido, pais, edad, email, "Formulario", token),
                )
                uid = cur.lastrowid
            c.commit()
            c.close()

            session["uid"] = uid
            enlace_confirmacion = url_for("confirmar_cuenta", token=token, _external=True)

    html = """
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>Registro +18</title>
      <style>
        body{font-family:system-ui;background:#0f172a;color:#f8fafc;padding:16px}
        .card{max-width:460px;margin:auto;background:#1e293b;padding:18px;border-radius:14px}
        label{display:block;font-weight:700;margin-top:10px}
        input{width:100%;padding:9px;border-radius:8px;border:1px solid #475569;background:#0f172a;color:#fff;box-sizing:border-box}
        button{margin-top:14px;width:100%;padding:10px;border:none;border-radius:10px;background:#059669;color:#fff;font-weight:800}
        .err{background:#7f1d1d;color:#fecaca;padding:10px;border-radius:8px;margin-bottom:10px}
        .ok{background:#064e3b;color:#a7f3d0;padding:10px;border-radius:8px;margin-top:12px;word-break:break-all}
        a{color:#38bdf8}
      </style>
    </head>
    <body>
      <div class="card">
        <a href="/">← Volver a la tienda</a>
        <h2>Registro de cliente (+18)</h2>
        {% if err %}<div class="err">{{ err }}</div>{% endif %}
        <form method="POST">
          <label>Nombre *</label>
          <input name="nombre" required>
          <label>Apellido *</label>
          <input name="apellido" required>
          <label>País *</label>
          <input name="pais" required>
          <label>Edad (+18) *</label>
          <input type="number" name="edad" min="1" max="120" required>
          <label>Correo electrónico *</label>
          <input type="email" name="email" required>
          <button type="submit">Registrarme</button>
        </form>

        {% if oauth_configurado %}
          <p style="text-align:center;margin-top:14px"><a href="/auth/google">Continuar con Google</a></p>
        {% endif %}

        {% if enlace_confirmacion %}
          <div class="ok">
            <strong>Enlace de confirmación generado:</strong><br>
            <a href="{{ enlace_confirmacion }}">{{ enlace_confirmacion }}</a>
          </div>
        {% endif %}
      </div>
    </body>
    </html>
    """
    return render_template_string(
        html,
        err=err,
        enlace_confirmacion=enlace_confirmacion,
        oauth_configurado=OAUTH_CONFIGURADO,
    )


@app.route("/confirmar/<token>")
def confirmar_cuenta(token):
    c = db()
    r = c.execute("SELECT * FROM usuarios WHERE token=?", (token,)).fetchone()
    if not r:
        c.close()
        return redirect("/registro?err=Token+no+valido.")
    c.execute("UPDATE usuarios SET confirmado=1 WHERE id=?", (r["id"],))
    c.commit()
    c.close()
    session["uid"] = r["id"]
    return redirect("/?msg=Cuenta+confirmada.")


@app.route("/salir")
def salir():
    session.pop("uid", None)
    return redirect("/?msg=Sesion+cerrada.")


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST" and request.form.get("clave") == ADMIN_CLAVE:
        session["admin"] = True

    if not session.get("admin"):
        return render_template_string("""
        <!doctype html><html><body style="font-family:sans-serif;background:#0f172a;color:#fff;padding:20px">
          <form method="POST" style="max-width:340px;margin:auto;background:#1e293b;padding:18px;border-radius:12px">
            <h3>Acceso Admin</h3>
            <input type="password" name="clave" placeholder="Clave de admin" required style="width:100%;padding:8px;margin-bottom:10px">
            <button type="submit" style="width:100%;padding:10px;background:#059669;color:#fff;border:0;border-radius:8px">Entrar</button>
          </form>
        </body></html>
        """)

    if request.method == "POST":
        accion = request.form.get("accion")
        c = db()
        if accion == "agregar_producto":
            nombre = request.form.get("nombre", "").strip()
            precio = float(request.form.get("precio", "0") or 0)
            desc = request.form.get("descripcion", "").strip()
            if nombre and precio > 0:
                c.execute("INSERT INTO productos (nombre, precio, descripcion) VALUES (?, ?, ?)", (nombre, precio, desc))
        elif accion == "borrar_producto":
            pid = int(request.form.get("pid", "0") or 0)
            c.execute("DELETE FROM productos WHERE id=?", (pid,))
        elif accion == "borrar_usuario":
            uid = int(request.form.get("uid", "0") or 0)
            c.execute("DELETE FROM usuarios WHERE id=?", (uid,))
        c.commit()
        c.close()
        return redirect("/admin")

    c = db()
    usuarios = c.execute("SELECT * FROM usuarios ORDER BY id DESC").fetchall()
    productos = c.execute("SELECT * FROM productos ORDER BY id DESC").fetchall()
    c.close()

    return render_template_string("""
    <!doctype html><html><body style="font-family:sans-serif;background:#0f172a;color:#fff;padding:16px">
      <div style="max-width:760px;margin:auto">
        <a href="/" style="color:#38bdf8">← Volver a la tienda</a>
        <h2>Panel de Administración</h2>

        <h3>Agregar producto</h3>
        <form method="POST" style="background:#1e293b;padding:12px;border-radius:10px;margin-bottom:16px">
          <input type="hidden" name="accion" value="agregar_producto">
          <input name="nombre" placeholder="Nombre del producto" required style="padding:8px;margin:4px 0;width:100%">
          <input type="number" step="0.01" name="precio" placeholder="Precio" required style="padding:8px;margin:4px 0;width:100%">
          <input name="descripcion" placeholder="Descripción" style="padding:8px;margin:4px 0;width:100%">
          <button type="submit" style="padding:8px 14px;background:#059669;color:#fff;border:0;border-radius:8px;margin-top:6px">Guardar producto</button>
        </form>

        <h3>Productos ({{ productos|length }})</h3>
        {% for p in productos %}
          <div style="background:#1e293b;padding:10px;border-radius:8px;margin-bottom:6px;display:flex;justify-content:space-between">
            <span>{{ p["nombre"] }} — ${{ "%.2f"|format(p["precio"]) }}</span>
            <form method="POST" style="display:inline">
              <input type="hidden" name="accion" value="borrar_producto">
              <input type="hidden" name="pid" value="{{ p['id'] }}">
              <button type="submit" style="background:#dc2626;color:#fff;border:0;border-radius:6px;padding:4px 8px">Eliminar</button>
            </form>
          </div>
        {% endfor %}

        <h3>Usuarios registrados ({{ usuarios|length }})</h3>
        {% for u in usuarios %}
          <div style="background:#1e293b;padding:10px;border-radius:8px;margin-bottom:6px;display:flex;justify-content:space-between">
            <span>{{ u["nombre"] }} {{ u["apellido"] }} ({{ u["email"] }}, {{ u["edad"] }} años, {{ u["pais"] }})</span>
            <form method="POST" style="display:inline">
              <input type="hidden" name="accion" value="borrar_usuario">
              <input type="hidden" name="uid" value="{{ u['id'] }}">
              <button type="submit" style="background:#dc2626;color:#fff;border:0;border-radius:6px;padding:4px 8px">Quitar</button>
            </form>
          </div>
        {% endfor %}
      </div>
    </body></html>
    """, usuarios=usuarios, productos=productos)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
