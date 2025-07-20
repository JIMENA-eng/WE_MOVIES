from flask import *
import psycopg2
import base64
from werkzeug.security import *
from io import BytesIO
from PIL import Image
from admin import admin_bp
import pandas as pd
import numpy as np
import base64
from random import choices

app = Flask(__name__)
app.secret_key = 'zimmyflix_2025_clave_super_secreta'
app.register_blueprint(admin_bp)


# Configura la conexión a la base de datos 'movil'
def get_db_connection():
    conn = psycopg2.connect(
        dbname='movil',
        user='postgres',
        password='jimena123456',  # Usa UTF-8, sin tildes ni caracteres especiales si es posible
        host='localhost',
        port='5432'
    )
    conn.set_client_encoding('UTF8')
    return conn

def obtener_peliculas_populares():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            p.id,
            p.titulo,
            d.descripcion,
            c.imagen_card,
            po.imagen_portada,
            ARRAY(
                SELECT e.descripcion
                FROM etiquetas e
                WHERE e.pelicula_id = p.id
            ) AS etiquetas
        FROM peliculas p
        LEFT JOIN descripciones d ON d.pelicula_id = p.id
        LEFT JOIN cards c ON c.pelicula_id = p.id
        LEFT JOIN portadas po ON po.pelicula_id = p.id
        ORDER BY p.id DESC LIMIT 50;
    """)
    
    peliculas = []
    for id, titulo, descripcion, card_bytes, portada_bytes, etiquetas in cur.fetchall():
        card_img = base64.b64encode(card_bytes).decode('utf-8') if card_bytes else None
        portada_img = base64.b64encode(portada_bytes).decode('utf-8') if portada_bytes else None
        peliculas.append({
            'id': id,
            'titulo': titulo,
            'descripcion': descripcion or '',
            'card': card_img,
            'portada': portada_img,
            'etiquetas': etiquetas or []
        })
    cur.close()
    conn.close()
    return peliculas

@app.route('/')
def inicio():
    conn = get_db_connection()
    cur = conn.cursor()

    # Obtener carrusel y películas destacadas
    peliculas = obtener_peliculas_populares()
    carrusel = obtener_datos_carrusel()

    # Obtener recomendaciones personalizadas si hay sesión activa
    recomendaciones = []
    otras_recomendaciones = []

    if 'user_id' in session:
        try:
            resultado = generar_recomendaciones_bootstrap(session['user_id'], conn)
            if resultado and isinstance(resultado, tuple) and len(resultado) == 2:
                recomendaciones, otras_recomendaciones = resultado
            else:
                recomendaciones, otras_recomendaciones = [], []
        except Exception as e:
            print(f"⚠️ Error al generar recomendaciones bootstrap: {e}")
            recomendaciones, otras_recomendaciones = [], []
    else:
        recomendaciones = []
        otras_recomendaciones = []

    # Obtener top 10 desde tabla 'rankings' y 'movies'
    cur.execute("""
        SELECT 
            m.id, 
            m.title, 
            ROUND(AVG(r.rating), 2) AS promedio,
            COUNT(r.rating) AS cantidad
        FROM movies m
        JOIN rankings r ON m.id = r.movie_id
        GROUP BY m.id, m.title
        HAVING COUNT(r.rating) > 10
        ORDER BY promedio DESC, cantidad DESC
        LIMIT 10;
    """)
    top_raw = cur.fetchall()

    top_peliculas = [{
        'id': r[0],
        'titulo': r[1],
        'promedio': r[2],
        'cantidad': r[3]
    } for r in top_raw]

    cur.close()
    conn.close()

    return render_template('base.html',
                           peliculas=peliculas,
                           carrusel=carrusel,
                           recomendaciones=recomendaciones,
                           otras_recomendaciones=otras_recomendaciones,
                           top_peliculas=top_peliculas)

    
def obtener_datos_carrusel():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            p.id,
            p.titulo,
            d.descripcion,
            po.imagen_portada,
            COALESCE((
                SELECT COUNT(*) 
                FROM reacciones r 
                WHERE r.pelicula_id = p.id AND r.me_gusta = true
            ), 0) AS total_likes,
            COALESCE((
                SELECT COUNT(*) 
                FROM vistas v 
                WHERE v.pelicula_id = p.id
            ), 0) AS total_vistas,
            COALESCE((
                SELECT ROUND(AVG(valoracion), 1)
                FROM valoraciones v
                WHERE v.pelicula_id = p.id
            ), 0) AS promedio_valoracion
        FROM peliculas p
        LEFT JOIN descripciones d ON d.pelicula_id = p.id
        LEFT JOIN portadas po ON po.pelicula_id = p.id
        ORDER BY p.id DESC LIMIT 5;
    """)
    
    resultados = []
    for fila in cur.fetchall():
        id, titulo, descripcion, portada_bytes, likes, vistas, promedio = fila
        imagen_base64 = base64.b64encode(portada_bytes).decode('utf-8') if portada_bytes else None
        resultados.append({
            'id': id,
            'titulo': titulo,
            'descripcion': descripcion,
            'imagen': imagen_base64,
            'likes': likes,
            'vistas': vistas,
            'promedio': promedio
        })
    
    cur.close()
    conn.close()
    return resultados

