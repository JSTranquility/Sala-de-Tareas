# Instalación y uso — Sala de Tareas

Guía detallada. Volver al [README principal](../README.md) o al
[índice de documentación](README.md). Ejecutar los comandos desde la raíz del proyecto.

Aplicación con Flask y SQLite mediante `sqlite3`. Incluye inicio y cierre de
sesión, gestión de usuarios para administradores, desactivación de cuentas y
gestión de tareas con permisos por registro y pagos asociados a tareas en USD o DOP.

Etapas 1 a 7 completadas para el alcance educativo: CRUD, permisos, simulación
local de PayPal, dashboard, filtros, paginación y verificación funcional final.
La interfaz usa una navegación lateral, tonos marfil y verde, tarjetas de resumen
y etiquetas de estado. Se adapta a móvil y funciona con CSS e iconos locales.
El botón de tema del encabezado alterna entre modo claro y oscuro y recuerda la
elección en el navegador. Sin elección previa, sigue el tema del sistema.

### Inicio rápido: instalación nueva

Desde la carpeta del proyecto, en PowerShell, solo si todavía no hay entorno,
base ni administrador preparados:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requeriments.txt
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
python -m flask --app run init-db
python -m flask --app run create-admin
python run.py
```

Abrir `http://127.0.0.1:5000/` e iniciar sesión con el administrador creado.
Para una instalación existente, usar los comandos de la sección 4; para una
base antigua, aplicar únicamente las actualizaciones de la sección 2.
Los archivos [EJECUTAR.md](EJECUTAR.md) y [PRUEBAS.md](PRUEBAS.md) contienen los
comandos rápidos. El guion para exponer está en [PRESENTACION.md](PRESENTACION.md).

## 1. Preparar el entorno

Requisito: Python 3.11 o superior. Desde la raíz del proyecto, crear el entorno solo si todavía no existe:

```powershell
python -m venv .venv
```

Activar el entorno, instalar las dependencias y configurar la clave de sesión:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requeriments.txt
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
```

La clave es obligatoria para las pantallas de acceso. Conservar una clave estable
entre ejecuciones; cambiarla invalida todas las sesiones.
`.env.example` documenta las variables; no se carga automáticamente.

## 2. Preparar la base de datos

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

### Si la base es de una versión anterior

Detener la aplicación y ejecutar las actualizaciones en este orden. Una base nueva creada con `init-db` ya incluye el esquema actual y no necesita estos comandos.

```powershell
python -m flask --app run migrate-users
python -m flask --app run migrate-tasks
python -m flask --app run migrate-payments
```

Los comandos conservan los datos y crean un respaldo cuando actualizan el esquema. Repetirlos sobre una base actualizada no modifica los registros. No se ejecutan automáticamente al arrancar.

## 3. Crear el primer administrador

Después de preparar la base, crear el primer administrador si todavía no hay uno activo:

```powershell
python -m flask --app run create-admin
```

El comando pide nombre, correo y una contraseña de entre 8 y 128 caracteres,
con confirmación y sin mostrarla. No crea otro administrador si ya hay uno activo,
ni promueve una cuenta existente. Los siguientes usuarios se crean desde la
pantalla **Usuarios**, usando la cuenta administradora. No hay registro público.

## 4. Ejecutar la aplicación

Para arrancar una instalación ya preparada, abrir PowerShell en la carpeta del
proyecto y ejecutar:

```powershell
.\.venv\Scripts\Activate.ps1
$env:SECRET_KEY = "tu-clave-secreta-configurada"
$env:FLASK_DEBUG = "0"
$env:SESSION_COOKIE_SECURE = "0"
python run.py
```

Sustituir `tu-clave-secreta-configurada` por la clave generada durante la
preparación y conservarla entre ejecuciones. Asignarla de nuevo si se abre otra
terminal. No es necesario reinstalar dependencias, inicializar la base ni crear
otro administrador en cada arranque. Si se utiliza una base en otra ubicación,
asignar también `$env:DATABASE_PATH` antes de ejecutar `python run.py`.

Mantener la terminal abierta mientras se usa la aplicación. Para detener el
servidor, presionar `Ctrl+C`.

Abrir `http://127.0.0.1:5000/`. La depuración está desactivada por defecto; para
desarrollo se puede asignar `$env:FLASK_DEBUG = "1"` antes de arrancar. En
producción, mantener `FLASK_DEBUG=0`, usar un servidor adecuado y activar
`SESSION_COOKIE_SECURE=1` cuando se sirva por HTTPS.

