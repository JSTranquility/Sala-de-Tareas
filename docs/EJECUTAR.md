# Comandos rápidos — PowerShell

Ejecutar desde la raíz del proyecto, no desde `docs/`.

## Preparar la terminal

```powershell
cd C:\Users\rezoa\Desktop\proyectoweb
.\.venv\Scripts\Activate.ps1
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
```

## Ejecutar la app

```powershell
python run.py
```

Abrir: http://127.0.0.1:5000/ · Detener: `Ctrl+C`.

Si el puerto 5000 está ocupado:

```powershell
python -m flask --app run run --port 5001
```

Abrir: http://127.0.0.1:5001/

## Crear el primer administrador

Con la base preparada y sin un administrador activo:

```powershell
python -m flask --app run create-admin
```

Pide nombre, correo y contraseña (8–128 caracteres).

## Primera instalación solamente

Antes de activar el entorno, si todavía no existe:

```powershell
python -m venv .venv
```

Después de activar el entorno, instalar dependencias:

```powershell
python -m pip install -r requeriments.txt
```

Para una base nueva, antes de crear el administrador:

```powershell
python -m flask --app run init-db
```

## Actualizar una base antigua

Con la app detenida; no hace falta para una base nueva:

```powershell
python -m flask --app run migrate-users
python -m flask --app run migrate-tasks
python -m flask --app run migrate-payments
```

## Restablecer una contraseña

```powershell
python -m flask --app run reset-password
```

## Ejecutar pruebas

```powershell
python -m unittest discover -s tests -v
```

La clave hexadecimal nueva cierra las sesiones anteriores. Estos comandos usan
la base predeterminada `saladetareas.db`, salvo que hayas configurado `DATABASE_PATH`.
Si no puedes activar el entorno, sustituye `python` por `.\.venv\Scripts\python.exe`.
