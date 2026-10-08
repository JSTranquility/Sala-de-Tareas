# Sala de Tareas: exposición y defensa del código

Este documento es un guion para presentar el proyecto y una guía de estudio para responder preguntas sobre su implementación. Está basado en el código actual. Los ejemplos con puntos suspensivos son fragmentos abreviados, no archivos completos para ejecutar.

Para exponer sin leer toda la guía, usar [PRESENTACION.md](PRESENTACION.md).
Los comandos se encuentran en [EJECUTAR.md](EJECUTAR.md) y [PRUEBAS.md](PRUEBAS.md).

## 1. Introducción para decir en la exposición

«Buenos días. Voy a presentar Sala de Tareas, una aplicación web que permite organizar usuarios, asignar tareas y registrar los pagos relacionados con esas tareas.

El objetivo es tener la información en un mismo lugar y controlar qué puede hacer cada usuario. Un administrador gestiona las cuentas, las tareas y los pagos. Un miembro consulta sus tareas asignadas y actualiza su estado.

El proyecto utiliza Python para la lógica, Flask para atender las peticiones web, SQLite para guardar los datos y HTML con Jinja2 y CSS para mostrar las pantallas. Ahora explicaré cómo se conectan estas partes y cómo se protegen las operaciones.»

## 2. Qué está implementado

| Área | Funcionamiento actual |
| --- | --- |
| Acceso | Inicio y cierre de sesión; rechazo de cuentas inactivas. |
| Usuarios | El administrador puede crear, listar, consultar, editar, eliminar y desactivar cuentas, con restricciones. |
| Tareas | El administrador crea y asigna tareas; el miembro consulta las suyas y cambia su estado. |
| Pagos | El administrador registra, consulta, edita según el estado y anula pagos en USD o DOP. |
| Seguridad | Hash de contraseñas, validación en servidor, permisos, CSRF y SQL parametrizado. |
| Conservación de datos | Actualizaciones explícitas de esquema con respaldo y comprobaciones. |
| Dashboard y listados | Tareas por estado y vencimiento; pagos por moneda; búsqueda, filtros y páginas de 10 registros. |
| Simulación de PayPal | Aprobar, rechazar o cancelar una operación ficticia, sin conexión externa. |
| Interfaz | Diseño adaptable a móvil, etiquetas de estado y tema claro/oscuro persistente. |

El proyecto conserva tablas y operaciones de materias y asistencias. Las materias existentes pueden seleccionarse en tareas; no hay una interfaz completa nueva para gestionar esas dos entidades.

Las siete etapas del alcance educativo están implementadas. No hay registro público
ni una pasarela que cobre dinero: PayPal se simula localmente y el módulo de pagos
registra información. Los miembros no ven resúmenes financieros.

## 3. Cómo se conectan las partes

```text
Navegador: muestra un formulario y envía una petición
    ↓
run.py: configura Flask y registra las rutas
    ↓
app/routes.py: comprueba acceso y decide la operación
    ↓
app/forms.py: valida los campos recibidos
    ↓
app/utils/data/CRUD.py: ejecuta las consultas SQL
    ↓
app/utils/data/database.py: gestiona la conexión y transacción
    ↓
SQLite: almacena los registros

La ruta recibe el resultado y renderiza una plantilla
o redirige a otra página que mostrará el resultado.
```

No todas las peticiones recorren cada módulo: listar tareas, por ejemplo, no necesita validar un formulario. La separación permite cambiar la presentación sin reescribir las consultas.

**Para decir:** «Las rutas coordinan la petición, los formularios validan la entrada, el CRUD trabaja con los datos y las plantillas los presentan.»

## 4. Desglose de `run.py`: el punto de entrada

```python
app = Flask(__name__, template_folder="app/templates", static_folder="app/static")
```

Esta línea crea la aplicación. `__name__` ayuda a Flask a identificar el módulo y resolver recursos. `template_folder` indica dónde están los archivos HTML; `static_folder`, dónde están CSS y JavaScript.

