from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os
from datetime import timedelta, datetime
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Clave secreta aleatoria
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

# Configuración de conexión a MySQL desde variables de entorno
HOST = os.getenv("MYSQL_HOST")
USER = os.getenv("MYSQL_USER")
PASSWORD = os.getenv("MYSQL_PASSWORD")
DBNAME = os.getenv("MYSQL_DBNAME")

# Función para obtener la conexión a MySQL
def obtener_conexion():
    return mysql.connector.connect(
        host=HOST,
        user=USER,
        password=PASSWORD,
        database=DBNAME
    )

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario']
        contraseña = request.form['contraseña']

        # Verificar credenciales
        conexion = obtener_conexion()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute('SELECT * FROM dueño WHERE usuario = %s AND contraseña = %s', (usuario, contraseña))
        dueño = cursor.fetchone()
        cursor.close()
        conexion.close()

        if dueño:
            session['usuario'] = usuario
            session.permanent = True
            return redirect(url_for('listar_clientes'))
    return render_template('login.html')

def login_requerido(func):
    def wrapper(*args, **kwargs):
        if 'usuario' not in session:  # Verifica si el usuario está en sesión
            return redirect(url_for('login'))  # Redirige al login si no está autenticado
        return func(*args, **kwargs)  # Si está autenticado, permite el acceso
    wrapper.__name__ = func.__name__
    return wrapper


@app.route('/cambiar_usuario_contraseña', methods=['GET', 'POST'])
@login_requerido
def cambiar_usuario_contraseña():
    if request.method == 'POST':
        nuevo_usuario = request.form['nuevo_usuario']
        nueva_contraseña = request.form['nueva_contraseña']
        confirmar_contraseña = request.form['confirmar_contraseña']

        if nueva_contraseña != confirmar_contraseña:
            flash('Las contraseñas no coinciden.', 'error')
            return render_template('cambiar_usuario_contraseña.html')

        # Actualizar en la base de datos
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute('''
            UPDATE dueño
            SET usuario = %s, contraseña = %s
            WHERE usuario = %s
        ''', (nuevo_usuario, nueva_contraseña, session['usuario']))
        conexion.commit()
        cursor.close()
        conexion.close()

        # Actualizar sesión con el nuevo usuario
        session['usuario'] = nuevo_usuario
        return redirect(url_for('listar_clientes'))

    return render_template('cambiar_usuario_contraseña.html')

