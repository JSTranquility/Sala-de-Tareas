# Guía de los decoradores @ en routes.py

Los `@` de `app/routes.py` son **decoradores de Python**. Se colocan encima de una función para registrarla en Flask o añadirle un comportamiento, como comprobar permisos.

Volver al [índice de documentación](README.md). Los fragmentos siguientes se
centran en los decoradores y pueden abreviar la lógica interna de una ruta.

Un decorador recibe una función y devuelve una función u otro objeto. Algunos envuelven la función para ejecutar comprobaciones; otros la registran como ruta, manejador de errores o comando.

## 1. @wraps(view): conservar la identidad de la función

Se usa dentro de `login_required` y `admin_required`.

Estos decoradores envuelven la función original en otra llamada `wrapped`. `@wraps(view)`, importado desde `functools`, conserva el nombre, la documentación y otros atributos de la función original.

```python
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped
```

Esto permite que Flask siga identificando correctamente las funciones como `index` o `users_list`. Sin `wraps`, varias funciones decoradas podrían aparecer con el mismo nombre `wrapped` y provocar conflictos al registrar rutas.

`*args` y `**kwargs` transmiten los argumentos recibidos a la función original, como el identificador de un usuario.

## 2. @login_required: exigir inicio de sesión

Es un decorador creado en el propio proyecto.

```python
@app.get("/")
@login_required
def index():
    assigned = g.user["id"] if g.user["rol"] != "admin" else None
    return render_template("index.html", dashboard=crud.get_dashboard(assigned))
```

Antes de ejecutar `index()`, comprueba si `g.user` contiene un usuario autenticado. Si no existe, redirige al login; si existe, ejecuta la función original.

Se usa en la portada, el cierre de sesión, las consultas y la edición de tareas,
y dentro de `admin_required`.

`g.user` contiene los datos del usuario durante la petición actual. La comprobación de que la cuenta existe y sigue activa se realiza previamente en `before_request`.

## 3. @admin_required: exigir un administrador

También es un decorador creado en el proyecto. Primero comprueba el inicio de sesión mediante `@login_required`. Después verifica el rol del usuario:

```python
def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user["rol"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped
```

Si el usuario no es administrador, `abort(403)` detiene la operación y genera una respuesta de acceso denegado.

Protege todas las operaciones de usuarios y pagos, y la creación y eliminación de tareas.
La edición de tareas comprueba el rol dentro de su función: el administrador
edita el contenido y el miembro solo cambia el estado de su tarea asignada.
El rol se obtiene desde la base de datos; no se confía en un rol enviado por el navegador.

## 4. @app.before_request: comprobar cada petición antes de la ruta

```python
@app.before_request
def load_user_and_check_csrf():
    ...
```

Registra una función que Flask ejecuta antes de llamar a la función de la ruta.

En este proyecto realiza estas acciones:

1. Inicializa `g.user` sin usuario.
2. Comprueba que exista `SECRET_KEY`, necesaria para las sesiones.
3. Lee el identificador del usuario almacenado en la sesión.
4. Busca la cuenta en SQLite y comprueba que siga activa y tenga un rol permitido.
5. Guarda sus datos públicos en `g.user` o limpia la sesión si la cuenta ya no es válida.
6. Valida el token CSRF en las peticiones que pueden modificar datos.

Para facilitar la lectura, `is_active_user()` reúne las comprobaciones de la
cuenta y `check_csrf()` realiza la comparación del token. El login también usa
`is_active_user()` mediante `password_matches()` antes de verificar la contraseña.

Si la función devuelve una respuesta o llama a `abort()`, Flask detiene la petición antes de ejecutar la ruta. Si termina sin devolver una respuesta, Flask continúa.

La falta de `SECRET_KEY` produce actualmente una respuesta **503** con el mensaje «El acceso no está configurado».

### Qué hace la comprobación CSRF