@app.route('/pelicula/<int:pelicula_id>')
def detalle_pelicula(pelicula_id):
    user_id = session.get('user_id')  # Necesario para recomendaciones

    conn = get_db_connection()
    cur = conn.cursor()

    # Datos principales de la película
    cur.execute("""
        SELECT 
            p.titulo,
            d.descripcion,
            po.imagen_portada,
            v.url_video,
            ARRAY(SELECT e.descripcion FROM etiquetas e WHERE e.pelicula_id = p.id),
            COALESCE((SELECT COUNT(*) FROM reacciones r WHERE r.pelicula_id = p.id AND r.me_gusta = TRUE), 0),
            COALESCE((SELECT COUNT(*) FROM vistas vs WHERE vs.pelicula_id = p.id), 0),
            COALESCE((SELECT ROUND(AVG(valoracion), 1) FROM valoraciones val WHERE val.pelicula_id = p.id), 0)
        FROM peliculas p
        LEFT JOIN descripciones d ON d.pelicula_id = p.id
        LEFT JOIN portadas po ON po.pelicula_id = p.id
        LEFT JOIN videos v ON v.pelicula_id = p.id
        WHERE p.id = %s
    """, (pelicula_id,))
    row = cur.fetchone()

    if not row:
        return "Película no encontrada", 404

    titulo, descripcion, portada, url_video, etiquetas, likes, vistas, promedio = row
    portada_b64 = base64.b64encode(portada).decode('utf-8') if portada else None

    
    # --- Recomendaciones basadas en "me gusta" del usuario ---
    recomendaciones = []
    if user_id:
        recomendaciones = generar_recomendaciones_bootstrap(user_id, conn)
    # --- Similitud por etiquetas ---
    similares = []
    if etiquetas:
        cur.execute("""
            SELECT * FROM (
            SELECT DISTINCT p.id, p.titulo, p.anio_publicacion, c.imagen_card
            FROM etiquetas e
            JOIN peliculas p ON e.pelicula_id = p.id
            LEFT JOIN cards c ON p.id = c.pelicula_id
            WHERE e.descripcion = ANY(%s) AND p.id != %s
        ) AS sub
        ORDER BY RANDOM()
        LIMIT 6
        """, (etiquetas, pelicula_id))
        similares = [(s[0], s[1], s[2], base64.b64encode(s[3]).decode('utf-8')) for s in cur.fetchall() if s[3]]

    # --- Capítulos (múltiples videos asociados a la película) ---
    cur.execute("""
        SELECT id, url_video
        FROM videos
        WHERE pelicula_id = %s
        ORDER BY id
    """, (pelicula_id,))
    capitulos = cur.fetchall()

    cur.execute("SELECT url_video FROM videos WHERE pelicula_id = %s ORDER BY id", (pelicula_id,))
    capitulos_data = cur.fetchall()

    capitulos = []
    for cap in capitulos_data:
        capitulos.append({
            'url': cap[0],
            'portada': portada_b64  # usa la misma portada por ahora
        })
   
    cur.execute("INSERT INTO vistas (pelicula_id) VALUES (%s)", (pelicula_id,))
    conn.commit()

    cur.execute("""
        SELECT u.usuario, c.descripcion
        FROM comentarios c
        JOIN users u ON c.user_id = u.id
        WHERE c.pelicula_id = %s
        ORDER BY c.id DESC
    """, (pelicula_id,))
    comentarios = cur.fetchall()

    otras_recomendaciones = []
    if 'user_id' in session:
        otras_recomendaciones = generar_recomendaciones_bootstrap(session['user_id'], conn)

    cur.close()
    conn.close()

    
        

    return render_template("detalle_pelicula.html",
                           titulo=titulo,
                           descripcion=descripcion,
                           portada=portada_b64,
                           url_video=url_video,
                           etiquetas=etiquetas,
                           likes=likes,
                           vistas=vistas,
                           promedio=promedio,
                           pelicula_id=pelicula_id,
                           recomendaciones=recomendaciones,
                           similares=similares,
                           capitulos=capitulos,
                           comentarios=comentarios,
                           otras_recomendaciones=otras_recomendaciones)