`os.environ.get(...)` lee configuración del entorno: `SECRET_KEY`, `FLASK_DEBUG` y `SESSION_COOKIE_SECURE`. Las variables llegan como texto; por eso el código interpreta `"1"` y `"true"` como valores verdaderos.

`app.config.update(...)` configura también la ruta de SQLite y las cookies:

- `HTTPONLY=True`: impide que JavaScript lea la cookie de sesión.
- `SAMESITE="Lax"`: limita su envío en ciertos contextos entre sitios.
- `SECURE`: cuando está activado, la cookie se envía por HTTPS.

`register_routes(app)` conecta las funciones de `routes.py` con la aplicación.

```python
if __name__ == "__main__":
    app.run()
```

El servidor de desarrollo arranca cuando ejecutamos `python run.py`. Importar el módulo desde las pruebas no ejecuta ese bloque. El servidor de desarrollo no es el servidor previsto para producción.

**Pregunta posible: ¿por qué no guardar la clave secreta en el código?**

Porque debe mantenerse privada y configurable. Se usa para firmar la sesión; compartirla en el repositorio permitiría comprometer esa protección. Un archivo `.env` no se carga automáticamente en este proyecto.

## 5. Desglose de `routes.py`: peticiones y permisos

### 5.1 Qué significa una ruta

```python
@app.get("/users/")
@admin_required
def users_list():
    return render_template("users/list.html", **list_context("users", {
        "rol": ("Rol", {"admin": "Administrador", "member": "Miembro"}),
        "activo": ("Estado", {"1": "Activo", "0": "Inactivo"}),
    }))
```

`@app.get` registra la dirección para peticiones GET. `@admin_required` protege la
función. `list_context()` valida los filtros y la página, consulta los registros
y construye los enlaces de paginación. `render_template()` genera el HTML.
`**` pasa las entradas del diccionario como argumentos con nombre.

Un decorador es una función que recibe otra función y añade comportamiento. En este caso, registra una dirección o comprueba permisos. Los decoradores se aplican de abajo hacia arriba: Flask registra la función ya protegida. `@wraps(view)` conserva su nombre y otros metadatos al envolverla.

### 5.2 Objetos de Flask que aparecen en el código

| Elemento | Para qué se usa |
| --- | --- |
| `request` | Consultar el método HTTP y los campos de `request.form`. |
| `session` | Conservar el identificador del usuario y el token CSRF entre peticiones. |
| `g.user` | Tener disponible el usuario verificado durante la petición actual. |
| `render_template` | Construir una página HTML usando Jinja2. |
| `url_for` | Generar una dirección a partir del nombre de la función de ruta. |
| `redirect` | Pedir al navegador que visite otra dirección. |
| `flash` | Guardar un mensaje que se mostrará en la siguiente página. |
| `abort` | Interrumpir la operación con un error HTTP. |

`g` dura una petición; `session` permite mantener información entre peticiones. En la configuración actual, Flask usa una cookie firmada para la sesión: la firma protege su integridad, pero no cifra su contenido. Por eso no se guardan contraseñas en ella.

### 5.3 Qué ocurre antes de cada petición

`load_user_and_check_csrf()` está registrada con `@app.before_request`:

1. Inicializa `g.user` en `None`.
2. Si falta la clave secreta, devuelve un error de configuración con código 503.
3. Lee `user_id` de la sesión y consulta la cuenta en SQLite.
4. Verifica que exista, esté activa y tenga un rol permitido.
5. Guarda la cuenta válida en `g.user`; si dejó de ser válida, limpia la sesión.
6. Ejecuta la comprobación CSRF cuando corresponde.

Así, desactivar una cuenta o cambiar su rol afecta la siguiente petición, aunque ya tuviera una sesión abierta.

### 5.4 Login y logout

En GET, `login()` presenta el formulario. En POST, normaliza el correo, busca la cuenta con `get_user_for_auth_by_email()` y verifica el hash mediante `password_matches()` y `check_password_hash()`.

Si las credenciales son correctas, limpia la sesión anterior, guarda `session["user_id"]`, genera un nuevo token CSRF y redirige al inicio. Si fallan, muestra un mensaje general. `logout()` acepta POST, limpia la sesión y redirige al login.

