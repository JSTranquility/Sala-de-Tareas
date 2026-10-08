"""Gestión de materias y navegación de tareas sobre SQLite temporal."""

from test_tasks import TaskTestCase
from app.utils.data import CRUD as crud


class SubjectsTests(TaskTestCase):
    def test_complete_crud_and_task_selection(self):
        self.authenticate()
        self.assertEqual(self.client.get('/subjects/new').status_code, 200)
        response = self.post('/subjects/new', {'nombre': 'Historia', 'descripcion': 'Curso'})
        self.assertEqual(response.status_code, 302)
        subject_id = int(response.location.rsplit('/', 1)[1])
        for path in ('/subjects/', response.location, f'/subjects/{subject_id}/edit'):
            page = self.client.get(path)
            self.assertEqual(page.status_code, 200)
            self.assertIn('Historia', page.get_data(as_text=True))
        form = self.client.get('/tasks/new').get_data(as_text=True)
        self.assertIn(f'value="{subject_id}"', form)
        task_response = self.post('/tasks/new', self.task_data(materia_id=str(subject_id)))
        self.assertEqual(task_response.status_code, 302)
        self.assertIn('Historia', self.client.get(task_response.location).get_data(as_text=True))
        self.assertEqual(self.post(f'/subjects/{subject_id}/edit',
                                  {'nombre': 'Historia universal', 'descripcion': 'Nueva'}).status_code, 302)
        self.assertIn('Historia universal', self.client.get(task_response.location).get_data(as_text=True))
        blocked = self.post(f'/subjects/{subject_id}/delete', follow_redirects=True)
        self.assertIn('tareas asociadas', blocked.get_data(as_text=True))
        self.post(task_response.location + '/delete')
        self.assertEqual(self.post(f'/subjects/{subject_id}/delete').status_code, 302)
        self.assertEqual(self.client.get(f'/subjects/{subject_id}').status_code, 404)

    def test_validation_csrf_permissions_and_methods(self):
        self.authenticate()
        for values in ({'nombre': ' '}, {'nombre': 'x' * 121},
                       {'nombre': 'Curso', 'descripcion': 'x' * 2001}):
            self.assertEqual(self.post('/subjects/new', values).status_code, 400)
        self.assertEqual(self.client.post('/subjects/new', data={'nombre': 'Curso'}).status_code, 400)
        self.assertEqual(self.post(f'/subjects/{self.subject_id}/delete',
                                  {'csrf_token': 'incorrecto'}).status_code, 400)
        self.assertEqual(self.client.get(f'/subjects/{self.subject_id}/delete').status_code, 405)
        self.assertEqual(self.client.get('/subjects/999999').status_code, 404)
        self.assertEqual(self.post('/subjects/999999/edit', {'nombre': 'Curso'}).status_code, 404)
        self.assertEqual(self.post('/subjects/999999/delete').status_code, 404)
        self.authenticate(2)
        for path in ('/subjects/', '/subjects/new', f'/subjects/{self.subject_id}',
                     f'/subjects/{self.subject_id}/edit'):
            self.assertEqual(self.client.get(path).status_code, 403)
        for path in ('/subjects/new', f'/subjects/{self.subject_id}/edit',
                     f'/subjects/{self.subject_id}/delete'):
            self.assertEqual(self.post(path, {'nombre': 'Curso'}).status_code, 403)
        with self.app.app_context():
            self.assertEqual(crud.get_subject_by_id(self.subject_id)['descripcion'], 'Conservar')

    def test_task_detail_links_for_admin_and_assigned_member(self):
        for user_id in (1, 2):
            self.authenticate(user_id)
            page = self.client.get('/tasks/').get_data(as_text=True)
            self.assertIn(f'data-task-url="/tasks/{self.task_id}"', page)
            self.assertIn('Ver detalle', page)
            self.assertEqual(self.client.get(f'/tasks/{self.task_id}').status_code, 200)
        self.assertEqual(self.client.get(f'/tasks/{self.other_id}').status_code, 403)
