from __future__ import annotations

import json
import uuid

from tests import base


class AsyncHTTPTestCase(base.TestCaseWithReset):
    ADMIN_ACCESS = True
    TRUNCATE_TABLES = [
        'v1.projects',
        'v1.environments',
        'v1.namespaces',
        'v1.notification_filters',
        'v1.notification_rules',
        'v1.integration_notifications',
        'v1.integrations',
        'v1.project_types',
    ]

    def setUp(self) -> None:
        super().setUp()
        self.project = self.create_project()
        self.project_fact_type = self.create_project_fact_type()
        self.integration_name = 'some-app'
        self.notification_name = 'pipeline'
        self.surrogate_id = str(uuid.uuid4())

        rsp = self.fetch('/integrations',
                         method='POST',
                         json_body={
                             'name': self.integration_name,
                             'api_endpoint': 'https://integration.example.com',
                             'api_secret': None,
                         })
        self.assertEqual(200, rsp.code)

        rsp = self.fetch(
            f'/integrations/{self.integration_name}/notifications',
            method='POST',
            json_body={
                'name': self.notification_name,
                'id_pattern': '/id',
                'documentation': None,
                'default_action': 'process',
                'verification_token': None,
            })
        self.assertEqual(200, rsp.code)

        rsp = self.fetch(
            f'/integrations/{self.integration_name}'
            f'/notifications/{self.notification_name}'
            f'/rules',
            method='POST',
            json_body={
                'fact_type_id': self.project_fact_type['id'],
                'pattern': '/state',
            })
        self.assertEqual(200, rsp.code)

        rsp = self.fetch(f'/projects/{self.project["id"]}/identifiers',
                         method='POST',
                         json_body={
                             'external_id': self.surrogate_id,
                             'integration_name': self.integration_name,
                         })
        self.assertEqual(200, rsp.code)

    def get_project_fact(self, *, project_id=None) -> str | None:
        project_id = self.project['id'] if project_id is None else project_id
        rsp = self.fetch(f'/projects/{project_id}/facts')
        self.assertEqual(200, rsp.code)

        facts = json.loads(rsp.body)
        if facts:
            self.assertEqual(1, len(facts))
            self.assertEqual(self.project_fact_type['id'],
                             facts[0]['fact_type_id'])
            return facts[0]['value']
        return None

    def test_processing_with_empty_notification(self) -> None:
        rsp = self.fetch(
            f'/integrations/{self.integration_name}'
            f'/notifications/{self.notification_name}'
            f'/post',
            method='POST',
            json_body={})
        self.assertEqual(200, rsp.code)

    def test_processing_correct_notification(self) -> None:
        rsp = self.fetch(
            f'/integrations/{self.integration_name}'
            f'/notifications/{self.notification_name}'
            f'/post',
            method='POST',
            json_body={
                'id': self.surrogate_id,
                'state': 'whatever'
            })
        self.assertEqual(200, rsp.code)

        rsp = self.fetch(f'/projects/{self.project["id"]}/facts')
        self.assertEqual(200, rsp.code)
        self.assertEqual('whatever', self.get_project_fact())

    def test_processing_invalid_notification_paths(self) -> None:
        rsp = self.fetch('/integrations/invalid/notifications/invalid/post',
                         method='POST',
                         json_body={})
        self.assertEqual(404, rsp.code)

        rsp = self.fetch(
            f'/integrations/{self.integration_name}'
            '/notifications/invalid/post',
            method='POST',
            json_body={})
        self.assertEqual(404, rsp.code)

        rsp = self.fetch(
            f'/integrations/{self.integration_name}'
            f'/notifications/{self.notification_name}/get',
            method='POST',
            json_body={})
        self.assertEqual(400, rsp.code)

    def test_filters_for_default_process(self) -> None:
        rsp = self.fetch(
            f'/integrations/{self.integration_name}'
            f'/notifications/{self.notification_name}/filters',
            method='POST',
            json_body={
                'name': 'reject-tests',
                'pattern': '/test',
                'operation': '==',
                'value': 'true',
                'action': 'ignore'
            })
        self.assertEqual(200, rsp.code)

        # test that matching ignore filter actually ignores
        rsp = self.fetch(
            f'/integrations/{self.integration_name}'
            f'/notifications/{self.notification_name}'
            f'/post',
            method='POST',
            json_body={
                'id': self.surrogate_id,
                'state': 'whatever',
                'test': 'true',
            })
        self.assertEqual(200, rsp.code)
        self.assertIsNone(self.get_project_fact(),
                          'Matched filter did not ignore update')

        # test that non-matching ignore filter does not ignore
        rsp = self.fetch(
            f'/integrations/{self.integration_name}'
            f'/notifications/{self.notification_name}'
            f'/post',
            method='POST',
            json_body={
                'id': self.surrogate_id,
                'state': 'whatever',
                'test': 'false',
            })
        self.assertEqual(200, rsp.code)
        self.assertEqual('whatever', self.get_project_fact(),
                         'Unmatched filter ignored update')

        # test that lack of filter condition does not ignore
        rsp = self.fetch(
            f'/integrations/{self.integration_name}'
            f'/notifications/{self.notification_name}'
            f'/post',
            method='POST',
            json_body={
                'id': self.surrogate_id,
                'state': 'something-else',
            })
        self.assertEqual(200, rsp.code)
        self.assertEqual('something-else', self.get_project_fact(),
                         'Unmatched filter ignored update')

    def test_filters_for_default_ignore(self) -> None:
        rsp = self.fetch(
            f'/integrations/{self.integration_name}'
            f'/notifications/{self.notification_name}',
            method='PATCH',
            json_body=[{
                'op': 'replace',
                'path': '/default_action',
                'value': 'ignore'
            }])
        self.assertEqual(200, rsp.code)

        rsp = self.fetch(
            f'/integrations/{self.integration_name}'
            f'/notifications/{self.notification_name}/filters',
            method='POST',
            json_body={
                'name': 'accept-non-tests',
                'pattern': '/test',
                'operation': '!=',
                'value': 'true',
                'action': 'process'
            })
        self.assertEqual(200, rsp.code)

        rsp = self.fetch(
            f'/integrations/{self.integration_name}'
            f'/notifications/{self.notification_name}/filters',
            method='POST',
            json_body={
                'name': 'accept-production',
                'pattern': '/environment',
                'operation': '==',
                'value': 'production',
                'action': 'process'
            })
        self.assertEqual(200, rsp.code)

        # test that non-matching filter ignores
        rsp = self.fetch(
            f'/integrations/{self.integration_name}'
            f'/notifications/{self.notification_name}'
            f'/post',
            method='POST',
            json_body={
                'id': self.surrogate_id,
                'state': 'whatever',
                'test': 'true',
            })
        self.assertEqual(200, rsp.code)
        self.assertIsNone(self.get_project_fact(),
                          'Unmatched filter did not ignore update')

        # test that matching partial filter does not ignore
        rsp = self.fetch(
            f'/integrations/{self.integration_name}'
            f'/notifications/{self.notification_name}'
            f'/post',
            method='POST',
            json_body={
                'id': self.surrogate_id,
                'state': 'whatever',
                'test': 'false',
            })
        self.assertEqual(200, rsp.code)
        self.assertEqual('whatever', self.get_project_fact(),
                         'Partial filter match ignored update')

        # test that matching full filter does not ignore
        rsp = self.fetch(
            f'/integrations/{self.integration_name}'
            f'/notifications/{self.notification_name}'
            f'/post',
            method='POST',
            json_body={
                'id': self.surrogate_id,
                'state': 'something-else',
                'test': 'false',
                'environment': 'production',
            })
        self.assertEqual(200, rsp.code)
        self.assertEqual('something-else', self.get_project_fact(),
                         'Full filter match ignored update')

        # test that half match of filter condition applies
        rsp = self.fetch(
            f'/integrations/{self.integration_name}'
            f'/notifications/{self.notification_name}'
            f'/post',
            method='POST',
            json_body={
                'id': self.surrogate_id,
                'state': 'yet-another-thing',
                'test': 'false',
                'environment': 'local',
            })
        self.assertEqual(200, rsp.code)
        self.assertEqual('yet-another-thing', self.get_project_fact(),
                         'Half-matched filter ignored update')

        # test that lack of filter condition ignores
        rsp = self.fetch(
            f'/integrations/{self.integration_name}'
            f'/notifications/{self.notification_name}'
            f'/post',
            method='POST',
            json_body={
                'id': self.surrogate_id,
                'state': 'yet-another-another-thing',
            })
        self.assertEqual(200, rsp.code)
        self.assertEqual('yet-another-thing', self.get_project_fact(),
                         'Unmatched filter applied update')

    def test_different_project_type(self) -> None:
        rsp = self.fetch(
            f'/integrations/{self.integration_name}'
            f'/notifications/{self.notification_name}'
            f'/filters',
            method='POST',
            json_body={
                'name': 'reject-testing',
                'pattern': '/environment',
                'operation': '!=',
                'value': 'production',
                'action': 'ignore'
            })
        self.assertEqual(200, rsp.code)

        surrogate_id = str(uuid.uuid4())
        new_project_type = self.create_project_type()
        new_project = self.create_project(
            project_type_id=new_project_type['id'])
        rsp = self.fetch(f'/projects/{new_project["id"]}/identifiers',
                         method='POST',
                         json_body={
                             'external_id': surrogate_id,
                             'integration_name': self.integration_name,
                         })
        self.assertEqual(200, rsp.code)

        rsp = self.fetch(
            f'/integrations/{self.integration_name}'
            f'/notifications/{self.notification_name}'
            f'/get?id={surrogate_id}&environment=production&state=matched', )
        self.assertEqual(200, rsp.code)
        self.assertIsNone(
            self.get_project_fact(project_id=new_project['id']),
            'Fact should not be updated for different project type')