### 5.5 Autenticación y autorización

Autenticación significa comprobar quién eres. Autorización significa decidir qué puedes hacer.

`login_required` exige una cuenta válida. `admin_required` exige además el rol `admin`. Para tareas, `task_or_404()` comprueba también el registro concreto: un miembro no puede abrir una tarea asignada a otra persona cambiando el ID de la URL.

Los administradores acceden a usuarios y pagos. Los miembros solo ven sus tareas y cambian su estado; los campos adicionales que intenten enviar no se usan para modificar título, prioridad o asignación.

### 5.6 Métodos HTTP y errores

GET muestra información o formularios. POST crea, modifica, elimina, anula o cierra la sesión. Las rutas de eliminación no aceptan GET.

| Código | Significado en el proyecto |
| --- | --- |
| 200 | Página mostrada correctamente. |
| 302 | Redirección, por ejemplo al login o al detalle tras guardar. |
| 400 | Formulario inválido o token CSRF incorrecto. |
| 403 | Usuario sin permiso. |
| 404 | Registro inexistente. |
| 405 | Método no permitido para esa ruta. |
| 503 | Problema de configuración de acceso o error de SQLite atendido por la aplicación. |

## 6. Desglose de `forms.py`: validación

Las funciones reciben campos y devuelven dos diccionarios:

```python
values, errors = validate_task_form(request.form)
```

`values` contiene los datos que se usarán o volverán a mostrar. `errors` contiene mensajes asociados a campos. `if not errors:` significa que no se detectaron errores de validación.

- `validate_user_form()`: valida nombre, correo, teléfono, rol, indicador activo y longitud de contraseña. En una edición, una contraseña vacía conserva la anterior.
- `validate_task_form()`: valida título, descripción, prioridad, estado, fecha e identificadores opcionales.
- `validate_task_status()`: lee únicamente el estado, que es lo que un miembro puede cambiar.
- `validate_payment_form()`: valida IDs, importe, moneda, método y estado.
- `validate_payment_notes()`: valida la longitud de las notas.

`.strip()` elimina espacios al principio y al final. `.lower()` normaliza el correo. `re.fullmatch()` exige que todo el texto cumpla un patrón. `date.fromisoformat()` comprueba la fecha; una comparación adicional exige el formato `AAAA-MM-DD`.

Las rutas comprueban además que los IDs correspondan a registros reales y utilizables. Un número con formato válido no garantiza que el usuario exista o esté activo.

**Pregunta posible: ¿para qué validar en Python si el HTML tiene `required`?**

Porque el navegador puede modificarse o saltarse. La validación del servidor decide si los datos se aceptan; la del HTML facilita el uso del formulario.

## 7. Desglose de `database.py`: conexión y tablas

### 7.1 Ubicación de la base

La base predeterminada es `saladetareas.db`, en la raíz. `get_database_path()` permite configurar `DATABASE_PATH`; las rutas relativas se resuelven desde la raíz del proyecto.

Una conexión normal usa `mode=rw`, que exige que el archivo exista. Solo la inicialización explícita usa `mode=rwc` y permite crearlo. Esto evita abrir accidentalmente una base vacía por una ruta incorrecta.

### 7.2 Transacciones y `with`

`get_connection()` utiliza `@contextmanager` para poder escribirse así:

```python
with get_connection() as connection:
    connection.execute("DELETE FROM Usuarios WHERE id = ?", (id,))
```

Abre la conexión, configura `sqlite3.Row` y activa `PRAGMA foreign_keys = ON`. `yield connection` entrega temporalmente la conexión al bloque `with`. Al finalizar, hace `commit()` si todo fue bien, `rollback()` si hubo una excepción y `close()` en el bloque `finally`.

- `commit`: confirma los cambios de la transacción.
- `rollback`: revierte los cambios pendientes de esa transacción.
- `finally`: ejecuta la limpieza tanto en éxito como en error.
- `sqlite3.Row`: permite leer columnas por nombre, como `row["id"]`.