## 5. Usuarios y acceso

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

## 6. Tareas

Después de iniciar sesión, abrir **Tareas** en la navegación; los miembros ven
**Mis tareas**. También se puede acceder a `http://127.0.0.1:5000/tasks/`.

- Administradores: listar todas las tareas, crear, consultar detalle, editar,
  asignar y eliminar. La asignación y la materia son opcionales; solo se permite
  asignar usuarios activos. Desde **Materias** (`/subjects/`) se pueden crear,
  listar, consultar, editar y eliminar materias sin tareas asociadas. Después
  aparecen en el selector al crear o editar tareas. Nombre obligatorio de hasta
  120 caracteres y descripción opcional de hasta 2000; gestión solo para admin.
  Abre el detalle de una tarea desde su título, **Ver detalle** o la fila.
- Miembros: listar y consultar únicamente sus tareas asignadas y cambiar su
  estado. No pueden crear, eliminar ni modificar el título, prioridad,
  vencimiento, materia, asignación o autoría, aunque envíen campos manualmente.
- Estados: pendiente, en progreso, completada y cancelada. Prioridades: baja,
  media y alta. Se valida el título (1–200 caracteres), la descripción (hasta
  5000), las fechas, los estados, las prioridades y las relaciones en el servidor.
- El creador se registra automáticamente con la cuenta administradora al crear
  y se conserva al editar. Las tareas sin asignar solo son visibles para
  administradores. Si un usuario asignado se desactiva, conserva sus tareas,
  pierde el acceso y el administrador debe reasignar o dejar sin asignar la tarea
  para guardar una edición.
- Eliminar requiere POST y CSRF. La pantalla pide confirmación; el servidor
  bloquea la eliminación si existen registros asociados, incluidos pagos cuando
  su esquema incorpore `tarea_id`. Los pagos heredados no tienen esa relación y
  no se vinculan a tareas a partir de su usuario receptor.

**Usuario asignado** es la persona responsable de realizar la tarea. En SQLite,
la columna histórica `Tareas.usuario_id` conserva su nombre y representa esta
asignación; nunca representa al creador. Los formularios usan
`usuario_asignado_id` para que su significado sea claro. **Creado por** usa la
columna independiente `Tareas.creador_id`.

Las nuevas fechas de creación y actualización se guardan en ISO 8601 con zona
UTC (`+00:00`); la fecha de actualización cambia al editar o cambiar el estado.
El vencimiento se introduce y guarda como fecha `AAAA-MM-DD`, sin hora. Las
fechas históricas se conservan al migrar; los valores generados anteriormente
por SQLite con `CURRENT_TIMESTAMP` están en UTC. Al editar una tarea con un
vencimiento histórico con hora, el formulario utiliza solo su fecha.

## 7. Pagos

Después de iniciar sesión como administrador, abrir **Pagos** o visitar
`http://127.0.0.1:5000/payments/`. Los miembros no pueden consultar ni modificar
pagos, incluso mediante una URL o formulario enviado manualmente.

1. Usar **Registrar pago**, seleccionar una tarea y un usuario receptor activo.
   El receptor se elige explícitamente; no se supone que sea el asignado de la tarea.
2. Introducir un monto mayor que cero con hasta dos decimales y punto decimal,
   por ejemplo `125.50`. Elegir **USD** o **pesos dominicanos (DOP)**, un método
   (efectivo, transferencia, tarjeta u otro), estado y notas opcionales.
