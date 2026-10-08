# Plan de trabajo según agents.md — Sala de Tareas

> Documento histórico. Conserva el diagnóstico y la planificación de esa etapa.
> Estado final: [README](../../README.md). Instrucciones: [agents.md](../../agents.md).

Fecha: 4 de octubre de 2026.

Plan basado en el `agents.md` actualizado y en la lectura del código actual. Mantiene **Flask y sqlite3**, consultas parametrizadas y la estructura existente. Este documento actualiza las recomendaciones del plan anterior: no exige una fábrica de aplicación, Blueprints, ORM, nuevas extensiones ni renombrar el archivo de dependencias.

Durante esta revisión no se ejecutó la aplicación ni se abrió la base de datos. Los hallazgos sobre columnas corresponden al código de creación de tablas; el esquema y los datos reales deben comprobarse antes de implementar actualizaciones.

## 1. Qué existe y qué falta

| Parte | Estado observado | Pendiente |
| --- | --- | --- |
| Aplicación Flask | `run.py` crea la aplicación; `/` devuelve `root`. | Conectar rutas, plantillas, sesiones y configuración. |
| Conexiones SQLite | Context manager con commit, rollback, cierre y claves foráneas habilitadas. | Corregir import, unificar ubicación e inicializar explícitamente. |
| Usuarios | Crear, actualizar, eliminar, listar y buscar por correo en `CRUD.py`. | Consulta por ID, validación, hashing, usuario activo, permisos y pantallas. |
| Tareas | Crear, actualizar y eliminar. | Listado, detalle, prioridades, creador, asignación opcional, fecha de actualización y permisos. |
| Pagos | Solo creación con usuario y monto. | Relación con tarea, dinero en centavos, estados, método, fechas, notas y resto del CRUD. |
| Materias y asistencias | Tablas y algunas funciones existentes. | Preservarlas y sus relaciones; no ampliar estos módulos en esta tanda. |
| Autenticación | No implementada. | Login, logout, sesión, roles y alta inicial de administrador. |
| Formularios e interfaz | `forms.py`, `routes.py` e `index.html` vacíos. | Validaciones, CSRF, navegación y pantallas. |
| Pruebas y documentación | No hay pruebas en los archivos revisados; README con solo el título. | Verificar flujos y documentar ejecución y configuración. |

`models.py` y `app/__init__.py` también están vacíos. No hace falta llenarlos para cumplir una arquitectura: utilizarlos únicamente si ayudan al trabajo concreto.

## 2. Problemas inmediatos

1. **Import incorrecto:** `CRUD.py` importa `app.utils.database`, pero el módulo está en `app/utils/data/database.py`.
2. **Ruta de base incoherente:** `DB_PATH` usa `parents[2]`, por lo que apunta a `app/saladetareas.db`; el archivo observado está en la raíz, como `saladetareas.db`. No se encontró una base directamente dentro de `app/`.
3. **Escritura al importar:** `database.py` ejecuta `initialize_database()` automáticamente. Esto podría crear otra base al conectar los módulos.
4. **Contraseñas sin hashing en el CRUD:** las funciones guardan directamente el valor recibido. Falta implementar el procesamiento seguro antes de guardar.
5. **Credenciales incluidas en el listado:** `get_all_users()` usa `SELECT *` y convierte todas las columnas a JSON, incluida `contrasena`. Actualmente no hay una ruta que publique ese resultado, pero debe corregirse antes de conectarlo.
6. **Errores ambiguos:** varias funciones capturan cualquier excepción y devuelven `0` o nada, sin distinguir fallo, registro inexistente y éxito.
7. **Dinero en `REAL`:** el esquema de pagos no sigue la regla de almacenar centavos enteros.

## 3. Etapas de implementación

### Etapa 1 — Conectar la base y Flask correctamente

**Archivos previstos:** `run.py`, `app/routes.py`, `app/utils/data/database.py` y `app/utils/data/CRUD.py`.

- Revisar el esquema de la base existente en modo de solo lectura, sin mostrar credenciales ni datos personales innecesarios.
- Definir una única ruta de base; como opción inicial, conservar el archivo de la raíz después de confirmar que es el correcto.
- Separar la inicialización de tablas de la importación del módulo. Añadir una acción explícita y documentada para inicializar una instalación nueva.
- Corregir el import de la conexión después de retirar la escritura automática.
- Conservar la aplicación global de `run.py`. Registrar las rutas mediante una función sencilla que reciba la aplicación, evitando imports circulares.
- Configurar Flask para encontrar `app/templates`; no mover las plantillas para resolverlo.
- Leer la clave de sesión y la configuración desde variables de entorno. Añadir `.env.example` al implementar esa configuración y hacer que la depuración sea una opción de desarrollo.