En ciertas operaciones, `BEGIN IMMEDIATE` obtiene la transacción de escritura antes de comprobar y modificar los datos. Reduce conflictos entre esas comprobaciones y otras escrituras; SQLite sigue pudiendo producir errores de bloqueo si hay contención.

### 7.3 Tablas y relaciones

| Tabla | Datos y relaciones principales |
| --- | --- |
| `Usuarios` | Nombre, correo único, hash, teléfono, rol, activo y creación. |
| `Tareas` | Título, descripción, estado, prioridad, vencimiento, asignado, creador y materia. |
| `Pagos` | Receptor, tarea, centavos, moneda, método, estado y fechas. |
| `Materias` | Materias que pueden asociarse a tareas. |
| `Asistencias` | Registros relacionados con usuarios. |

Una clave primaria identifica un registro. Una clave foránea exige que una referencia apunte a un registro existente. `CHECK` limita valores, como los estados permitidos; `UNIQUE` impide duplicados según la restricción definida.

En `Tareas`, **`usuario_id` es el asignado** y **`creador_id` es el autor**. En `Pagos`, `usuario_id` es el receptor, que se selecciona explícitamente y puede diferir del asignado de la tarea.

`initialize_database()` crea las tablas que faltan cuando se ejecuta su comando. `CREATE TABLE IF NOT EXISTS` no actualiza la estructura de una tabla existente.

## 8. Desglose de `CRUD.py`: las consultas

CRUD significa Create, Read, Update y Delete: crear, consultar, actualizar y eliminar. Este archivo usa SQL directo mediante `sqlite3`; no utiliza un ORM.

### 8.1 Funciones compartidas

| Función | Resultado |
| --- | --- |
| `_insert()` | ID nuevo mediante `cursor.lastrowid`. |
| `_modify()` | Número de filas afectadas mediante `rowcount`. |
| `_fetch_one()` | Diccionario o `None` si no existe. |
| `_fetch_all()` | Lista de diccionarios; puede estar vacía. |
| `_current_utc_time()` | Fecha y hora UTC en formato ISO. |

El prefijo `_` indica una función de uso interno por convención; no impide técnicamente llamarla. El CRUD devuelve datos, mientras que las rutas deciden respuestas HTTP y mensajes.

### 8.2 SQL parametrizado

```python
return _fetch_one(
    f"SELECT {USER_FIELDS} FROM Usuarios WHERE id = ?", (id,)
)
```

El `?` representa un valor que SQLite recibe por separado. `(id,)` es una tupla de un elemento; la coma es necesaria. Así la entrada se interpreta como dato y no como instrucciones SQL.

Aquí la f-string inserta `USER_FIELDS`, una constante de columnas definida en el código. No inserta la entrada del usuario. También se concatenan fragmentos SQL fijos, como `TASK_SELECT` y una condición; los valores externos siguen usando parámetros.

### 8.3 Usuarios y hashes

`create_user()` llama a `generate_password_hash()` antes de insertar la contraseña. `update_user()` conserva el hash cuando recibe `contrasena=None` y genera uno nuevo cuando se cambia la clave.

Las consultas públicas seleccionan `USER_FIELDS`, que excluye `contrasena`. Solo `get_user_for_auth_by_email()` incluye el hash para verificar el login. Un hash no se descifra: se comprueba la contraseña candidata con `check_password_hash()`.

### 8.4 Tareas y JOIN

`TASK_SELECT` combina tareas con usuarios y materias para mostrar sus nombres. Usa `LEFT JOIN`: conserva una tarea aunque no tenga asignado, creador conocido o materia. Un `INNER JOIN` descartaría filas sin una coincidencia.

`update_task()` conserva el creador y la fecha de creación. Para miembros, la actualización se limita a:

```sql
UPDATE Tareas SET estado = ?, fecha_actualizacion = ?
WHERE id = ? AND usuario_id = ?
```

Además del permiso de la ruta, el SQL exige que la tarea siga asignada a ese miembro al ejecutar el cambio.