El formulario incluye un token oculto vinculado a la sesión. Al recibir un POST, el servidor compara el token enviado con el de la sesión usando `secrets.compare_digest`.

Si falta o no coincide, rechaza la petición con **400**. Esto ayuda a impedir que otra página haga enviar operaciones al servidor aprovechando la sesión del usuario.

## 5. @app.errorhandler(...): responder a errores

Estos decoradores registran funciones para construir respuestas cuando ocurre un error.

| Decorador | Uso en este proyecto |
| --- | --- |
| `@app.errorhandler(sqlite3.Error)` | Atiende errores de SQLite y muestra un mensaje controlado con código 503. |
| `@app.errorhandler(400)` | Atiende solicitudes inválidas, como un token CSRF incorrecto. |
| `@app.errorhandler(403)` | Muestra que el usuario no tiene permiso. |
| `@app.errorhandler(404)` | Muestra que no se encontró la página o el registro. |

Los decoradores de 400, 403 y 404 están encima de la misma función porque comparten la plantilla de errores:

```python
@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
def request_error(error):
    ...
```

El decorador no provoca el error: indica qué función debe responder cuando aparece. Algunos errores de integridad se manejan directamente dentro de las rutas para mostrar un mensaje específico, como cuando un usuario tiene registros asociados.

## 6. @app.get(...): registrar una ruta de consulta

Se usa para abrir páginas sin modificar datos:

| Ruta | Qué muestra |
| --- | --- |
| `/` | Inicio del usuario autenticado. |
| `/users/` | Listado de usuarios. |
| `/users/<int:user_id>` | Detalle de un usuario. |
| `/tasks/` | Todas las tareas para administradores o las asignadas al miembro. |
| `/tasks/<int:task_id>` | Detalle de una tarea que el usuario puede consultar. |
| `/payments/` | Listado de pagos, solo para administradores. |
| `/payments/<int:payment_id>` | Detalle de un pago. |

```python
@app.get("/users/<int:user_id>")
@admin_required
def user_detail(user_id):
    ...
```

`<int:user_id>` captura un número de la URL y lo entrega a la función como argumento. Al visitar `/users/5`, Flask llama a la función protegida con `user_id=5`.

`@app.get(...)` es una forma abreviada de registrar una ruta con el método GET. Flask también gestiona HEAD y OPTIONS según su comportamiento habitual.

## 7. @app.post(...): registrar una acción

En el proyecto se usa para:

- `/auth/logout`: cerrar la sesión.
- `/users/<int:user_id>/delete`: eliminar un usuario.
- `/tasks/<int:task_id>/delete`: eliminar una tarea, solo para administradores.
- `/payments/<int:payment_id>/delete`: anular un pago conservando el registro.

```python
@app.post("/auth/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))
```

Abrir esas direcciones mediante GET no ejecuta la acción: Flask responde con **405, método no permitido**.

El decorador `@app.post` establece el método permitido. La comprobación CSRF se realiza por separado en `before_request`; no viene incluida automáticamente en este decorador.

## 8. @app.route(..., methods=["GET", "POST"]): mostrar y procesar formularios

```python
@app.route("/users/new", methods=["GET", "POST"])
@admin_required
def user_create():
    return save_user()
```

La misma dirección tiene dos comportamientos:

- **GET:** muestra el formulario.
- **POST:** recibe los campos, los valida y procesa el cambio.

Se utiliza en estas rutas:

| Ruta | GET | POST |
| --- | --- | --- |
| `/auth/login` | Muestra el acceso. | Verifica credenciales e inicia sesión. |
| `/users/new` | Muestra el formulario de alta. | Crea el usuario. |
| `/users/<int:user_id>/edit` | Muestra los datos actuales. | Guarda los cambios. |
| `/tasks/new` | Muestra el formulario de tarea. | Crea la tarea como administrador. |
| `/tasks/<int:task_id>/edit` | Muestra la edición permitida. | Guarda contenido como administrador o estado como miembro. |
| `/payments/new` | Muestra el formulario de pago. | Registra un pago. |
| `/payments/<int:payment_id>/edit` | Muestra el formulario permitido por su estado. | Edita pendientes o las notas de pagados. |
| `/payments/<int:payment_id>/simulate` | Muestra la simulación educativa. | Procesa aprobar/rechazar/cancelar, solo para administrador y con CSRF. |