**Resultado verificable:** la aplicación muestra una plantilla inicial, usa la base elegida y no crea tablas ni otra base por el simple hecho de importar módulos.

### Etapa 2 — Ordenar el CRUD y preparar cambios de datos

**Archivos previstos:** `app/utils/data/CRUD.py`, `app/utils/data/database.py` y scripts pequeños en `migrations/` cuando sean necesarios.

- Mantener consultas SQL con parámetros `?`.
- Devolver identificadores al crear, datos al consultar y filas afectadas al actualizar o eliminar.
- Mover `jsonify` a las rutas, si alguna ruta necesita JSON. Para páginas HTML, pasar los datos a Jinja2.
- Excluir contraseñas y hashes de los listados; limitar su consulta al flujo de autenticación.
- Manejar errores de integridad y registros inexistentes de forma diferenciada. Conservar rollback y registrar errores inesperados sin exponer datos sensibles.
- Completar consultas por ID y listados según se implemente cada módulo.
- Preparar actualizaciones de esquema explícitas e incrementales, conservando claves, relaciones y datos. No usar `CREATE TABLE IF NOT EXISTS` como mecanismo de actualización.

**Resultado verificable:** los resultados son claros y las rutas pueden distinguir éxito, datos inválidos y registros inexistentes.

### Etapa 3 — Usuarios, acceso y protección de formularios

**Archivos previstos:** `app/routes.py`, `app/forms.py`, `app/utils/data/CRUD.py`, `database.py` y plantillas de acceso y usuarios.

- Añadir un indicador de usuario activo, con valores `0` y `1`, mediante actualización explícita del esquema.
- Hashear nuevas contraseñas con Werkzeug y verificarlas con `check_password_hash`. Revisar el formato de las credenciales existentes antes de convertirlas; no hashear indiscriminadamente posibles hashes previos.
- Implementar login y logout con la sesión de Flask. Guardar un identificador de usuario y comprobar en el servidor que la cuenta continúa activa y tiene permisos.
- Definir un procedimiento explícito para crear el primer administrador, sin contraseña fija en el código.
- Mantener inicialmente el alta de cuentas a cargo del administrador. Si se habilita registro público, solo crear cuentas `member`.
- Centralizar autenticación, comprobación de roles y CSRF. Usar un token generado con `secrets`, almacenado en sesión y validado con comparación segura en cada POST.
- Completar listado, detalle, creación, edición y eliminación/desactivación de usuarios. Solo administradores pueden modificar cuentas.
- Validar nombre, correo único, teléfono opcional, rol y contraseña en el servidor. Al editar, permitir conservar la contraseña si no se solicita cambiarla.
- Bloquear eliminaciones que afecten pagos o relaciones existentes y mostrar un mensaje claro; ofrecer desactivación cuando corresponda.

**Resultado verificable:** un administrador gestiona cuentas; un miembro no puede hacerlo cambiando una URL o enviando un formulario manualmente. Los datos públicos no contienen credenciales.

### Etapa 4 — Tareas completas y permisos por registro

**Archivos previstos:** módulos actuales de rutas, validación y datos; plantillas de tareas; script de actualización del esquema.

- Aclarar qué representa el actual `usuario_id` antes de separar creador y usuario asignado.
- Añadir prioridad, creador y fecha de actualización; permitir una asignación opcional según el objetivo de `agents.md`.
- Preservar `materia_id`, la tabla Materias y los identificadores existentes.
- No atribuir tareas históricas a un creador inventado. Preparar una revisión de los registros que necesiten completar información.
- Implementar listado, detalle, creación, edición y eliminación con las rutas indicadas en `agents.md`.
- Administradores crean, asignan, editan y eliminan. Miembros solo ven sus tareas asignadas y cambian su estado.
- Validar estados, prioridades, título, fechas y relaciones. No aceptar cambios de asignación o autoría enviados por un miembro.
- Actualizar la fecha de modificación al cambiar la tarea y bloquear su eliminación si tiene pagos asociados.