3. Guardar como **Pendiente** o **Pagado**. Al marcar pagado se registra la fecha
   actual en UTC automáticamente; el navegador no decide esa fecha.
4. Un pago pendiente permite editar datos. Uno pagado conserva importe, moneda,
   tarea, receptor, método y fecha de pago; solo admite corregir notas o anular.
5. Desde el detalle, **Anular pago** conserva el registro y su fecha de pago.
   Un pago anulado no se puede editar ni reactivar. No hay borrado físico ni cascadas.

No se admiten nuevos pagos ni ediciones de datos sobre tareas canceladas o
receptores inactivos. Sí se permite anular esos pagos y corregir notas de uno
ya pagado. Usuarios y tareas con pagos asociados no se pueden eliminar, incluso
si los pagos fueron anulados; se pueden desactivar usuarios o cancelar tareas.

Cada pago conserva su moneda y se muestra como `USD 12.50` o `DOP 12.50`. No hay
conversión automática de moneda ni suma de monedas distintas. La aplicación
registra pagos; no realiza cobros, transferencias ni integra pasarelas de pago.

Los registros históricos aparecen con **Información histórica pendiente** hasta
identificar tarea, moneda, estado y método, y revisar cualquier monto no positivo.
En **Editar pago**, completar esos datos con información real. No se inventan
asociaciones, monedas ni fechas de pago. Si se marca un histórico como pagado,
se registra la fecha de esta acción, no una supuesta fecha histórica. También
se puede anular un histórico incompleto para conservarlo sin activarlo.

### Simulación educativa de PayPal

Desde el detalle de un pago pendiente y completo, un administrador puede pulsar
**Simular pago con PayPal**. Todo ocurre localmente: no necesita internet, cuenta
PayPal, credenciales, Sandbox ni dependencias adicionales. No se mueve dinero.

Para mostrarlo en clase, usar una base de práctica separada: configurar
`DATABASE_PATH` con una ruta nueva, inicializarla explícitamente con `init-db` y
crear el administrador con `create-admin` como se explica arriba. Crear un usuario
activo, una tarea y un pago pendiente con método **Otro**, moneda USD o DOP y notas
«Ejercicio educativo». Abrir el detalle y entrar en la simulación.

- **Rechazar** o **Cancelar** muestra un mensaje y conserva el pago pendiente.
- **Aprobar** guarda `pagado`, fecha de pago UTC y una nota con referencia ficticia
  `SIM-PAGO-<id>` y el aviso de que no hubo cobro real. Conserva las notas anteriores,
  el importe, la moneda, el método, el receptor y el estado de la tarea.
- Una segunda aprobación se rechaza y conserva la fecha original. No se permite
  simular pagos anulados, incompletos, de tareas canceladas o receptores inactivos.

Probar primero rechazo y cancelación, y después aprobación; crear otro pago para
repetir el ejercicio. Si las notas no tienen espacio para el aviso educativo
(límite de 2000 caracteres), acortarlas antes de aprobar. Los miembros no pueden
usar esta función y todos los formularios mantienen la protección CSRF existente.
No hay cambios de esquema ni migraciones nuevas para esta simulación.

### Dashboard, búsqueda, filtros y paginación (etapa 6)

La pantalla **Inicio** muestra tareas por estado, vencidas y próximas a vencer.
Los miembros solo ven sus tareas asignadas; los administradores ven todas.
Vencida significa fecha anterior a hoy; próxima significa desde hoy hasta dentro
de 3 días, inclusive. Se usa la fecha UTC y solo cuentan tareas pendientes o en
progreso; sin vencimiento no cuenta en ninguno de esos dos grupos.

Solo administradores ven el resumen monetario: cantidad e importe de pagos
pendientes y pagados por separado para USD y DOP. Se excluyen pagos anulados o
con datos incompletos; los históricos incompletos aparecen en un aviso. Los pagos
simulados sí cuentan como registros pagados, sin representar cobros bancarios.

