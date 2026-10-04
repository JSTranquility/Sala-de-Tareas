from pathlib import Path
import sqlite3
from contextlib import closing
import tempfile
import unittest

from flask import Flask
from werkzeug.security import check_password_hash

from app.routes import register_routes
from app.utils.data import CRUD as crud
from app.utils.data.database import get_connection, initialize_database
from migrations.add_user_active import migrate


class UsersAndAuthTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'users.db'
        self.app = Flask(__name__, template_folder=str(Path('app/templates').resolve()))
        self.app.config.update(TESTING=True, SECRET_KEY='solo-pruebas', DATABASE_PATH=str(self.path))
        register_routes(self.app)
        with self.app.app_context():
            initialize_database()
            self.admin_id = crud.create_first_admin('Admin', 'admin@example.test', 'clave-segura')
            self.member_id = crud.create_user('Miembro', 'member@example.test', 'clave-segura', None, 'member')
        self.client = self.app.test_client()

    def tearDown(self):
        self.directory.cleanup()

    def token(self):
        self.client.get('/auth/login')
        with self.client.session_transaction() as session:
            return session['csrf_token']

    def post(self, path, data=None, **kwargs):
        return self.client.post(path, data={'csrf_token': self.token(), **(data or {})}, **kwargs)

    def login(self, email='admin@example.test', password='clave-segura'):
        return self.post('/auth/login', {'correo': email, 'contrasena': password})

    def user_data(self, **changes):
        data = dict(nombre='Nuevo', correo='nuevo@example.test', contrasena='clave-segura',
                    telefono='+1 809 555 0100', rol='member', activo='1')
        data.update(changes)
        return data

    def test_login_logout_and_token_rotation(self):
        original = self.token()
        login_html = self.client.get('/auth/login').get_data(as_text=True)
        self.assertIn('Iniciar sesión', login_html)
        self.assertIn('Contraseña', login_html)
        self.assertEqual(self.login().status_code, 302)
        with self.client.session_transaction() as session:
            self.assertEqual(session['user_id'], self.admin_id)
            self.assertNotEqual(session['csrf_token'], original)
            self.assertNotIn('rol', session)
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.post('/auth/logout', data={'csrf_token': original}).status_code, 400)
        self.assertEqual(self.client.get('/auth/logout').status_code, 405)
        self.assertEqual(self.post('/auth/logout').status_code, 302)
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_bad_password_inactive_and_plaintext_are_rejected(self):
        self.assertEqual(self.login(password='incorrecta').status_code, 400)
        with self.app.app_context(), get_connection() as connection:
            connection.execute('UPDATE Usuarios SET activo = 0 WHERE id = ?', (self.member_id,))
        self.assertEqual(self.login('member@example.test').status_code, 400)
        with self.app.app_context(), get_connection() as connection:
            connection.execute('UPDATE Usuarios SET contrasena = ? WHERE id = ?',
                               ('clave-segura', self.admin_id))
        self.assertEqual(self.login().status_code, 400)
        with self.client.session_transaction() as session:
            self.assertNotIn('user_id', session)

    def test_csrf_rejects_absent_wrong_and_non_ascii_tokens(self):
        for token in (None, 'incorrecto', 'inválido'):
            data = {'correo': 'admin@example.test', 'contrasena': 'clave-segura'}
            if token is not None:
                data['csrf_token'] = token
            self.assertEqual(self.client.post('/auth/login', data=data).status_code, 400)
        self.login()
        for path in ('/users/new', f'/users/{self.member_id}/edit',
                     f'/users/{self.member_id}/delete', '/auth/logout'):
            self.assertEqual(self.client.post(path, data=self.user_data()).status_code, 400)
        with self.app.app_context():
            self.assertEqual(len(crud.get_all_users()), 2)

    def test_members_cannot_access_any_users_operation(self):
        self.login('member@example.test')
        for path in ('/users/', '/users/new', f'/users/{self.admin_id}',
                     f'/users/{self.admin_id}/edit'):
            self.assertEqual(self.client.get(path).status_code, 403)
        for path in ('/users/new', f'/users/{self.admin_id}/edit',
                     f'/users/{self.admin_id}/delete'):
            self.assertEqual(self.post(path, self.user_data(rol='admin')).status_code, 403)
        self.assertEqual(self.client.get('/auth/register').status_code, 404)

    def test_anonymous_access_redirects_to_login(self):
        for path in ('/', '/users/', '/users/new', f'/users/{self.admin_id}/edit'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.location.endswith('/auth/login'))

    def test_admin_full_crud_does_not_expose_passwords(self):
        self.login()
        response = self.post('/users/new', self.user_data())
        self.assertEqual(response.status_code, 302)
        detail = self.client.get(response.location)
        self.assertEqual(detail.status_code, 200)
        self.assertIn('Nuevo', detail.get_data(as_text=True))
        self.assertNotIn('clave-segura', detail.get_data(as_text=True))
        with self.app.app_context():
            user = crud.get_user_by_email('nuevo@example.test')
            user_id = user['id']
            password_hash = crud.get_user_for_auth_by_email(user['correo'])['contrasena']
        listed = self.client.get('/users/').get_data(as_text=True)
        self.assertNotIn(password_hash, listed)
        self.assertEqual(self.client.get(f'/users/{user_id}/edit').status_code, 200)
        response = self.post(f'/users/{user_id}/edit', self.user_data(nombre='Editado', contrasena=''))
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(crud.get_user_by_id(user_id)['nombre'], 'Editado')
            self.assertEqual(crud.get_user_for_auth_by_email(user['correo'])['contrasena'], password_hash)
        self.assertEqual(self.client.get(f'/users/{user_id}/delete').status_code, 405)
        self.assertEqual(self.post(f'/users/{user_id}/delete').status_code, 302)
        self.assertEqual(self.client.get(f'/users/{user_id}').status_code, 404)

    def test_validation_duplicates_and_password_not_reflected(self):
        self.login()
        cases = [dict(nombre=''), dict(nombre='x' * 101), dict(correo='invalid'),
                 dict(telefono='letras'), dict(rol='superadmin'), dict(activo='2'),
                 dict(contrasena='corta'), dict(correo='ADMIN@EXAMPLE.TEST')]
        for changes in cases:
            with self.subTest(changes=changes):
                response = self.post('/users/new', self.user_data(**changes))
                self.assertEqual(response.status_code, 400)
                self.assertNotIn('value="clave-segura"', response.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(len(crud.get_all_users()), 2)

    def test_deactivation_revokes_an_existing_session(self):
        self.login('member@example.test')
        with self.app.app_context(), get_connection() as connection:
            connection.execute('UPDATE Usuarios SET activo = 0 WHERE id = ?', (self.member_id,))
        self.assertEqual(self.client.get('/').status_code, 302)
        with self.client.session_transaction() as session:
            self.assertNotIn('user_id', session)

    def test_role_changes_are_checked_on_every_request(self):
        self.login()
        with self.app.app_context(), get_connection() as connection:
            connection.execute("UPDATE Usuarios SET rol = 'member' WHERE id = ?", (self.admin_id,))
        self.assertEqual(self.client.get('/users/').status_code, 403)

    def test_admin_cannot_delete_deactivate_or_demote_self(self):
        self.login()
        self.assertEqual(self.post(f'/users/{self.admin_id}/delete').status_code, 302)
        for changes in (dict(rol='member'), dict(activo='0')):
            response = self.post(f'/users/{self.admin_id}/edit', self.user_data(
                correo='admin@example.test', rol='admin', **changes
            ) if 'rol' not in changes else self.user_data(correo='admin@example.test', **changes))
            self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            user = crud.get_user_by_id(self.admin_id)
            self.assertEqual((user['rol'], user['activo']), ('admin', 1))

    def test_related_user_is_preserved_and_can_be_deactivated(self):
        self.login()
        with self.app.app_context():
            payment_id = crud.create_payment(self.member_id, '12.50')
        response = self.post(f'/users/{self.member_id}/delete', follow_redirects=True)
        self.assertIn('registros asociados', response.get_data(as_text=True))
        response = self.post(f'/users/{self.member_id}/edit', self.user_data(
            correo='member@example.test', activo='0', contrasena=''))
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(crud.get_user_by_id(self.member_id)['activo'], 0)
            self.assertEqual(crud.get_payment_by_id(payment_id)['monto'], 12.5)

    def test_user_content_is_escaped(self):
        self.login()
        response = self.post('/users/new', self.user_data(nombre='<script>alert(1)</script>'), follow_redirects=True)
        self.assertNotIn('<script>alert(1)</script>', response.get_data(as_text=True))
        self.assertIn('&lt;script&gt;', response.get_data(as_text=True))

    def test_cli_admin_creation_reset_and_duplicate_guard(self):
        runner = self.app.test_cli_runner()
        result = runner.invoke(args=['create-admin', '--name', 'Otro', '--email', 'other@example.test'],
                               input='clave-segura\nclave-segura\n')
        self.assertNotEqual(result.exit_code, 0)
        with self.app.app_context():
            crud.delete_user(self.admin_id)
        result = runner.invoke(args=['create-admin', '--name', 'Otro', '--email', 'other@example.test'],
                               input='clave-segura\nclave-segura\n')
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertNotIn('clave-segura', result.output)
        result = runner.invoke(args=['reset-password', '--email', 'member@example.test'],
                               input='otra-clave\notra-clave\n')
        self.assertEqual(result.exit_code, 0, result.output)
        with self.app.app_context():
            user = crud.get_user_for_auth_by_email('member@example.test')
            self.assertTrue(check_password_hash(user['contrasena'], 'otra-clave'))

    def test_missing_secret_and_database_show_controlled_error(self):
        self.app.config['SECRET_KEY'] = None
        self.assertEqual(self.client.get('/auth/login').status_code, 503)
        self.app.config['SECRET_KEY'] = 'solo-pruebas'
        self.app.config['DATABASE_PATH'] = str(Path(self.directory.name) / 'missing.db')
        with self.assertLogs('app.utils.data.database', level='ERROR'):
            response = self.login()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('missing.db', response.get_data(as_text=True))


class MigrationTests(unittest.TestCase):
    def test_migration_preserves_data_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'legacy.db'
            with closing(sqlite3.connect(path)) as connection:
                connection.execute('CREATE TABLE Usuarios (id INTEGER PRIMARY KEY, nombre TEXT, correo TEXT, contrasena TEXT, rol TEXT)')
                connection.execute('INSERT INTO Usuarios VALUES (1, ?, ?, ?, ?)',
                                   ('Antiguo', 'old@example.test', 'valor-original', 'member'))
                connection.commit()
                original = list(connection.iterdump())
            backup = migrate(path)
            with closing(sqlite3.connect(backup)) as connection:
                self.assertEqual(list(connection.iterdump()), original)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute('SELECT nombre, contrasena, activo FROM Usuarios').fetchone(),
                                 ('Antiguo', 'valor-original', 1))
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute('UPDATE Usuarios SET activo = 2')
            self.assertIsNone(migrate(path))
            self.assertEqual(len(list(Path(directory).glob('*.backup-*.db'))), 1)

    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'missing.db'
            with self.assertRaises(sqlite3.OperationalError):
                migrate(path)
            self.assertFalse(path.exists())

    def test_invalid_relations_roll_back_schema_change(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'invalid.db'
            with closing(sqlite3.connect(path)) as connection:
                connection.execute('CREATE TABLE Usuarios (id INTEGER PRIMARY KEY)')
                connection.execute('CREATE TABLE Tareas (usuario_id INTEGER REFERENCES Usuarios(id))')
                connection.execute('INSERT INTO Tareas VALUES (999)')
                connection.commit()
            with self.assertRaises(ValueError):
                migrate(path)
            with closing(sqlite3.connect(path)) as connection:
                self.assertNotIn('activo', [r[1] for r in connection.execute('PRAGMA table_info(Usuarios)')])
                self.assertEqual(connection.execute('SELECT usuario_id FROM Tareas').fetchone()[0], 999)


if __name__ == '__main__':
    unittest.main()