@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT u.id, u.usuario, u.password_hash, r.nombre AS rol
        FROM users u
        LEFT JOIN roles r ON u.rol_id = r.id
        WHERE u.email = %s
    """, (email,))
    
    user = cur.fetchone()

    if user and check_password_hash(user[2], password):
        session['user_id'] = user[0]
        session['usuario'] = user[1]
        session['rol'] = user[3]

        cur.close()
        conn.close()

        if session['rol'] == 'admin':
            return redirect(url_for('admin.dashboard'))
        else:
            return redirect(url_for('inicio'))

    cur.close()
    conn.close()
    return redirect(url_for('inicio', error='Credenciales inválidas'))

@app.route('/login_ajax', methods=['POST'])
def login_ajax():
    try:
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            return jsonify({
                'success': False, 
                'message': 'Email y contraseña son requeridos'
            }), 400

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT u.id, u.usuario, u.password_hash, r.nombre AS rol
            FROM users u
            LEFT JOIN roles r ON u.rol_id = r.id
            WHERE u.email = %s
        """, (email,))
        
        user = cur.fetchone()

        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['usuario'] = user[1]
            session['rol'] = user[3]

            cur.close()
            conn.close()

            return jsonify({
                'success': True, 
                'message': 'Login exitoso',
                'user': user[1],
                'rol': user[3]
            })
        else:
            cur.close()
            conn.close()
            return jsonify({
                'success': False, 
                'message': 'Credenciales inválidas'
            }), 401
            
    except Exception as e:
        print(f"Error en login_ajax: {e}")  # Debug en consola del servidor
        return jsonify({
            'success': False, 
            'message': 'Error interno del servidor'
        }), 500

# ✅ PASO 2: Crea un context processor para obtener la imagen

@app.context_processor
def inject_foto():
    def get_foto(user_id):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT imagen FROM perfil WHERE user_id = %s", (user_id,))
        foto = cur.fetchone()
        cur.close()
        conn.close()
        return base64.b64encode(foto[0]).decode('utf-8') if foto else None
    return dict(get_foto=get_foto)