Los listados muestran 10 registros por página y mantienen los filtros al pulsar
**Anterior** o **Siguiente**. **Limpiar** restablece el listado. Se puede combinar:

- Tareas: buscar título, descripción o nombre asignado; filtrar estado y prioridad.
- Usuarios (admin): buscar nombre o correo; filtrar rol y activo/inactivo.
- Pagos (admin): buscar tarea, receptor o notas; filtrar estado, moneda y método.

La búsqueda es de texto literal (incluyendo `%` y `_`), hasta 100 caracteres.
SQLite ignora mayúsculas/minúsculas de letras ASCII; los acentos deben coincidir.
Los filtros o páginas inválidos se rechazan; una página superior a la última se
ajusta a la última disponible. Las consultas no exponen contraseñas ni hashes.
Esta etapa no añade dependencias, tablas ni migraciones.

## 8. Ejecutar las pruebas

```powershell
python -m unittest discover -s tests -v
```

Las pruebas usan bases temporales y no modifican `saladetareas.db`.
Incluyen el CRUD de tareas, permisos por registro, campos manipulados, CSRF,
validaciones, relaciones, bloqueo de eliminación con pagos y migración con
respaldo, conservación de datos e idempotencia.
También comprueban pagos en ambas monedas, conversión exacta a centavos,
validaciones, fechas automáticas, permisos, anulaciones y conservación del historial.
Cubren además dashboard, búsquedas combinadas, paginación, privacidad por usuario
y los resultados de la simulación de PayPal.

Para ejecutar solo los recorridos completos de la etapa 7:

```powershell
python -m unittest discover -s tests -p "test_final_flows.py" -v
```

Estos recorridos inicializan una base temporal, crean el primer administrador
mediante el comando real, inician sesión con formularios y comprueban creación,
edición, consulta y eliminación de registros sin relaciones. También verifican
simulación aprobada/rechazada/cancelada, cambio de estado como miembro, protección
de usuarios y tareas con pagos, desactivación, logout y enlaces de navegación.
No requieren credenciales reales, una base del usuario ni conexión a PayPal.

## 9. Cómo leer el código

Para entender el proyecto, revisar estos archivos en este orden:

1. `run.py` crea la aplicación, lee la configuración del entorno y registra
   las rutas.
2. `app/routes.py` recibe las peticiones del navegador. Está organizado en acceso,
   usuarios, tareas, pagos y comandos de terminal. GET muestra páginas; POST valida y
   guarda los cambios.
3. `app/forms.py` comprueba los campos de los formularios. Devuelve `values`
   (los valores recibidos) y `errors` (los mensajes por campo).
4. `app/utils/data/CRUD.py` consulta o modifica los registros con SQL. Devuelve
   datos e identificadores para que las rutas construyan las respuestas.
5. `app/utils/data/database.py` decide qué base usar y gestiona las conexiones.
   `with get_connection()` guarda la operación si sale bien, la revierte si falla
   y cierra la conexión al terminar.
6. `app/templates/` contiene el HTML con Jinja. `base.html` comparte el estilo,
   la navegación y los mensajes; cada pantalla añade su contenido.
7. `app/models.py` contiene la conversión de montos con `Decimal` y las opciones
   de monedas y métodos; no contiene un ORM.
8. `app/static/styles.css` comparte el diseño y sus reglas para móvil;
   `app/templates/ui.html` contiene los iconos SVG y etiquetas de estado.
   `run.py` configura explícitamente esta carpeta estática. No hay CDN ni fuentes
   externas. Para ver los estilos nuevos tras actualizar, recargar con `Ctrl+F5`.

Por ejemplo, al crear una tarea, `task_create()` comprueba que la cuenta sea
administradora y llama a `save_task()`. Esta función valida el formulario y sus
relaciones, llama a `crud.create_task()` y redirige al detalle si pudo guardarla.
Los argumentos se escriben con su nombre, como `usuario_id=assigned_user_id`,
para distinguir la persona asignada del creador.