La función puede distinguir ambos casos mediante `request.method`.

## 9. @app.cli.command(...): registrar comandos de terminal

Estos comandos se ejecutan desde la terminal, no desde una dirección web.

| Decorador | Acción |
| --- | --- |
| `@app.cli.command("init-db")` | Crea las tablas faltantes. No actualiza tablas existentes. |
| `@app.cli.command("migrate-users")` | Añade `activo` mediante una actualización explícita con respaldo previo. |
| `@app.cli.command("migrate-tasks")` | Actualiza tareas con respaldo y conserva la información histórica. |
| `@app.cli.command("migrate-payments")` | Convierte importes a centavos con respaldo y señala datos históricos pendientes. |
| `@app.cli.command("create-admin")` | Crea el primer administrador activo. |
| `@app.cli.command("reset-password")` | Restablece una contraseña guardando su hash. |

Por ejemplo:

```powershell
python -m flask --app run create-admin
```

`--app run` indica a Flask que cargue la aplicación del módulo `run.py`. `create-admin` selecciona el comando registrado por el decorador.

Los comandos de terminal no pasan por las comprobaciones HTTP de `before_request`. Deben ejecutarlos las personas que administran el servidor.

## 10. @click.option(...): definir entradas de un comando

```python
@click.option("--name", prompt="Nombre")
@click.option("--email", prompt="Correo")
```

Permiten proporcionar nombre y correo como opciones de terminal. Si no se proporcionan, `prompt` hace que el comando los pregunte.

```powershell
python -m flask --app run create-admin --name "Ana" --email "ana@example.com"
```

Los valores llegan como argumentos a la función del comando: `name` y `email`.

En `reset-password`, `@click.option("--email", prompt="Correo")` determina la cuenta cuya contraseña se va a restablecer.

## 11. @click.password_option(...): solicitar una contraseña oculta

```python
@click.password_option(
    prompt="Contraseña",
    confirmation_prompt=True
)
```

Solicita una contraseña sin mostrar los caracteres en pantalla y pide repetirla para comprobar que coincide. El valor llega a la función como el argumento `password`.

Se usa al crear el administrador y al restablecer contraseñas. Para introducir la contraseña, conviene usar la pregunta interactiva, evitando escribirla como una opción visible en el historial de la terminal.

## 12. El orden de los decoradores

Python aplica los decoradores de **abajo hacia arriba** al definir la función:

```python
@app.get("/users/")
@admin_required
def users_list():
    ...
```

Primero `admin_required` envuelve la función con la comprobación de permisos. Después `app.get` registra esa función protegida como la ruta `/users/`.

La idea equivale a:

```python
users_list = admin_required(users_list)
users_list = app.get("/users/")(users_list)
```

No significa que todas las comprobaciones se ejecuten al importar el archivo. En ese momento se registran las funciones; las comprobaciones de permisos se ejecutan al recibir una petición.

## 13. Recorrido de una petición en este proyecto

Para abrir `/users/`, el flujo es:

1. Flask identifica la ruta.
2. `before_request` carga al usuario y realiza las comprobaciones generales.
3. `admin_required` comprueba el inicio de sesión y el rol de administrador.
4. Si está permitido, se ejecuta `users_list()`.
5. La función consulta el CRUD y renderiza la plantilla.
6. Si ocurre un error no manejado en la ruta, Flask busca el manejador de errores correspondiente.

En un POST, la comprobación CSRF ocurre en el segundo paso, antes de que se ejecute la función que modifica los datos.