# ---------------------------
# REGISTRO DE USUARIO
# ---------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            usuario = request.form['usuario']
            email = request.form['email']
            password = request.form['password']
            fecha_nacimiento = request.form['fecha_nacimiento']
            pais = request.form['pais']
            imagen_data = request.form['imagen_crop']

            if not imagen_data:
                return render_template("register.html", error="Debes seleccionar una imagen de perfil.")

            password_hash = generate_password_hash(password)

            conn = get_db_connection()
            cur = conn.cursor()

            # Verificar que el email no esté duplicado
            cur.execute("SELECT 1 FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                cur.close()
                conn.close()
                return render_template("register.html", error="Este correo ya está registrado.")

            # Registrar usuario
            cur.execute("""
                INSERT INTO users (usuario, email, password_hash, fecha_nacimiento, pais, rol_id)
                VALUES (%s, %s, %s, %s, %s, 2) RETURNING id
            """, (usuario, email, password_hash, fecha_nacimiento, pais))
            user_id = cur.fetchone()[0]

            # Guardar imagen de perfil
            if imagen_data:
                header, encoded = imagen_data.split(',', 1)
                binary_img = base64.b64decode(encoded)
                cur.execute("INSERT INTO perfil (imagen, user_id) VALUES (%s, %s)", (binary_img, user_id))

            conn.commit()
            cur.close()
            conn.close()

            return redirect(url_for('inicio'))

        except Exception as e:
            print("Error en registro:", e)
            return render_template("register.html", error="Ocurrió un error al registrar. Intenta de nuevo.")

    return render_template("register.html")
# ---------------------------
# CIERRE DE SESIÓN
# ---------------------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('inicio'))


@app.route('/me_gusta', methods=['POST'])
def me_gusta():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    pelicula_id = request.form['pelicula_id']

    conn = get_db_connection()
    cur = conn.cursor()

    # Verifica si ya existe reacción
    cur.execute("SELECT id FROM reacciones WHERE user_id = %s AND pelicula_id = %s", (user_id, pelicula_id))
    if cur.fetchone():
        cur.execute("UPDATE reacciones SET me_gusta = TRUE WHERE user_id = %s AND pelicula_id = %s", (user_id, pelicula_id))
    else:
        cur.execute("INSERT INTO reacciones (user_id, pelicula_id, me_gusta) VALUES (%s, %s, TRUE)", (user_id, pelicula_id))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for('detalle_pelicula', pelicula_id=pelicula_id))


@app.route('/agregar_lista', methods=['POST'])
def agregar_lista():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    pelicula_id = request.form['pelicula_id']

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT id FROM listas WHERE user_id = %s AND pelicula_id = %s", (user_id, pelicula_id))
    if not cur.fetchone():
        cur.execute("INSERT INTO listas (user_id, pelicula_id) VALUES (%s, %s)", (user_id, pelicula_id))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for('detalle_pelicula', pelicula_id=pelicula_id))


@app.route('/agregar_favorito', methods=['POST'])
def agregar_favorito():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    pelicula_id = request.form['pelicula_id']

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT id FROM favoritos WHERE user_id = %s AND pelicula_id = %s", (user_id, pelicula_id))
    if not cur.fetchone():
        cur.execute("INSERT INTO favoritos (user_id, pelicula_id) VALUES (%s, %s)", (user_id, pelicula_id))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for('detalle_pelicula', pelicula_id=pelicula_id))

@app.route('/pelicula/<int:pelicula_id>/comentario', methods=['POST'])
def agregar_comentario(pelicula_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))  # Redirige si no ha iniciado sesión

    comentario = request.form.get('comentario')
    valoracion = int(request.form.get('valoracion'))
    user_id = session['user_id']

    if not comentario:
        return "Comentario requerido", 400

    conn = get_db_connection()
    cur = conn.cursor()

    # Insertar comentario
    cur.execute("INSERT INTO comentarios (descripcion, user_id, pelicula_id) VALUES (%s, %s, %s)",
                (comentario, user_id, pelicula_id))

    # Insertar o actualizar la valoración
    cur.execute("SELECT id FROM valoraciones WHERE user_id = %s AND pelicula_id = %s", (user_id, pelicula_id))
    if cur.fetchone():
        cur.execute("UPDATE valoraciones SET valoracion = %s, fecha_valoracion = CURRENT_DATE WHERE user_id = %s AND pelicula_id = %s",
                    (valoracion, user_id, pelicula_id))
    else:
        cur.execute("INSERT INTO valoraciones (valoracion, user_id, pelicula_id) VALUES (%s, %s, %s)",
                    (valoracion, user_id, pelicula_id))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for('detalle_pelicula', pelicula_id=pelicula_id))

