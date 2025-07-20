from flask import *
from . import admin_bp
import base64
import psycopg2
from werkzeug.utils import secure_filename
import os

def get_db_connection():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    return conn
# Decorador para restringir acceso solo a admin
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('rol') != 'admin':
            flash('Acceso restringido al administrador')
            return redirect(url_for('inicio'))
        return f(*args, **kwargs)
    return decorated

@admin_bp.route('/admin')
@admin_required
def dashboard():
    return render_template('admin/dashboard.html', titulo='Panel de Administración')

@admin_bp.route('/admin/usuarios/vista')
def vista_usuarios():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT u.id, u.usuario, u.email, r.nombre AS rol,
               encode(p.imagen, 'base64') AS foto
        FROM users u
        LEFT JOIN roles r ON u.rol_id = r.id
        LEFT JOIN perfil p ON u.id = p.user_id
    """)

    usuarios = []
    for row in cur.fetchall():
        usuarios.append({
            'id': row[0],
            'usuario': row[1],
            'email': row[2],
            'rol': row[3],
            'foto': row[4]
        })

    cur.close()
    conn.close()
    return render_template('admin/usuarios.html', usuarios=usuarios)

@admin_bp.route('/admin/peliculas')
@admin_required
def admin_peliculas():
    # Aquí iría la lógica para obtener las películas
    peliculas = []  # Temporal
    return render_template('admin/peliculas.html', peliculas=peliculas)

@admin_bp.route('/admin/usuarios/eliminar/<int:user_id>', methods=['POST'])
def eliminar_usuario(user_id):
    conn = get_db_connection()
    cur = conn.cursor()

    # Borra la foto de perfil
    cur.execute("DELETE FROM perfil WHERE user_id = %s", (user_id,))

    # Borra el usuario
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()

    cur.close()
    conn.close()

    return '', 204  # No Content: ideal para fetch()
@admin_bp.route('/admin/peliculas/vista', methods=['GET'])
def vista_peliculas():
    conn = get_db_connection()
    cur = conn.cursor()

    buscar = request.args.get('buscar')
    
    if buscar:
        query = """
            SELECT p.id, p.titulo, p.anio_publicacion, d.descripcion 
            FROM peliculas p 
            LEFT JOIN descripciones d ON p.id = d.pelicula_id
            WHERE LOWER(p.titulo) LIKE %s
        """
        cur.execute(query, (f"%{buscar.lower()}%",))
    else:
        cur.execute("""
            SELECT p.id, p.titulo, p.anio_publicacion, d.descripcion 
            FROM peliculas p 
            LEFT JOIN descripciones d ON p.id = d.pelicula_id
        """)

    peliculas = cur.fetchall()

    resultados = []
    for p in peliculas:
        cur.execute("SELECT descripcion FROM etiquetas WHERE pelicula_id = %s", (p[0],))
        etiquetas = [e[0] for e in cur.fetchall()]
        resultados.append({
            'id': p[0],
            'titulo': p[1],
            'anio_publicacion': p[2],
            'descripcion': p[3],
            'etiquetas': etiquetas
        })

    editar = None
    if request.args.get("editar"):
        id_peli = request.args.get("editar")
        cur.execute("SELECT id, titulo, anio_publicacion FROM peliculas WHERE id = %s", (id_peli,))
        peli = cur.fetchone()

        cur.execute("SELECT descripcion FROM descripciones WHERE pelicula_id = %s", (id_peli,))
        desc = cur.fetchone()

        cur.execute("SELECT descripcion FROM etiquetas WHERE pelicula_id = %s", (id_peli,))
        etiquetas = [e[0] for e in cur.fetchall()]

        cur.execute("SELECT imagen FROM portadas WHERE pelicula_id = %s", (id_peli,))
        portada = cur.fetchone()

        cur.execute("SELECT imagen FROM cards WHERE pelicula_id = %s", (id_peli,))
        card = cur.fetchone()

        editar = {
            'id': peli[0],
            'titulo': peli[1],
            'anio_publicacion': peli[2],
            'descripcion': desc[0] if desc else '',
            'etiquetas': ', '.join(etiquetas),
            'portada': base64.b64encode(portada[0]).decode('utf-8') if portada else None,
            'card': base64.b64encode(card[0]).decode('utf-8') if card else None
        }

    cur.close()
    conn.close()
    return render_template('admin/peliculas.html', peliculas=resultados, editar_pelicula=editar)

@admin_bp.route('/admin/peliculas/añadir', methods=['POST'])
def añadir_pelicula():
    titulo = request.form['titulo']
    año = request.form['año']
    descripcion = request.form['descripcion']
    etiquetas = request.form['etiquetas'].split(',')
    portada = request.files['portada']
    card = request.files['card']

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO peliculas (titulo, anio_publicacion) VALUES (%s, %s) RETURNING id", (titulo, año))
    pelicula_id = cur.fetchone()[0]

    if descripcion:
        cur.execute("INSERT INTO descripciones (pelicula_id, descripcion) VALUES (%s, %s)", (pelicula_id, descripcion))

    for e in etiquetas:
        e = e.strip()
        if e:
            cur.execute("INSERT INTO etiquetas (pelicula_id, descripcion) VALUES (%s, %s)", (pelicula_id, e))

    if portada:
        cur.execute("INSERT INTO portadas (pelicula_id, imagen_portada) VALUES (%s, %s)", (pelicula_id, portada.read()))

    if card:
        cur.execute("INSERT INTO cards (pelicula_id, imagen_card) VALUES (%s, %s)", (pelicula_id, card.read()))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for('admin.vista_peliculas'))

@admin_bp.route('/admin/peliculas/eliminar/<int:id>',  methods=['POST'])
def eliminar_pelicula(id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM peliculas WHERE id = %s", (id,))
    cur.execute("DELETE FROM descripciones WHERE pelicula_id = %s", (id,))
    cur.execute("DELETE FROM etiquetas WHERE pelicula_id = %s", (id,))
    cur.execute("DELETE FROM portadas WHERE pelicula_id = %s", (id,))
    cur.execute("DELETE FROM cards WHERE pelicula_id = %s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('admin.vista_peliculas'))

@admin_bp.route('/admin/peliculas/editar/<int:id>', methods=['POST'])
def editar_pelicula(id):
    titulo = request.form['titulo']
    año = request.form['año']
    descripcion = request.form['descripcion']
    etiquetas = request.form['etiquetas'].split(',')
    portada = request.files['portada']
    card = request.files['card']

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("UPDATE peliculas SET titulo = %s, anio_publicacion = %s WHERE id = %s", (titulo, año, id))
    cur.execute("DELETE FROM descripciones WHERE pelicula_id = %s", (id,))
    if descripcion:
        cur.execute("INSERT INTO descripciones (pelicula_id, descripcion) VALUES (%s, %s)", (id, descripcion))

    cur.execute("DELETE FROM etiquetas WHERE pelicula_id = %s", (id,))
    for e in etiquetas:
        e = e.strip()
        if e:
            cur.execute("INSERT INTO etiquetas (pelicula_id, descripcion) VALUES (%s, %s)", (id, e))

    if portada:
        cur.execute("DELETE FROM portadas WHERE pelicula_id = %s", (id,))
        cur.execute("INSERT INTO portadas (pelicula_id, imagen_portada) VALUES (%s, %s)", (id, portada.read()))

    if card:
        cur.execute("DELETE FROM cards WHERE pelicula_id = %s", (id,))
        cur.execute("INSERT INTO cards (pelicula_id, imagen_cards) VALUES (%s, %s)", (id, card.read()))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for('admin.vista_peliculas'))

@admin_bp.route('/admin/peliculas/video', methods=['POST'])
def inserta_video_pelicula():
    pelicula_id = request.form.get('pelicula_id')
    url_video = request.form.get('url_video')  # ✅ ahora se espera una URL en lugar de un archivo

    if not url_video or not pelicula_id:
        return "Debe ingresar una URL de video válida y asignarla a una película", 400

    # Inserta la URL en la base de datos
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("INSERT INTO videos (url_video, pelicula_id) VALUES (%s, %s)", (url_video, pelicula_id))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for('admin.vista_peliculas'))

@admin_bp.route('/admin/estadisticas')
def estadisticas():
    conn = get_db_connection()
    cur = conn.cursor()

    # 🔵 TOP 5 con más ME GUSTA (desde reacciones donde me_gusta = TRUE)
    cur.execute("""
        SELECT p.titulo, COUNT(r.id) AS cantidad
        FROM reacciones r
        JOIN peliculas p ON r.pelicula_id = p.id
        WHERE r.me_gusta = TRUE
        GROUP BY p.titulo
        ORDER BY cantidad DESC
        LIMIT 5
    """)
    top_megusta = [{'titulo': row[0], 'cantidad': row[1]} for row in cur.fetchall()]

    # ❤️ TOP 5 FAVORITOS (desde tabla favoritos)
    cur.execute("""
        SELECT p.titulo, COUNT(f.id) AS cantidad
        FROM favoritos f
        JOIN peliculas p ON f.pelicula_id = p.id
        GROUP BY p.titulo
        ORDER BY cantidad DESC
        LIMIT 5
    """)
    top_favoritos = [{'titulo': row[0], 'cantidad': row[1]} for row in cur.fetchall()]

    # ⭐ TOP 5 VALORACIONES por promedio
    cur.execute("""
        SELECT p.titulo, ROUND(AVG(v.valoracion), 2) AS promedio
        FROM valoraciones v
        JOIN peliculas p ON v.pelicula_id = p.id
        GROUP BY p.titulo
        HAVING COUNT(v.id) >= 3 -- opcional: solo películas con al menos 3 valoraciones
        ORDER BY promedio DESC
        LIMIT 5
    """)
    top_valoraciones = [{'titulo': row[0], 'promedio': row[1]} for row in cur.fetchall()]

    # 👁️ TOP 5 VISTAS (conteo en la tabla vistas)
    cur.execute("""
        SELECT p.titulo, COUNT(v.id) AS vistas
        FROM vistas v
        JOIN peliculas p ON v.pelicula_id = p.id
        GROUP BY p.titulo
        ORDER BY vistas DESC
        LIMIT 5
    """)
    top_vistas = [{'titulo': row[0], 'vistas': row[1]} for row in cur.fetchall()]

    cur.close()
    conn.close()

    return render_template(
        'admin/estadisticas.html',
        top_megusta=top_megusta,
        top_favoritos=top_favoritos,
        top_valoraciones=top_valoraciones,
        top_vistas=top_vistas,
        top_megusta_json=json.dumps(top_megusta),
        top_valoraciones_json=json.dumps(top_valoraciones),
        top_vistas_json=json.dumps(top_vistas)
    )
@admin_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('inicio'))
