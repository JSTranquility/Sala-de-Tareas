# Presentación — Sala de Tareas

## Apertura (1 minuto)

«Sala de Tareas es una aplicación web para organizar el trabajo de un equipo.
El administrador gestiona usuarios, materias, tareas y registros de pagos; los miembros
consultan sus tareas y actualizan su estado. La construimos con Python, Flask,
SQLite, HTML, CSS y JavaScript sencillo para un curso de Python intermedio.»

## Demostración (5–7 minutos)

1. Iniciar sesión como administrador y mostrar el dashboard: estados, vencimientos
   y totales de pagos separados en USD y DOP.
2. Mostrar **Usuarios** y crear un miembro de demostración con una contraseña de prueba.
3. Crear una materia desde **Materias** y seleccionarla al crear una tarea
   asignada a ese miembro. Abrir el detalle haciendo clic en la fila o en
   **Ver detalle**. Explicar que el asignado realiza la
   tarea y que el creador se guarda por separado.
4. Mostrar búsqueda y filtros. La paginación aparece cuando hay más de 10 registros.
5. Registrar un pago pendiente con método **Otro**. Mostrar rechazo y cancelación
   en la simulación de PayPal; finalmente aprobar y mostrar fecha y nota educativa.
6. Cerrar sesión, entrar como miembro y cambiar el estado de su tarea. Mostrar
   que no tiene acceso a usuarios ni pagos.
7. Volver como administrador y mostrar el resultado actualizado. Explicar que
   una tarea con pagos no se elimina y que un pago se anula conservando el historial.
8. Alternar el tema claro/oscuro y, si hay tiempo, mostrar la vista móvil.

Usar una base de demostración separada. Asignar una ruta **nueva** antes de preparar
el entorno; no usar la base que contiene datos personales:

```powershell
$env:DATABASE_PATH = "demo-presentacion.db"
```

Si ese archivo todavía no existe, seguir la instalación y creación del primer
administrador en [EJECUTAR.md](EJECUTAR.md). Si ya está preparado, solo arrancar.
La variable afecta únicamente la terminal actual; si se abre otra, asignarla de
nuevo. Para volver a la base predeterminada, detener la app y ejecutar:

```powershell
Remove-Item Env:DATABASE_PATH -ErrorAction SilentlyContinue
```

No se generan datos de demostración automáticamente. Preparar las cuentas antes
de exponer y no mostrar contraseñas, hashes ni datos personales en pantalla.

## Explicación del código (3–4 minutos)

```text
Navegador → routes.py → forms.py → CRUD.py → database.py → SQLite
              ↓
         Plantillas Jinja + CSS local + JavaScript del tema
```

- `run.py`: configura Flask y registra rutas y recursos estáticos.
- `routes.py`: coordina las peticiones y comprueba sesión, rol y CSRF.
- `forms.py`: valida los datos en Python.
- `CRUD.py`: ejecuta SQL parametrizado; devuelve datos, no respuestas HTTP.
- `database.py`: centraliza conexión, commit, rollback y cierre.
- `models.py`: convierte dinero con `Decimal`; SQLite guarda centavos enteros.
- `paypal_simulator.py`: devuelve un resultado ficticio elegido por el usuario.

Mostrar el [esquema de la base](../README.md#base-de-datos) y explicar que
`Tareas.usuario_id` es el asignado, mientras `Pagos.usuario_id` es el receptor.

## Verificación (1 minuto)

Mostrar las pruebas de [PRUEBAS.md](PRUEBAS.md). Cubren CRUD, permisos, CSRF,
transacciones, migraciones, dinero, dashboard y recorridos con login real.
Las pruebas usan bases temporales; no modifican la base de la demostración.

## Cierre

«El proyecto integra tareas, usuarios y registros de pagos con permisos en el
servidor y conservación del historial. PayPal es una simulación educativa:
no hay cobros ni transferencias reales. Mantuvimos una estructura sencilla,
sin ORM ni servicios externos, para poder explicar cada paso del código.»

Para preguntas técnicas, consultar [la guía de defensa](EXPOSICION_PROYECTO.md).