@app.route('/buscar')
def buscar():
    consulta = request.args.get('q', '').strip().lower()

    if not consulta:
        return redirect(url_for('inicio'))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT p.id, p.titulo, p.anio_publicacion, c.imagen
        FROM peliculas p
        LEFT JOIN descripciones d ON p.id = d.pelicula_id
        LEFT JOIN etiquetas e ON p.id = e.pelicula_id
        LEFT JOIN cards c ON p.id = c.pelicula_id
        WHERE LOWER(p.titulo) LIKE %s
           OR LOWER(d.descripcion) LIKE %s
           OR LOWER(e.descripcion) LIKE %s
    """, (f'%{consulta}%', f'%{consulta}%', f'%{consulta}%'))

    resultados = []
    for row in cur.fetchall():
        card_b64 = base64.b64encode(row[3]).decode('utf-8') if row[3] else None
        resultados.append({
            'id': row[0],
            'titulo': row[1],
            'anio': row[2],
            'card': card_b64
        })

    cur.close()
    conn.close()

    return render_template("resultados_busqueda.html", consulta=consulta, resultados=resultados)

@app.route('/autocompletar')
def autocompletar():
    termino = request.args.get('q', '').strip().lower()
    if not termino:
        return jsonify([])

    conn = get_db_connection()
    cur = conn.cursor()

    # Buscar en tabla 'peliculas'
    cur.execute("""
        SELECT id, titulo
        FROM peliculas
        WHERE LOWER(titulo) LIKE %s
        LIMIT 10
    """, (f"%{termino}%",))
    resultados_peliculas = [{"id": r[0], "titulo": r[1], "fuente": "peliculas"} for r in cur.fetchall()]

    # Buscar en tabla 'movies'
    cur.execute("""
        SELECT id, title
        FROM movies
        WHERE LOWER(title) LIKE %s
        LIMIT 10
    """, (f"%{termino}%",))
    resultados_movies = [{"id": r[0], "titulo": r[1], "fuente": "movies"} for r in cur.fetchall()]

    # Buscar por etiquetas (desde tabla `etiquetas` con columna `descripcion`)
    cur.execute("""
        SELECT DISTINCT p.id, p.titulo
        FROM etiquetas e
        JOIN peliculas p ON e.pelicula_id = p.id
        WHERE LOWER(e.descripcion) LIKE %s
        LIMIT 10
    """, (f"%{termino}%",))
    resultados_etiquetas = [{"id": r[0], "titulo": r[1], "fuente": "etiquetas"} for r in cur.fetchall()]

    cur.close()
    conn.close()

    return jsonify(resultados_peliculas + resultados_movies + resultados_etiquetas)

@app.route('/buscar_titulo')
def buscar_titulo():
    titulo = request.args.get('q', '').strip().lower()
    if not titulo:
        return jsonify({})

    conn = get_db_connection()
    cur = conn.cursor()

    # Buscar en peliculas
    cur.execute("SELECT id FROM peliculas WHERE LOWER(titulo) = %s", (titulo,))
    resultado = cur.fetchone()
    if resultado:
        cur.close()
        conn.close()
        return jsonify({"id": resultado[0], "fuente": "peliculas"})

    # Buscar en movies si no se encontró antes
    cur.execute("SELECT id FROM movies WHERE LOWER(title) = %s", (titulo,))
    resultado = cur.fetchone()
    cur.close()
    conn.close()
    if resultado:
        return jsonify({"id": resultado[0], "fuente": "movies"})

    return jsonify({})

@app.route('/detalle_minibar')
def detalle_minibar():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cur = conn.cursor()

    # Me gusta
    cur.execute("""
        SELECT p.id, p.titulo
        FROM reacciones r
        JOIN peliculas p ON r.pelicula_id = p.id
        WHERE r.user_id = %s AND r.me_gusta = TRUE
    """, (user_id,))
    megusta = cur.fetchall()

    # Favoritos
    cur.execute("""
        SELECT p.id, p.titulo
        FROM favoritos f
        JOIN peliculas p ON f.pelicula_id = p.id
        WHERE f.user_id = %s
    """, (user_id,))
    favoritos = cur.fetchall()

    # Mi lista
    cur.execute("""
        SELECT p.id, p.titulo
        FROM listas l
        JOIN peliculas p ON l.pelicula_id = p.id
        WHERE l.user_id = %s
    """, (user_id,))
    listas = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('bar.html', megusta=megusta, favoritos=favoritos, listas=listas)
@app.route("/top")
def ver_top_peliculas():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            m.id, 
            m.title, 
            ROUND(AVG(r.rating), 2) AS promedio,
            COUNT(r.rating) AS cantidad
        FROM movies m
        JOIN rankings r ON m.id = r.movie_id
        GROUP BY m.id, m.title
        HAVING COUNT(r.rating) > 10
        ORDER BY promedio DESC, cantidad DESC
        
    """)
    otras_recomendaciones = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("top.html", otras_recomendaciones=otras_recomendaciones)