### 8.5 Pagos y reglas de negocio

`create_payment()` valida dentro de la transacción que el monto sea un entero positivo, la tarea exista y no esté cancelada, y el receptor esté activo. La fecha de pago la calcula el servidor si el estado es `pagado`.

`update_payment()` modifica pendientes o completa históricos. Un pago pagado solo admite corregir notas con `update_payment_notes()` o anularse. Un anulado no puede editarse ni reactivarse.

`annul_payment()` cambia el estado sin borrar importe ni fecha de pago. Aunque la URL termina en `/delete`, la operación de pagos es una anulación. Los pagos asociados bloquean la eliminación de usuarios y tareas, incluso después de anularlos.

### 8.6 Dashboard, búsqueda y paginación

`get_dashboard()` cuenta tareas por estado y vencimiento. Los miembros solo reciben
sus tareas asignadas; para administradores, también suma pagos válidos por moneda
y estado usando centavos enteros. Excluye anulados e históricos incompletos.

`get_filtered_page()` combina SQL predefinido con valores parametrizados. Consulta
el total y usa `LIMIT ? OFFSET ?` para devolver 10 registros por página. La
restricción de asignación del miembro se aplica dentro del SQL, antes de contar
y paginar, para no revelar tareas ajenas.

## 9. Desglose de `models.py`: dinero exacto

El nombre del archivo no significa que haya modelos de un ORM. Contiene opciones de pagos y auxiliares monetarios.

```python
cents = int(Decimal(value) * 100)
```

`amount_to_cents()` valida primero un texto positivo con hasta dos decimales. Después convierte, por ejemplo, `"125.50"` a `12550` centavos. Se almacena un `INTEGER`; se evita `float` por sus aproximaciones binarias.

`format_amount()` usa `divmod(abs(cents), 100)` para separar unidades y centavos. `:02d` muestra dos dígitos: `5` se muestra como `05`. El importe conserva su moneda, USD o DOP. No hay conversión automática ni se mezclan monedas.

Las fechas nuevas de creación, actualización y pago usan UTC con zona explícita; el vencimiento de una tarea es una fecha sin hora.

## 10. Plantillas: HTML, CSS y Jinja2

`base.html` comparte navegación y mensajes, y enlaza los estilos locales de
`app/static/styles.css`. Las demás plantillas la extienden:

```jinja
{% extends "base.html" %}
{% block content %}
    <h2>{{ 'Editar tarea' if editing else 'Crear tarea' }}</h2>
{% endblock %}
```

`{% ... %}` ejecuta instrucciones de plantilla, como condiciones y bucles. `{{ ... }}` imprime una expresión. Los bloques permiten reemplazar partes de la página base.

El formulario envía campos cuyo atributo `name` coincide con las claves leídas en `request.form`. El campo oculto `csrf_token` acompaña al POST. Los errores aparecen junto al campo correspondiente y se conservan los valores válidos para facilitar su corrección.

Jinja escapa automáticamente el contenido en estas plantillas HTML. Un título con etiquetas se muestra como texto en vez de ejecutarse como HTML. Ocultar enlaces según el rol mejora la interfaz, pero la protección real también se comprueba en las rutas.

`ui.html` comparte iconos SVG y etiquetas. `app/static/js/theme.js` cambia el tema
sin enviar peticiones al servidor: usa `localStorage` para recordar la elección
y la preferencia del sistema si no hay una guardada. No guarda credenciales.

### Simulación de PayPal

`simulate_payment()` valida el importe, moneda y resultado elegido y devuelve
un diccionario con mensaje y referencia ficticia. La ruta exige administrador
y CSRF. Aprobar llama a `mark_payment_paid()`, que guarda fecha UTC y una nota
educativa en una transacción, únicamente si el pago sigue pendiente. Rechazar
o cancelar lo conserva pendiente. No se llama a la API de PayPal ni cambia la tarea.

## 11. CSRF explicado para la defensa

Un ataque CSRF intenta que el navegador de una persona autenticada envíe una operación no deseada desde otro sitio.

