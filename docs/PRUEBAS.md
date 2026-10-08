# Pruebas — PowerShell

Ejecutar desde la raíz del proyecto, no desde `docs/`.

## Preparar la terminal

```powershell
cd C:\Users\rezoa\Desktop\proyectoweb
.\.venv\Scripts\Activate.ps1
```

## Todas las pruebas

```powershell
python -m unittest discover -s tests -v
```

## Solo recorridos completos (etapa 7)

```powershell
python -m unittest discover -s tests -p "test_final_flows.py" -v
```

## Solo dashboard, búsqueda, filtros y paginación

```powershell
python -m unittest discover -s tests -p "test_dashboard_lists.py" -v
```

## Solo la simulación de PayPal

```powershell
python -m unittest discover -s tests -p "test_paypal_simulation.py" -v
```

## Solo pagos

```powershell
python -m unittest discover -s tests -p "test_payments.py" -v
```

## Solo tareas

```powershell
python -m unittest discover -s tests -p "test_tasks.py" -v
```

## Solo usuarios y autenticación

```powershell
python -m unittest discover -s tests -p "test_users_auth.py" -v
```

`OK` = pasaron. `FAIL` o `ERROR` = revisar el mensaje.
No hace falta arrancar la app ni generar la clave hexadecimal; las pruebas usan bases temporales.