Las comprobaciones generales se ejecutan antes de cada ruta: el usuario de la
petición se guarda en `g.user` y el token CSRF se compara con el de la sesión.
La [guía de decoradores](GUIA_DECORADORES_ROUTES.md) explica los `@` usados
para registrar rutas y comprobar permisos.

Los scripts de `migrations/` actualizan esquemas antiguos únicamente al ejecutar
sus comandos. `tests/` comprueba los flujos sobre bases temporales. El proyecto
incluye las siete etapas dentro del alcance educativo, con la verificación final
de recorridos en `tests/test_final_flows.py`.

## 10. Contratos del CRUD

`app/utils/data/CRUD.py` devuelve datos de Python, sin `jsonify` ni respuestas HTTP:

- Crear devuelve el identificador del registro.
- Actualizar o eliminar devuelve las filas afectadas: `1` si existe, `0` si no.
- Consultar por ID o correo devuelve un diccionario o `None`.
- Los listados devuelven listas de diccionarios, vacías cuando no hay resultados.
- `get_filtered_page()` devuelve los registros de la página y sus metadatos:
  `items`, `total`, `page` y `pages`; `get_dashboard()` devuelve el resumen.
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

Desde la etapa 5, `Pagos.monto` es un `INTEGER` en centavos. La función
`create_payment(usuario_id, monto_centavos, tarea_id, moneda, metodo, ...)`
requiere centavos enteros y valida relaciones dentro de una transacción.
`update_payment` permite editar pendientes o completar históricos;
`update_payment_notes` corrige notas de pagados y `annul_payment` conserva el
registro al anular. La ruta POST `/payments/<id>/delete` llama a esta anulación.
Un importe `12.50` se convierte a `1250` mediante `Decimal`; no se usa `float`
para importes nuevos. Las reglas de negocio inválidas producen `ValueError` y
las restricciones de SQLite producen `sqlite3.IntegrityError`.

## 11. Actualizaciones de esquema

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

La etapa 4 usa `migrations/add_task_fields.py`. Además del comando Flask, puede
ejecutarse desde la raíz del proyecto con:

```powershell
python -m migrations.add_task_fields saladetareas.db
```

La actualización admite el esquema heredado de Tareas y conserva las columnas
en español. Para permitir una asignación vacía, SQLite requiere sustituir la
tabla que tenía `usuario_id NOT NULL`: el script hace una copia dentro de una
transacción, comprueba cada registro antes de sustituirla y conserva la secuencia
de identificadores, incluso si se habían eliminado tareas. No toca usuarios,
materias, pagos ni asistencias. Guarda una copia completa de la base con la API
de respaldo de SQLite mientras bloquea otras escrituras, y verifica integridad
y claves foráneas. Si falla una operación, revierte la transacción.

En tareas históricas, `prioridad`, `creador_id` y `fecha_actualizacion` quedan en
`NULL`: no se inventan prioridades, autores ni fechas. La interfaz muestra
“Sin especificar” y “No consta (tarea histórica)”; `migrate-tasks` lista los IDs
con autor o prioridad pendientes. Al editar, el administrador elige una prioridad
y se registra la fecha real de actualización, conservando el creador desconocido.
El script rechaza estados históricos inválidos, columnas inesperadas, índices o
triggers adicionales y tablas que referencien Tareas; esos casos necesitan
revisión específica antes de actualizar.

La etapa 5 usa `migrations/add_payment_fields.py`, mediante `migrate-payments` o:

```powershell
python -m migrations.add_payment_fields saladetareas.db
```

El script admite el esquema heredado `id, usuario_id, monto REAL, fecha`. Conserva
IDs, receptor, fecha original y secuencia de identificadores. SQLite requiere
sustituir la tabla para cambiar `REAL` a `INTEGER`: se verifica cada registro
convertido antes del reemplazo y toda la actualización es transaccional. No se
modifican usuarios, tareas, materias ni asistencias. Se comprueban integridad y
claves foráneas, y se rechazan esquemas personalizados que requieran revisión.