`csrf_token()` genera un valor aleatorio con `secrets.token_urlsafe(32)` y lo guarda en la sesión. Cada formulario envía ese valor en un campo oculto. `check_csrf()` lo compara con el esperado mediante `secrets.compare_digest()` y rechaza tokens ausentes o incorrectos.

Los métodos GET, HEAD y OPTIONS no pasan esa comprobación de token porque no se usan para cambiar datos. Login y logout también tienen protección CSRF. El token no sustituye la autenticación ni los permisos: las tres comprobaciones cumplen funciones diferentes.

## 12. Ejemplo completo: crear una tarea

Supongamos que el administrador crea «Preparar exposición», asignada a Ana y con prioridad alta.

1. El navegador pide GET `/tasks/new`.
2. `before_request` carga la cuenta y `admin_required` comprueba el rol.
3. `task_create()` llama a `save_task()`; en GET presenta `tasks/form.html`.
4. El formulario envía POST a la misma ruta con sus datos y el token CSRF.
5. Se comprueban nuevamente sesión, token y rol.
6. `validate_task_form()` valida contenido, fecha, estado, prioridad e IDs.
7. `validate_task_relations()` comprueba que Ana exista y esté activa, y que la materia exista si se eligió.
8. La ruta llama a `crud.create_task()`. El creador sale de `g.user["id"]`, no de un campo enviado por el navegador.
9. El CRUD añade las fechas y ejecuta el INSERT parametrizado mediante la conexión centralizada.
10. Se confirma la transacción y se devuelve el ID nuevo.
11. La ruta usa `flash()` y redirige al detalle, que el navegador obtiene con GET.

Si hay errores de validación, se muestra el formulario con código 400 sin insertar la tarea. Si falla una restricción SQL, se revierte la transacción y la ruta informa del problema.

Esta secuencia de POST seguido de una redirección a GET evita repetir el envío al recargar la página final. No garantiza por sí sola que dos envíos simultáneos sean únicos.

## 13. Actualizaciones del esquema: `migrations/`

Los scripts son actualizaciones hechas con `sqlite3`, sin Alembic ni Flask-Migrate:

- `add_user_active.py`: incorpora el indicador de cuenta activa.
- `add_task_fields.py`: adapta las tareas para prioridad, creador, actualización y asignación opcional.
- `add_payment_fields.py`: convierte importes históricos y añade los campos y relaciones de pagos.

Se ejecutan explícitamente, crean respaldos cuando actualizan y comprueban integridad. No se ejecutan al importar módulos ni al arrancar el servidor.

Para cambios que SQLite no resuelve directamente, los scripts copian los datos a una tabla con el esquema nuevo, verifican la copia y sustituyen la tabla dentro de una transacción. Conservan registros e identificadores; un fallo revierte la actualización.

La conversión histórica de pagos usa `Decimal(str(monto)) * 100` y `ROUND_HALF_UP`: `12.345` pasa a `1235` centavos. También conserva la representación original del importe. En entradas nuevas, más de dos decimales se rechazan en lugar de redondearse.

No se inventan la tarea, moneda ni fecha de pago de un registro histórico. Los datos desconocidos quedan pendientes de completar con información real. La fecha original del registro no se interpreta automáticamente como fecha de pago.

**Idempotencia:** repetir una actualización sobre un esquema que el script reconoce como actualizado no vuelve a transformar sus datos.

## 14. Pruebas: qué demuestran y dónde están

El proyecto usa `unittest`, el cliente de pruebas de Flask y bases SQLite temporales.

| Archivo | Casos que contiene |
| --- | --- |
| `test_stage_one.py` | Configuración, inicialización explícita, conexión y transacciones. |
| `test_crud.py` | Resultados del CRUD, hashes, duplicados, relaciones e entradas SQL tratadas como datos. |
| `test_users_auth.py` | Login, logout, roles, CSRF, desactivación y usuarios. |
| `test_tasks.py` | CRUD de tareas, asignación, permisos por registro y campos manipulados. |
| `test_payments.py` | Centavos, monedas, fechas, estados, anulaciones y actualización histórica. |
| `test_paypal_simulation.py` | Los tres resultados ficticios, permisos, CSRF y aprobación repetida. |
| `test_dashboard_lists.py` | Totales, vencimientos, filtros, paginación y privacidad por usuario. |
| `test_final_flows.py` | Recorridos completos con comandos, login real, formularios y relaciones. |