**Resultado verificable:** se puede asignar una tarea y actualizar su estado; un miembro no puede consultar ni modificar tareas ajenas.

### Etapa 5 — Pagos asociados a tareas

**Archivos previstos:** módulos actuales de rutas, validación y datos; plantillas de pagos; script de actualización del esquema.

- Definir la moneda y convertir entradas con `Decimal`, aceptando como máximo dos decimales y un monto mayor que cero.
- Preparar la conversión de `monto REAL` a centavos enteros con respaldo y regla de redondeo documentada. Comparar importes antes y después; no interpretar los valores actuales como centavos.
- Añadir tarea, estado, método, fecha de pago y notas, preservando usuario y fecha de creación existentes.
- Los pagos históricos sin tarea requieren conciliación explícita. Conservarlos y señalarlos como pendientes de completar; no asignar tareas arbitrarias.
- Completar crear, listar, ver detalle, editar y eliminar/anular. Restringir el módulo inicialmente a administradores.
- Rechazar pagos para tareas inexistentes o canceladas y para usuarios inactivos.
- Registrar automáticamente la fecha al pasar a `pagado`; definir cómo se conserva el historial si se corrige o anula un pago.
- Preferir anulación para registros de pago que deben conservarse y evitar cualquier borrado en cascada.

**Resultado verificable:** los importes se guardan exactamente en centavos, cada nuevo pago referencia una tarea válida y las operaciones respetan sus reglas.

### Etapa 6 — Interfaz, dashboard y listados útiles

- Crear `base.html` con navegación, mensajes `flash` y formularios con CSRF.
- Construir pantallas sencillas para usuarios, tareas y pagos, en español y utilizables desde móvil.
- Mostrar errores junto a los campos, mensajes sin datos y confirmaciones para acciones de eliminación o anulación.
- Sustituir `root` por un dashboard con tareas por estado, próximas a vencer y totales de pagos pendientes y pagados.
- Limitar el dashboard de miembros a sus tareas; reservar los resúmenes financieros para administradores.
- Añadir búsqueda, filtros y paginación después de completar los CRUD. Parametrizar los valores y permitir ordenación solo por columnas autorizadas.

**Resultado verificable:** los flujos completos se pueden usar desde el navegador y los resúmenes respetan los permisos.

### Etapa 7 — Pruebas y documentación

- Añadir pruebas con `unittest` y el cliente Flask, sin exigir nuevas dependencias.
- Usar una base temporal independiente de `saladetareas.db`. Si se usa `:memory:`, conservar la conexión necesaria entre operaciones.
- Probar los CRUD conforme se implementen: éxito, datos inválidos, registros inexistentes y permisos insuficientes.
- Cubrir correo duplicado, hashing, ausencia de credenciales en listados, usuario inactivo, CSRF ausente/incorrecto, claves foráneas y rollback.
- Probar dinero con decimales, tareas canceladas, fecha de pago y bloqueo de eliminaciones con pagos asociados.
- Verificar los scripts de actualización sobre una copia, comprobando conservación de registros, importes y relaciones.
- Completar README con activación del entorno en PowerShell, `requeriments.txt`, variables de entorno, inicialización, actualizaciones, ejecución y pruebas.
- Documentar respaldos y ejecución de producción con depuración desactivada.

**Resultado verificable:** otra persona puede arrancar y usar el proyecto siguiendo el README; las pruebas comprueban sus reglas principales.

## 4. Primera tanda recomendada

- [ ] Confirmar el esquema y la ubicación de la base existente en modo de solo lectura.
- [ ] Retirar la inicialización automática al importar y corregir el import del CRUD.
- [ ] Conectar rutas y plantillas con `run.py` conservando la estructura.
- [ ] Normalizar retornos y errores del CRUD; excluir credenciales de listados.
- [ ] Preparar configuración de sesiones y validación CSRF.
- [ ] Implementar acceso y el CRUD de usuarios con hashing y permisos.
- [ ] Comprobar ese primer flujo antes de continuar con tareas y pagos.

## 5. Límites de este plan

Conservar Flask, sqlite3, nombres de tablas y estructura actual. No añadir ORM, Alembic, Blueprints obligatorios ni capas vacías. No eliminar materias, asistencias, dependencias o datos existentes. Revisar cualquier modificación de esquema sobre una copia antes de aplicarla a la base de uso.

La implementación queda pendiente: esta tarea crea únicamente este documento y conserva el plan anterior como referencia histórica.