@app.route('/clientes')
@login_requerido
def listar_clientes():
    page = request.args.get('page', 1, type=int)
    per_page = 5
    offset = (page - 1) * per_page
    
    conexion = obtener_conexion()
    cursor = conexion.cursor()  # Quitamos dictionary=True
    
    cursor.execute('SELECT COUNT(*) FROM clientes')
    total_clientes = cursor.fetchone()[0]
    total_paginas = (total_clientes // per_page) + (1 if total_clientes % per_page else 0)

    cursor.execute('''
        SELECT id_cliente, nombre, telefono, tipo_membresia, fecha_inicio, fecha_vencimiento
        FROM clientes
        ORDER BY id_cliente DESC
        LIMIT %s OFFSET %s
    ''', (per_page, offset))
    
    clientes = cursor.fetchall()
    cursor.close()
    conexion.close()

    fecha_actual = datetime.now().date()
    fecha_limite_aviso = fecha_actual + timedelta(days=3)
    
    return render_template(
        'dashboard.html', 
        clientes=clientes, 
        page=page, 
        total_paginas=total_paginas, 
        fecha_actual=fecha_actual,
        fecha_limite_aviso=fecha_limite_aviso)

@app.route('/buscar_clientes')
@login_requerido
def buscar_clientes():
    query = request.args.get('query', '').strip().lower()
    fecha_actual = datetime.now().date()
    fecha_limite_aviso = fecha_actual + timedelta(days=3)

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute('''
        SELECT id_cliente, nombre, telefono, fecha_vencimiento
        FROM clientes
        WHERE LOWER(nombre) LIKE %s OR id_cliente LIKE %s
        ORDER BY id_cliente DESC
        LIMIT 5
    ''', (f"%{query}%", f"%{query}%"))

    clientes = cursor.fetchall()
    cursor.close()
    conexion.close()

    clientes_data = []
    for c in clientes:
        estado = ''
        if c[3] < fecha_actual:
            estado = 'vencida'
        elif fecha_actual <= c[3] <= fecha_limite_aviso:
            dias_restantes = (c[3] - fecha_actual).days
            estado = f'proxima_vencer_{dias_restantes}'
        
        clientes_data.append({
            'id': c[0],
            'nombre': c[1],
            'telefono': c[2],
            'vencimiento': c[3].strftime('%Y-%m-%d'),
            'estado': estado
        })

    return jsonify({'clientes': clientes_data})

@app.route('/clientes/nuevo', methods=['GET', 'POST'])
@login_requerido
def agregar_cliente():
    
    if request.method == 'POST':
        nombre = request.form['nombre']
        telefono = request.form['telefono']
        tipo_membresia = request.form['tipo_membresia']
        fecha_inicio = request.form['fecha_inicio']
        
        fecha_vencimiento = calcular_fecha_vencimiento(fecha_inicio, tipo_membresia)

        conexion = obtener_conexion()
        cursor = conexion.cursor()

        try:
            año_actual = datetime.now().year % 100 
            cursor.execute("SELECT MAX(id_cliente) FROM clientes WHERE id_cliente LIKE %s", (f"{año_actual}%",))
            max_id = cursor.fetchone()[0]

            if max_id:
                secuencia_actual = int(str(max_id)[2:])
                nueva_secuencia = secuencia_actual + 1
            else:
                nueva_secuencia = 1 

    
            id_cliente = f"{año_actual}{nueva_secuencia:03}"

            cursor.execute(''' 
                INSERT INTO clientes (id_cliente, nombre, telefono, tipo_membresia, fecha_inicio, fecha_vencimiento)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (id_cliente, nombre, telefono, tipo_membresia, fecha_inicio, fecha_vencimiento))
            
            conexion.commit()
            return redirect(url_for('listar_clientes'))

        except Exception as e:
            conexion.rollback()
        finally:
            cursor.close()
            conexion.close()

    return render_template('nuevo_cliente.html')

def calcular_fecha_vencimiento(fecha_inicio, tipo_membresia):
    duraciones = {
        'mensual': 30,
        'trimestral': 90,
        'semestral': 180,
        'anual': 365
    }

    fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d')
    duracion = duraciones.get(tipo_membresia)
    fecha_vencimiento = fecha_inicio + timedelta(days=duracion)
    return fecha_vencimiento.strftime('%Y-%m-%d')

@app.route('/clientes/editar/<int:id>', methods=['GET', 'POST'])
@login_requerido
def editar_cliente(id):
    conexion = obtener_conexion()
    cursor = conexion.cursor(dictionary=True)

    cursor.execute('SELECT * FROM clientes WHERE id_cliente = %s', (id,))
    cliente = cursor.fetchone()

    if request.method == 'POST':
        nombre = request.form['nombre']
        telefono = request.form['telefono']
       
        cursor.execute('''
            UPDATE clientes
            SET nombre = %s, telefono = %s
            WHERE id_cliente = %s
        ''', (nombre, telefono, id))
        conexion.commit()
        return redirect(url_for('listar_clientes'))

    cursor.close()
    conexion.close()
    return render_template('editar_cliente.html', cliente=cliente)


@app.route('/clientes/<int:id>/actualizar_membresia', methods=['GET', 'POST'])
@login_requerido
def actualizar_membresia(id):
    # Obtener la conexión y cursor
    conexion = obtener_conexion()
    cursor = conexion.cursor(dictionary=True)

    # Obtener los datos del cliente actual
    cursor.execute('SELECT id_cliente, nombre, tipo_membresia, fecha_inicio, fecha_vencimiento FROM clientes WHERE id_cliente = %s', (id,))
    cliente = cursor.fetchone()

    if request.method == 'POST':
        # Obtener los datos del formulario
        nuevo_tipo_membresia = request.form['tipo_membresia']
        nueva_fecha_inicio = request.form['fecha_inicio']

        # Calcular la nueva fecha de vencimiento
        nueva_fecha_vencimiento = calcular_fecha_vencimiento(nueva_fecha_inicio, nuevo_tipo_membresia)

        try:
            # Actualizar los datos en la base de datos
            cursor.execute('''
                UPDATE clientes 
                SET tipo_membresia = %s, fecha_inicio = %s, fecha_vencimiento = %s 
                WHERE id_cliente = %s
            ''', (nuevo_tipo_membresia, nueva_fecha_inicio, nueva_fecha_vencimiento, id))
            conexion.commit()

            flash('Membresía actualizada exitosamente.', 'success')
            return redirect(url_for('detalles_cliente', id=id))
        except Exception as e:
            conexion.rollback()

    # Cerrar conexión
    cursor.close()
    conexion.close()

    # Renderizar la página con el formulario prellenado
    return render_template('actualizar_membresia.html', cliente=cliente)

@app.route('/clientes/eliminar/<int:id>', methods=['POST'])
@login_requerido
def eliminar_cliente(id):
    # Conectar a la base de datos
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    # Eliminar el cliente con el ID proporcionado
    cursor.execute('DELETE FROM clientes WHERE id_cliente = %s', (id,))
    conexion.commit()

    # Cerrar la conexión
    cursor.close()
    conexion.close()
    return redirect(url_for('listar_clientes'))



@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('usuario', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)