`setUp()` prepara cada caso y `tearDown()` limpia sus recursos. El cliente de Flask simula peticiones sin abrir un navegador ni arrancar un servidor externo. Las aserciones comparan resultados esperados con los obtenidos.

El comando documentado es:

```powershell
python -m unittest discover -s tests -v
```

Esta guía describe las pruebas existentes; no constituye un informe de ejecución. Para afirmar que pasan, hay que ejecutar el comando y revisar su resultado.

## 15. Preguntas del profesor y respuestas para practicar

### ¿Por qué elegiste Flask?

Porque permite definir rutas, trabajar con sesiones y renderizar HTML con poca estructura adicional. Es suficiente para el alcance de la aplicación y deja visible cómo se conecta cada parte.

### ¿Por qué SQLite?

Porque guarda una base relacional en un archivo y no requiere administrar un servidor independiente. Es apropiado para el alcance previsto, aunque tiene limitaciones de concurrencia de escritura que habría que evaluar al aumentar el uso.

### ¿Usas programación orientada a objetos o un ORM?

La lógica de la aplicación está organizada principalmente en funciones y módulos. Se utilizan objetos de Flask y SQLite, pero no un ORM. El SQL está escrito explícitamente en el CRUD.

### ¿Esto es MVC?

Tiene separación de responsabilidades parecida: rutas que coordinan, plantillas que presentan y módulos que trabajan con datos. No lo describiría como una implementación estricta de MVC; `models.py` contiene auxiliares monetarios.

### ¿Dónde se guarda la contraseña?

En `Usuarios.contrasena` se guarda un hash generado por Werkzeug. El login verifica ese hash. Las consultas públicas y las pantallas excluyen la contraseña y su hash.

### ¿Qué evita que un miembro se haga administrador?

Las rutas de usuarios requieren administrador y el rol se obtiene de la cuenta consultada en la base. No se toma como autoridad un rol enviado por el navegador. No hay registro público.

### ¿Qué pasa si alguien cambia el ID de una tarea en la URL?

La ruta consulta el registro y comprueba su asignación. Si existe pero pertenece a otro miembro, devuelve 403; si no existe, devuelve 404.

### ¿Qué diferencia hay entre `None` y una lista vacía?

`None` significa que una consulta individual no encontró el registro. Una lista vacía significa que un listado no encontró coincidencias. No son el mismo contrato de retorno.

### ¿Qué significa `str | None` o `-> int`?

Son anotaciones de tipos. `str | None` permite conceptualmente texto o ausencia de valor; `-> int` indica un retorno entero. Ayudan a entender el código y a las herramientas, pero Python no las convierte automáticamente en validaciones en ejecución.

### ¿Para qué está el `*` en parámetros de algunas funciones?

Los parámetros posteriores al `*` deben enviarse por nombre. Por ejemplo, `prioridad="alta"` y `creador_id=1`. Así se reduce la confusión entre argumentos.

### ¿Qué pasa si dos usuarios intentan usar el mismo correo?

La ruta detecta los duplicados habituales y SQLite tiene una restricción UNIQUE. Si el INSERT o UPDATE incumple esa restricción, se produce `sqlite3.IntegrityError` y se revierte la transacción.

### ¿Se puede eliminar un usuario que tiene pagos?

No. Las relaciones protegen esos registros. Se puede desactivar la cuenta y conservar el historial. Las tareas con pagos tampoco se eliminan.

### ¿Por qué anular un pago en vez de borrarlo?

Para conservar importe, relaciones y fecha de pago. La anulación registra que ese pago dejó de estar vigente sin perder su información.

### ¿Elegir «tarjeta» hace un cobro?

