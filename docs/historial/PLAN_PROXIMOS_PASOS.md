# Plan de próximos pasos — Sala de Tareas

> Documento histórico. Las propuestas corresponden al inicio del proyecto;
> consultar el [README actual](../../README.md) para las funciones terminadas.

Fecha de revisión: 4 de octubre de 2026.

Este documento se basa en la lectura del código disponible. No se ejecutó la aplicación, no se instalaron dependencias y no se modificó ningún archivo existente. Las acciones siguientes son propuestas pendientes de implementación.

## 1. Estado actual

- `run.py` crea una aplicación Flask y expone únicamente `/`, que devuelve el texto `root`. El modo de depuración está habilitado al ejecutar este archivo directamente.
- `app/__init__.py`, `app/routes.py`, `app/models.py`, `app/forms.py` y `app/templates/index.html` están vacíos.
- `app/utils/data/database.py` define las tablas Usuarios, Materias, Tareas, Pagos y Asistencias. Gestiona conexiones con commit, rollback y claves foráneas habilitadas.
- `app/utils/data/CRUD.py` contiene operaciones parciales sobre esas tablas y usa parámetros SQL, una base útil para continuar.
- `requeriments.txt` declara Flask, Flask-Bcrypt y Flask-Login, pero las dos últimas dependencias todavía no están integradas en el código.
- `README.md` contiene únicamente el nombre del proyecto. No hay pruebas automatizadas en los archivos revisados.

## 2. Problemas que deben resolverse primero

| Prioridad | Hallazgo | Acción propuesta |
| --- | --- | --- |
| Alta | `CRUD.py` importa `app.utils.database`, pero el módulo disponible es `app/utils/data/database.py`. | Corregir el import y verificar que los módulos se pueden cargar. |
| Alta | `database.py` llama a `initialize_database()` al importarse. | Mover la creación de tablas a un comando explícito de inicialización. |
| Alta | `DB_PATH` usa `parents[2]`, que en la ubicación actual sitúa `saladetareas.db` dentro de `app/`. | Definir una ubicación configurable, por ejemplo en `instance/`, y documentarla. |
| Alta | Las funciones de usuario guardan directamente el valor recibido como contraseña. | Aplicar hashing antes de guardar y verificación segura al iniciar sesión. |
| Alta | `get_all_users()` serializa todas las columnas, incluida `contrasena`. | Seleccionar campos públicos y excluir siempre la contraseña o su hash. |
| Media | Varias operaciones capturan cualquier excepción, imprimen el error y devuelven `0` o nada. | Distinguir errores de validación, registros inexistentes y fallos de base de datos; registrar los fallos de forma coherente. |
| Media | El CRUD produce respuestas Flask mediante `jsonify`. | Devolver datos desde la capa de acceso y construir las respuestas HTTP en las rutas. |
| Media | Faltan listados y consultas necesarias para usar tareas, materias, pagos y asistencias desde una interfaz. | Completar las operaciones según los flujos acordados. |

## 3. Secuencia de implementación

### Etapa 1 — Definir el primer alcance

Antes de ampliar el código, concretar:

- Quién usa la aplicación y qué roles necesita. La columna `rol` existe, pero el código no define sus valores ni permisos.
- Si los usuarios se registran por sí mismos o los crea una persona administradora.
- Quién puede asignar tareas, quién puede completarlas y quién puede consultar cada registro.
- Si una tarea pertenece a un solo usuario, como refleja el esquema actual, o debe asignarse a varios.
- Si pagos y asistencias son indispensables para la primera versión.

**Alcance inicial recomendado:** acceso de usuarios, materias y gestión de tareas. Incorporar pagos y asistencias después de verificar ese flujo, salvo que sean requisitos centrales.

**Resultado esperado:** una lista breve de flujos y permisos que guíe las rutas, las pantallas y las reglas de datos.

### Etapa 2 — Preparar una aplicación ejecutable y organizada

1. Crear una fábrica `create_app()` en `app/__init__.py` y hacer que `run.py` la utilice.
2. Registrar las rutas desde `app/routes.py`, mediante un blueprint si ayuda a mantener la organización.
3. Corregir el import del módulo de base de datos.
4. Configurar la ubicación de SQLite y un comando explícito para inicializar las tablas.
5. Leer la clave de sesión y la configuración del entorno; reservar `debug=True` para desarrollo.
6. Mantener inicialmente SQLite y el acceso SQL existente. Definir la responsabilidad de `models.py` antes de introducir otra capa o un ORM.
7. Normalizar el nombre `requeriments.txt` a `requirements.txt` y actualizar las instrucciones que lo referencien.

**Criterio de finalización:** la aplicación arranca, la página inicial responde y la base se crea mediante una acción explícita en la ubicación documentada.

