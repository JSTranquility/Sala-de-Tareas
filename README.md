# Sala de Tareas

Aplicación con Flask y SQLite mediante `sqlite3`. Incluye inicio y cierre de
sesión, gestión de usuarios para administradores y desactivación de cuentas.
La gestión de tareas y pagos sigue pendiente.

## Preparación (PowerShell)

Desde la raíz del proyecto, activar el entorno existente o crearlo si hace falta:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requeriments.txt
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
```

La clave es obligatoria para las pantallas de acceso. Conservar una clave estable
entre ejecuciones; cambiarla invalida todas las sesiones.
`.env.example` documenta las variables; no se carga automáticamente.

## Base de datos

La ubicación predeterminada es `saladetareas.db` en la raíz del proyecto. Para
elegir otra ubicación, asignar `DATABASE_PATH` antes de ejecutar Flask; las rutas
relativas se resuelven desde la raíz del proyecto, no desde el directorio de la
terminal. El directorio padre debe existir.

Solo para inicializar una instalación nueva, ejecutar explícitamente:

```powershell
python -m flask --app run init-db
```

También está disponible `python -m app.utils.data.database`. Ambos comandos crean
las tablas faltantes; no actualizan tablas existentes ni borran registros. La
base existente no requiere reinicialización. Importar módulos, arrancar Flask o
consultar la portada no crea bases ni tablas. Una conexión normal exige que el
archivo exista y falla si falta, para evitar crear una base vacía accidentalmente.

## Ejecución

Antes del primer acceso, actualizar una base de una versión anterior y crear el
primer administrador. La actualización conserva registros y contraseñas y crea
un respaldo junto al archivo original. Una base nueva creada con `init-db` ya
incluye el campo `activo` y no necesita actualización.

```powershell
python -m flask --app run migrate-users
python -m flask --app run create-admin
```

`create-admin` pide nombre, correo y una contraseña de entre 8 y 128 caracteres,
con confirmación y sin mostrarla. No crea otro administrador si ya hay uno activo,
ni promueve una cuenta existente. Los siguientes usuarios se crean desde la
pantalla Usuarios, usando la cuenta administradora. No hay registro público.

```powershell
python run.py
```

Abrir `http://127.0.0.1:5000/`. La depuración está desactivada por defecto; para
desarrollo se puede asignar `$env:FLASK_DEBUG = "1"` antes de arrancar. En
producción, mantener `FLASK_DEBUG=0`, usar un servidor adecuado y activar
`SESSION_COOKIE_SECURE=1` cuando se sirva por HTTPS.

La portada requiere una cuenta activa y redirige a `/auth/login` sin sesión.
Usuarios permite listar, consultar, crear, editar, eliminar y desactivar cuentas.
Solo administradores acceden a estas pantallas. Una cuenta con tareas, pagos o
asistencias asociados no se elimina: se puede desactivar desde Editar. El usuario
administrador no puede eliminarse, desactivarse ni quitarse su propio rol desde
la interfaz. Al desactivar una cuenta, su sesión se rechaza en la siguiente petición.

Para restablecer explícitamente una contraseña histórica o recuperar una cuenta:

```powershell
python -m flask --app run reset-password --email persona@example.com
```

El comando pide una nueva contraseña sin mostrarla, guarda su hash y conserva
el rol y estado de la cuenta. El login no acepta contraseñas en texto plano ni
convierte datos históricos automáticamente. Estos comandos están destinados a
la persona que administra el servidor.

La validación de formularios se realiza en el servidor. Todos los POST, incluido
login y logout, requieren el token CSRF de la sesión. Logout y eliminación por
GET se rechazan. Contraseñas y hashes no se incluyen en las pantallas de usuarios.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

Las pruebas usan bases temporales y no modifican `saladetareas.db`.

## Contratos del CRUD

`app/utils/data/CRUD.py` devuelve datos de Python, sin `jsonify` ni respuestas HTTP:

- Crear devuelve el identificador del registro.
- Actualizar o eliminar devuelve las filas afectadas: `1` si existe, `0` si no.
- Consultar por ID o correo devuelve un diccionario o `None`.
- Los listados devuelven listas de diccionarios, vacías cuando no hay resultados.
- Las consultas públicas de usuarios excluyen `contrasena`. Solo
  `get_user_for_auth_by_email()` la incluye para verificar credenciales; su
  resultado no debe enviarse a plantillas ni a respuestas JSON.
- Crear usuarios o cambiar su contraseña guarda un hash de Werkzeug.
  `update_user(..., contrasena=None, ...)` conserva la contraseña actual.

Las restricciones incumplidas propagan `sqlite3.IntegrityError`; los fallos de
acceso u operaciones SQL propagan el error correspondiente, como
`sqlite3.OperationalError`. Las transacciones fallidas se revierten. Los fallos
SQLite inesperados se registran sin incluir valores de entrada ni credenciales.
Las rutas deben convertir estos resultados y errores en mensajes
comprensibles y aplicar validación, autenticación y permisos antes de operar.

Los campos y montos de pagos mantienen el esquema heredado: `monto` aún representa
unidades monetarias en una columna `REAL`. La función existente `create_payment`
se conserva sin publicarla mediante una ruta; no recibe centavos. La conversión
a enteros, relación con tareas y reglas completas se implementarán en la etapa 5.
No se convierten las contraseñas históricas en esta etapa.

## Próximos cambios de esquema

La etapa de acceso añade `Usuarios.activo` como entero con valores 0 o 1 mediante
`migrations/add_user_active.py`, ejecutado explícitamente por `migrate-users`.
Se puede ejecutar directamente con:

```powershell
python migrations/add_user_active.py saladetareas.db
```

El script usa la API de respaldo de SQLite, comprueba integridad y relaciones y
aplica el cambio en una transacción. Repetirlo no cambia una base que ya tiene
la columna. Los respaldos contienen datos sensibles y deben conservarse fuera
de Git y con acceso restringido, igual que la base de uso.

Para futuros campos de tareas o pagos, preparar otro script explícito:

1. Revisar el esquema y hacer una copia de respaldo de la base con la aplicación
   detenida o mediante la API de respaldo de SQLite.
2. Probar el script sobre una copia, conservando identificadores y relaciones.
3. Ejecutarlo dentro de una transacción y verificar registros, claves foráneas
   e importes antes de dar la actualización por terminada.
4. Documentar el comando y la versión de esquema que admite. Nunca actualizar
   tablas al importar módulos ni inventar relaciones para registros históricos.

`init-db` solo crea tablas faltantes; no reemplaza este procedimiento.