No. Es un dato que describe el método del pago registrado. La aplicación no conecta con un procesador de pagos ni mueve dinero.

### ¿Por qué validar los pagos tanto en la ruta como en el CRUD?

La ruta da mensajes comprensibles al usuario. El CRUD vuelve a comprobar las reglas importantes dentro de la transacción para que la operación use datos vigentes y tenga protección al llamarse desde otro lugar.

### ¿Cómo proteges contra inyección SQL y contra XSS?

Para SQL, los valores externos se pasan como parámetros `?`. Para el HTML, Jinja escapa el contenido de usuarios. Son problemas distintos y requieren protecciones distintas.

### ¿Qué pasa si falta la base de datos?

La conexión normal no crea otra base automáticamente. Falla y las rutas atienden el error de SQLite con una página controlada. La creación de tablas se solicita con `init-db`.

### ¿Importar `run.py` crea tablas?

No. Registra la aplicación y sus rutas, pero la inicialización y las actualizaciones se ejecutan mediante comandos explícitos.

### ¿Qué dependencias utiliza realmente para sesiones y hashes?

Las sesiones se manejan con Flask y los hashes con Werkzeug. Aunque Flask-Login y Flask-Bcrypt están declarados en `requeriments.txt`, estos flujos actuales no los utilizan como mecanismo de autenticación.

### ¿Qué mejorarías después?

El dashboard, los filtros, la paginación y los temas ya están implementados.
Como ampliaciones futuras se podrían evaluar notificaciones o un despliegue
público. No forman parte del alcance educativo entregado.

## 16. Orden recomendado para exponer y demostrar

Para una exposición de unos 10 a 15 minutos:

1. Presentar el problema y los roles de usuario.
2. Explicar el esquema navegador → rutas → validación → CRUD → SQLite.
3. Abrir `run.py` y señalar configuración y registro de rutas.
4. Abrir `routes.py` y explicar una ruta, sus decoradores y el control de sesión.
5. Seguir el ejemplo de creación de tarea hasta `forms.py` y `CRUD.py`.
6. Abrir `database.py` y explicar parámetros, claves foráneas y transacciones.
7. Mostrar `models.py` y justificar el uso de centavos y `Decimal`.
8. Mostrar una plantilla y su herencia de `base.html`.
9. Mostrar dashboard, filtros, simulación educativa y tema oscuro; presentar las pruebas.

Si haces una demostración, usa una base separada con cuentas de prueba. Sigue el
recorrido de [PRESENTACION.md](PRESENTACION.md): crear y asignar una tarea, cambiar
su estado como miembro y simular rechazo, cancelación y aprobación de un pago.

## 17. Cierre para decir en la exposición

«Sala de Tareas integra la gestión de usuarios, tareas y registros de pagos. La parte central del código es el recorrido de cada petición: comprobar al usuario, validar los campos, aplicar las reglas y guardar los datos en una transacción.

El proyecto mantiene una estructura sencilla con Flask y SQLite, protege los permisos
en el servidor y conserva el historial de pagos. El dashboard, los listados filtrados
y la simulación permiten demostrar el recorrido completo. Gracias; puedo mostrar
en el código cómo funciona cualquiera de estos flujos.»

## 18. Repaso rápido antes de entrar

- `run.py` configura; `routes.py` coordina; `forms.py` valida; `CRUD.py` consulta; `database.py` conecta; las plantillas presentan.
- Autenticación: quién eres. Autorización: qué puedes hacer.
- GET muestra; POST cambia datos y exige CSRF.
- `session` conserva información entre peticiones; `g.user` corresponde a la petición actual.
- `usuario_id` de tareas es el asignado; `creador_id` es el autor.
- SQL parametrizado separa instrucciones de valores.
- Dinero: `Decimal` al convertir, `INTEGER` en centavos al guardar.
- `commit` confirma; `rollback` revierte; `close` cierra.
- Los pagos se anulan y se conservan; no hay cobros reales.
- Dashboard, búsqueda, filtros y paginación están implementados.
- PayPal es una simulación local y el tema se recuerda en el navegador.