### Etapa 3 — Fortalecer datos y operaciones CRUD

1. Definir retornos consistentes: identificador al crear, resultado al consultar y cantidad de filas afectadas al actualizar o eliminar.
2. Añadir consultas por identificador y listados necesarios para los módulos del alcance inicial.
3. Validar campos obligatorios, correo, roles permitidos, estados de tarea, fechas y relaciones con usuarios y materias existentes.
4. Definir qué ocurre al eliminar un usuario o materia con registros asociados. Evitar decidir borrados en cascada sin una regla de negocio.
5. Añadir restricciones e índices donde las reglas y las consultas lo justifiquen.
6. Definir un mecanismo de cambios de esquema: `CREATE TABLE IF NOT EXISTS` no actualiza tablas existentes. Preparar copia de respaldo antes de migrar datos reales.

**Criterio de finalización:** las operaciones devuelven resultados claros y los datos inválidos o las relaciones inexistentes se rechazan de forma controlada.

### Etapa 4 — Implementar acceso y permisos

1. Integrar Flask-Bcrypt para guardar hashes de contraseña.
2. Integrar Flask-Login para iniciar sesión, cerrar sesión y cargar el usuario autenticado.
3. Implementar creación de usuarios según el flujo definido en la etapa 1.
4. Aplicar autorización en cada ruta: comprobar el rol y la propiedad de los registros.
5. Excluir credenciales de respuestas y listados.
6. Añadir protección CSRF a los formularios que cambian datos. Si se elige Flask-WTF, incorporarlo expresamente como dependencia.

**Criterio de finalización:** un usuario puede acceder y salir; los intentos de operar sobre registros sin permiso se rechazan desde el servidor.

### Etapa 5 — Completar materias y tareas con una interfaz útil

1. Crear una plantilla base con navegación y mensajes de resultado.
2. Implementar una pantalla inicial con tareas pendientes y próximas fechas de vencimiento.
3. Añadir listado, creación, edición y eliminación de materias según los permisos definidos.
4. Añadir listado, detalle, creación, edición y cambio de estado de tareas.
5. Incorporar filtros por materia y estado, con orden por vencimiento.
6. Mostrar errores de validación, estados sin datos y confirmación de acciones de eliminación.
7. Adaptar las pantallas a móvil y usar etiquetas y controles accesibles.

**Criterio de finalización:** se puede completar el flujo de acceso, creación de materia, asignación de tarea y actualización de estado desde el navegador.

### Etapa 6 — Incorporar pagos y asistencias si forman parte del alcance

- **Pagos:** definir moneda, precisión y qué representa cada registro. Evaluar almacenar unidades monetarias mínimas como enteros en lugar de `REAL`. Implementar registro y consulta del historial con permisos. El esquema actual representa registros de pagos; una integración de cobro requeriría un alcance adicional.
- **Asistencias:** definir si corresponden a un día o a una sesión, si admiten varios registros por fecha y cómo se corrigen. Implementar registro y consulta con validación de duplicados según esa regla.

**Criterio de finalización:** cada módulo permite registrar y consultar información conforme a reglas de negocio documentadas.

### Etapa 7 — Verificar y documentar la primera versión

1. Añadir pruebas con una base SQLite temporal, separada de los datos de uso.
2. Cubrir creación y consulta, correo duplicado, claves foráneas, rollback y registros inexistentes.
3. Cubrir inicio de sesión, denegación de acceso y exclusión de contraseñas en respuestas.
4. Cubrir creación de tareas y cambios de estado con validación y permisos.
5. Recorrer manualmente el flujo principal en escritorio y móvil.
6. Completar el README con instalación, configuración, inicialización de la base, ejecución y pruebas.
7. Antes de publicar, configurar un servidor adecuado para producción, desactivar depuración y definir copias de respaldo.

**Criterio de finalización:** una persona puede instalar y usar la aplicación siguiendo el README, y las pruebas comprueban los flujos críticos.

## 4. Primera tanda concreta de trabajo

Después de acordar el alcance, comenzar con estas acciones en este orden:

- [ ] Corregir el import de la conexión en `CRUD.py`.
- [ ] Crear `create_app()` y conectar `run.py` con el paquete `app`.
- [ ] Configurar la ruta de SQLite y eliminar la inicialización automática al importar.
- [ ] Añadir un comando explícito para crear la base y las tablas.
- [ ] Separar los datos CRUD de las respuestas HTTP y excluir las credenciales del listado de usuarios.
- [ ] Implementar hashing, inicio de sesión y controles de acceso.
- [ ] Construir el primer flujo funcional de materias y tareas.
- [ ] Verificar ese flujo y documentar cómo ejecutarlo.

No empezar por reportes, integraciones de cobro o una ampliación del esquema hasta que el flujo principal esté definido y funcione.