@app.route('/etiquetas')
def listar_etiquetas():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT descripcion FROM etiquetas ORDER BY descripcion")
    etiquetas = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(etiquetas)

@app.route('/filtrar_etiqueta/<nombre>')
def filtrar_etiqueta(nombre):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT p.id, p.titulo, c.imagen_card, d.descripcion
        FROM peliculas p
        LEFT JOIN etiquetas e ON e.pelicula_id = p.id
        LEFT JOIN cards c ON c.pelicula_id = p.id
        LEFT JOIN descripciones d ON d.pelicula_id = p.id
        WHERE LOWER(e.descripcion) = %s
    """, (nombre.lower(),))

    peliculas = []
    for row in cur.fetchall():
        id, titulo, card, descripcion = row
        card_b64 = base64.b64encode(card).decode('utf-8') if card else None
        peliculas.append({
            'id': id,
            'titulo': titulo,
            'card': card_b64,
            'descripcion': descripcion
        })

    cur.close()
    conn.close()

    return render_template("busqueda_filtros.html", etiqueta=nombre, peliculas=peliculas)

def motor_bootstrap_mejorado(n_usuarios=1000, k=10):
    """
    Motor de bootstrap mejorado para recomendaciones generales
    """
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Obtener datos de valoraciones con Bootstrap
        cur.execute("SELECT user_id, pelicula_id, valoracion FROM valoraciones")
        rows = cur.fetchall()
        
        if not rows:
            return []
            
        df = pd.DataFrame(rows, columns=["user_id", "pelicula_id", "valoracion"])

        # Bootstrap: seleccionar usuarios con reemplazo
        usuarios_disponibles = df['user_id'].unique()
        usuarios_muestra = np.random.choice(usuarios_disponibles, size=n_usuarios, replace=True)

        df_bootstrap = df[df['user_id'].isin(usuarios_muestra)]

        # Calcular promedio por película con variabilidad
        media_por_pelicula = df_bootstrap.groupby('pelicula_id')['valoracion'].agg(['mean', 'count'])
        media_filtrada = media_por_pelicula[media_por_pelicula['count'] > 5].sort_values(
            by='mean', ascending=False
        )
        
        # Añadir aleatoriedad en la selección
        candidatos = media_filtrada.head(k*2)  # Más candidatos
        if len(candidatos) >= k:
            indices_aleatorios = np.random.choice(len(candidatos), size=k, replace=False)
            peliculas_seleccionadas = candidatos.iloc[indices_aleatorios]
        else:
            peliculas_seleccionadas = candidatos

        recomendaciones = []
        for pelicula_id, row in peliculas_seleccionadas.iterrows():
            cur.execute("""
                SELECT p.titulo, c.imagen_card 
                FROM peliculas p
                LEFT JOIN cards c ON p.id = c.pelicula_id
                WHERE p.id = %s
            """, (int(pelicula_id),))
            
            resultado = cur.fetchone()
            if resultado:
                titulo, imagen = resultado
                card = base64.b64encode(imagen).decode() if imagen else None
                recomendaciones.append({
                    'id': int(pelicula_id),
                    'titulo': titulo,
                    'promedio': round(row['mean'], 2),
                    'card': card
                })

        return recomendaciones
        
    except Exception as e:
        print(f"❌ Error en motor bootstrap: {e}")
        return []
    
    finally:
        cur.close()
        conn.close()
        
import pandas as pd
import numpy as np
import base64
from io import BytesIO
from random import sample

def generar_recomendaciones_bootstrap(user_id, conn, n_usuarios=1000, k_recomendaciones=6):
    """
    Genera recomendaciones usando Bootstrap sampling para obtener 
    diferentes recomendaciones en cada refresh de la página
    """
    cur = conn.cursor()
    
    try:
        # 1. Obtener datos de valoraciones
        cur.execute("SELECT user_id, pelicula_id, valoracion FROM valoraciones")
        rows = cur.fetchall()
        
        if not rows:
            return [], []
            
        df = pd.DataFrame(rows, columns=['user_id', 'pelicula_id', 'valoracion'])
        
        # 2. Bootstrap: Seleccionar usuarios aleatoriamente con reemplazo
        usuarios_disponibles = df['user_id'].unique()
        if len(usuarios_disponibles) == 0:
            return [], []
            
        # Seleccionar muestra de usuarios (con reemplazo para variabilidad)
        n_sample = min(n_usuarios, len(usuarios_disponibles))
        usuarios_muestra = np.random.choice(usuarios_disponibles, size=n_sample, replace=True)
        
        # 3. Filtrar datos por usuarios seleccionados
        df_bootstrap = df[df['user_id'].isin(usuarios_muestra)]
        
        # 4. Crear matriz usuario-película
        matriz_usuario_pelicula = df_bootstrap.pivot_table(
            index='user_id', 
            columns='pelicula_id', 
            values='valoracion',
            fill_value=0
        )
        
        recomendaciones_personalizadas = []
        
        # 5. Si el usuario existe, generar recomendaciones personalizadas
        if user_id in matriz_usuario_pelicula.index:
            # Obtener valoraciones del usuario
            valoraciones_usuario = matriz_usuario_pelicula.loc[user_id]
            peliculas_vistas = valoraciones_usuario[valoraciones_usuario > 0].index
            
            # Calcular similitudes con otros usuarios
            similitudes = []
            for otro_usuario in matriz_usuario_pelicula.index:
                if otro_usuario != user_id:
                    v_1 = valoraciones_usuario.values
                    v_2 = matriz_usuario_pelicula.loc[otro_usuario].values
                    
                    # Verificar desviación estándar distinta de 0
                    if np.std(v_1) == 0 or np.std(v_2) == 0:
                        continue  # Saltar usuarios sin variabilidad
                    
                    correlacion = np.corrcoef(v_1, v_2)[0, 1]
                    
                    if not np.isnan(correlacion):
                        similitudes.append((otro_usuario, correlacion))
            # Ordenar por similitud (más similares primero)
            similitudes.sort(key=lambda x: x[1], reverse=True)
            usuarios_similares = [u[0] for u in similitudes[:50]]  # Top 50 usuarios similares
            
            # Recomendar películas de usuarios similares
            recomendaciones_scores = {}
            for usuario_similar in usuarios_similares:
                valoraciones_similar = matriz_usuario_pelicula.loc[usuario_similar]
                for pelicula_id, rating in valoraciones_similar.items():
                    if rating > 3 and pelicula_id not in peliculas_vistas:  # Solo películas bien valoradas
                        if pelicula_id not in recomendaciones_scores:
                            recomendaciones_scores[pelicula_id] = []
                        recomendaciones_scores[pelicula_id].append(rating)
            
            # Calcular promedio de scores y ordenar
            peliculas_recomendadas = []
            for pelicula_id, ratings in recomendaciones_scores.items():
                promedio = np.mean(ratings)
                peliculas_recomendadas.append((pelicula_id, promedio))
            
            peliculas_recomendadas.sort(key=lambda x: x[1], reverse=True)
            
            # Seleccionar top recomendaciones con aleatoriedad
            top_candidates = peliculas_recomendadas[:k_recomendaciones*3]  # Más candidatos
            if len(top_candidates) >= k_recomendaciones:
                # Seleccionar aleatoriamente de los top candidatos para variabilidad
                peliculas_finales = np.random.choice(
                    len(top_candidates), 
                    size=min(k_recomendaciones, len(top_candidates)), 
                    replace=False
                )
                peliculas_seleccionadas = [top_candidates[i][0] for i in peliculas_finales]
            else:
                peliculas_seleccionadas = [p[0] for p in top_candidates]
            
            # Obtener datos de las películas recomendadas
            for pelicula_id in peliculas_seleccionadas:
                cur.execute("""
                    SELECT p.id, p.titulo, d.descripcion, c.imagen_card
                    FROM peliculas p
                    LEFT JOIN descripciones d ON p.id = d.pelicula_id
                    LEFT JOIN cards c ON p.id = c.pelicula_id
                    WHERE p.id = %s
                """, (int(pelicula_id),))
                
                resultado = cur.fetchone()
                if resultado:
                    id_peli, titulo, descripcion, imagen = resultado
                    imagen_b64 = base64.b64encode(imagen).decode('utf-8') if imagen else None
                    recomendaciones_personalizadas.append({
                        'id': id_peli,
                        'titulo': titulo,
                        'descripcion': descripcion or '',
                        'card': imagen_b64
                    })
        
        # 6. Obtener recomendaciones generales (películas populares con Bootstrap)
        cur.execute("""
            SELECT 
                m.id, 
                m.title, 
                ROUND(AVG(r.rating), 2) AS promedio,
                COUNT(r.rating) AS cantidad
            FROM movies m
            JOIN rankings r ON m.id = r.movie_id
            GROUP BY m.id, m.title
            HAVING COUNT(r.rating) >= 5
            ORDER BY promedio DESC, cantidad DESC
            LIMIT 20;
        """)
        
        peliculas_populares = cur.fetchall()
        
        # Si hay pocas películas, relajar criterios
        if len(peliculas_populares) < 10:
            print(f"⚠️  Solo {len(peliculas_populares)} películas con 5+ valoraciones. Relajando criterios...")
            
            cur.execute("""
                SELECT 
                    m.id, 
                    m.title, 
                    ROUND(AVG(r.rating), 2) AS promedio,
                    COUNT(r.rating) AS cantidad
                FROM movies m
                JOIN rankings r ON m.id = r.movie_id
                GROUP BY m.id, m.title
                HAVING COUNT(r.rating) >= 1  -- Solo 1+ valoración
                ORDER BY promedio DESC, cantidad DESC
                LIMIT 50;
            """)
            
            peliculas_populares = cur.fetchall()
        
        # Si aún hay pocas, usar tabla peliculas como respaldo
        if len(peliculas_populares) < 10:
            print("⚠️  Pocas películas en 'movies'. Usando tabla 'peliculas'...")
            
            cur.execute("""
                SELECT 
                    p.id, 
                    p.titulo, 
                    COALESCE(ROUND(AVG(v.valoracion), 2), 4.0) AS promedio,
                    COALESCE(COUNT(v.valoracion), 0) AS cantidad
                FROM peliculas p
                LEFT JOIN valoraciones v ON p.id = v.pelicula_id
                GROUP BY p.id, p.titulo
                ORDER BY promedio DESC, cantidad DESC
                LIMIT 50;
            """)
            
            peliculas_adicionales = cur.fetchall()
            peliculas_populares.extend(peliculas_adicionales)
        
        # Seleccionar aleatoriamente para variabilidad
        if len(peliculas_populares) >= 20:
            indices_aleatorios = np.random.choice(
                len(peliculas_populares), 
                size=min(30, len(peliculas_populares)),  # Mostrar hasta 30
                replace=False
            )
            otras_recomendaciones = [peliculas_populares[i] for i in indices_aleatorios]
        else:
            otras_recomendaciones = peliculas_populares
        
        print(f"✅ Generadas {len(otras_recomendaciones)} tendencias globales")
        
        return recomendaciones_personalizadas, otras_recomendaciones
        
    except Exception as e:
        print(f"❌ Error en recomendaciones bootstrap: {e}")
        return [], []
    
    finally:
        cur.close()


if __name__ == '__main__':
    app.run(debug=True)
