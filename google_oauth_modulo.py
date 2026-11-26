import os
import sqlite3
import uuid
from authlib.integrations.flask_client import OAuth
from flask import Blueprint, redirect, render_template_string, request, session, url_for

google_bp = Blueprint("google_bp", __name__)
oauth = OAuth()

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
OAUTH_CONFIGURADO = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def init_google_oauth(app):
    if OAUTH_CONFIGURADO:
        oauth.init_app(app)
        oauth.register(
            name="google",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )


def _db(archivo_db):
    c = sqlite3.connect(archivo_db)
    c.row_factory = sqlite3.Row
    return c


@google_bp.route("/auth/google")
def auth_google():
    if not OAUTH_CONFIGURADO:
        return redirect("/registro?err=Configura+GOOGLE_CLIENT_ID+y+GOOGLE_CLIENT_SECRET.")
    return oauth.google.authorize_redirect(
        url_for("google_bp.auth_google_callback", _external=True)
    )


@google_bp.route("/auth/google/callback")
def auth_google_callback():
    if not OAUTH_CONFIGURADO:
        return redirect("/registro?err=Google+OAuth+no+configurado.")
    tok = oauth.google.authorize_access_token()
    info = tok.get("userinfo") or {}
    email = (info.get("email") or "").strip().lower()
    nom = (info.get("given_name") or info.get("name") or "Usuario").strip()
    ape = (info.get("family_name") or "Google").strip()
    if not email:
        return redirect("/registro?err=Sin+correo+de+Google.")

    adb = os.environ.get("ARCHIVO_DB", "tienda.db")
    c = _db(adb)
    r = c.execute("SELECT * FROM usuarios WHERE email=?", (email,)).fetchone()
    if r:
        uid, pais, edad = r["id"], r["pais"], r["edad"]
    else:
        cur = c.cursor()
        cur.execute(
            "INSERT INTO usuarios (nombre,apellido,pais,edad,email,metodo,confirmado,token) VALUES (?,?,?,?,?,?,0,?)",
            (nom, ape, "", 0, email, "Google OAuth", uuid.uuid4().hex),
        )
        c.commit()
        uid, pais, edad = cur.lastrowid, "", 0
    c.close()

    session["uid"] = uid
    if not pais or int(edad or 0) < 18:
        return redirect(url_for("google_bp.completar_perfil_google"))
    return redirect("/?msg=Sesion+con+Google+iniciada.")


@google_bp.route("/auth/google/completar", methods=["GET", "POST"])
def completar_perfil_google():
    uid = session.get("uid")
    if not uid:
        return redirect("/registro")

    adb = os.environ.get("ARCHIVO_DB", "tienda.db")
    c = _db(adb)
    r = c.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
    c.close()
    if not r:
        return redirect("/registro")

    err = None
    if request.method == "POST":
        pais = request.form.get("pais", "").strip()
        edad = int(request.form.get("edad", "0") or 0)
        if edad < 18:
            err = "No se permite menor de edad (mínimo 18 años)."
        elif not pais:
            err = "Indica tu país."
        else:
            c = _db(adb)
            c.execute(
                "UPDATE usuarios SET pais=?, edad=?, confirmado=1 WHERE id=?",
                (pais, edad, uid),
            )
            c.commit()
            c.close()
            return redirect("/?msg=Perfil+de+Google+confirmado.")

    tpl = """
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>+18</title>
      <style>
        body{font-family:system-ui;background:#f1f5f9;padding:16px}
        .card{max-width:460px;margin:auto;background:#fff;padding:18px;border-radius:14px}
        .err{background:#fef2f2;color:#991b1b;padding:10px;border-radius:10px;margin-bottom:10px}
        label{display:block;font-weight:700;margin-top:10px}
        input{width:100%;padding:9px;border-radius:8px;border:1px solid #cbd5e1;box-sizing:border-box}
        button{margin-top:14px;width:100%;padding:10px;border:none;border-radius:10px;background:#059669;color:#fff;font-weight:800}
      </style>
    </head>
    <body>
      <div class="card">
        {% if err %}<div class="err">{{ err }}</div>{% endif %}
        <h2>Completa perfil (+18)</h2>
        <p>{{ email }}</p>
        <form method="POST">
          <label>País *</label>
          <input name="pais" value="{{ pais }}" required>
          <label>Edad (+18) *</label>
          <input type="number" name="edad" min="1" max="120" value="{{ edad or '' }}" required>
          <button type="submit">Confirmar e ir a la tienda</button>
        </form>
      </div>
    </body>
    </html>
    """
    return render_template_string(tpl, err=err, email=r["email"], pais=r["pais"], edad=r["edad"])