La regla de conversión es `Decimal(str(monto)) * 100`, redondeada a entero con
`ROUND_HALF_UP`: por ejemplo `12.345` se convierte a `1235`, no a `12`. La copia
de respaldo conserva el valor SQLite original y `monto_original` conserva su
representación textual en unidades monetarias. Los importes históricos cero o
negativos se conservan y requieren revisión antes de completar el pago. Los
valores no numéricos, no finitos o fuera del rango de SQLite detienen la migración.

Los históricos quedan con tarea, moneda, estado, método y fecha de pago en `NULL`.
`fecha` se conserva y se copia a `fecha_creacion` como fecha del registro, sin
interpretarla como fecha de pago. `migrate-payments` lista los IDs pendientes de
completar. No hay moneda predeterminada para datos históricos ni conversión entre
USD y DOP. Los pagos nuevos guardan creación y pago en ISO 8601 con zona UTC.

Para futuros campos de tareas o pagos, preparar otro script explícito:

1. Revisar el esquema y hacer una copia de respaldo de la base con la aplicación
   detenida o mediante la API de respaldo de SQLite.
2. Probar el script sobre una copia, conservando identificadores y relaciones.
3. Ejecutarlo dentro de una transacción y verificar registros, claves foráneas
   e importes antes de dar la actualización por terminada.
4. Documentar el comando y la versión de esquema que admite. Nunca actualizar
   tablas al importar módulos ni inventar relaciones para registros históricos.

`init-db` solo crea tablas faltantes; no reemplaza este procedimiento.

## 12. Archivos locales y Git

El `.gitignore` permite incluir el README y las guías de `docs/` en Git. Las bases
SQLite, respaldos, entornos virtuales, cachés, secretos y capturas locales siguen
excluidos. `agents.md` permanece en la raíz como instrucciones para agentes.
La base y sus respaldos no se desplazan al organizar la documentación.
Después de clonar, preparar el entorno y crear una base nueva y el primer
administrador con los comandos explícitos de esta guía.

## 13. Uso rápido y problemas habituales

Como administrador: crear un miembro en **Usuarios**, asignarle una tarea en
**Tareas** y registrar un pago en **Pagos**. Para la demostración, dejarlo pendiente,
abrir su detalle y probar rechazar, cancelar y finalmente aprobar la simulación.
Como miembro: iniciar sesión con su cuenta, consultar **Mis tareas** y cambiar
su estado. El dashboard y los listados reflejan los cambios al volver a abrirlos.

| Problema | Qué hacer |
| --- | --- |
| «El acceso no está configurado» | Asignar `SECRET_KEY` en la terminal antes de arrancar. |
| «No se pudo acceder a los datos» | Comprobar `DATABASE_PATH`. Inicializar solo una base nueva; actualizar explícitamente una antigua. |
| Correo o contraseña rechazados | Comprobar cuenta activa; usar `reset-password` para restablecer la clave. |
| Formulario vencido o inválido | Recargar la página y enviar de nuevo; cambiar `SECRET_KEY` invalida las sesiones. |
| No permite eliminar usuario o tarea | Conservar los registros asociados; desactivar el usuario o cancelar la tarea. |
| El entorno no activa en PowerShell | Usar directamente `.\.venv\Scripts\python.exe` en lugar de `python` en los comandos. |
| Puerto 5000 ocupado | Detener la instancia anterior con `Ctrl+C` o usar `python -m flask --app run run --port 5001`. |

`python run.py` sirve para la demostración local. La simulación nunca mueve dinero;
los registros marcados como pagados son datos del ejercicio, no comprobantes de
PayPal. Las pruebas automatizadas validan funcionamiento mediante el cliente de
Flask. La revisión visual local utiliza datos ficticios y capturas de escritorio
y móvil; no equivale a una verificación de un despliegue público.
