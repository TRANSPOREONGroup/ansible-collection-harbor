import copy
from ansible_collections.swisstxt.harbor.plugins.module_utils.base import HarborBaseModule
import requests
from ansible.module_utils.basic import AnsibleModule

DOCUMENTATION = r'''
---
module: harbor_retention
author:
  - Enes Malik Sen (@Dragonax42)
version_added: ""
short_description: Manage retention policies
description:
  - Update or create retention policies for a project
options:
  project:
    description:
    - Name of the project where the policies will be applied
    required: true
    type: str
    default: {}
  rules:
    description:
    - List with the retention policies
    - The list can be aquired in the right format by manually configuring the retention rules in the UI and then requesting it from the API.
    required: true
    type: list
    default: {}
  schedule_cron:
    description:
    - Schedule of the retention runs in cron format
    required: true
    type: str
    default: {}
extends_documentation_fragment:
  - joschi36.harbor.api
'''

EXAMPLES = r'''
# Configuring two retention policies for the project library to run every week
- name: Create Retention rules
  harbor_retention:
    api_url: https://localhost/api/v2.0
    api_username: username
    api_password: password
    api_verify: False
    project: library
    schedule_cron: 0 0 0 * * 0
    rules:
      - action: retain
        params:
          latestPushedK: 10
        scope_selectors:
          repository:
          - decoration: repoMatches
            kind: doublestar
            pattern: "**"
        tag_selectors:
        - decoration: matches
          extras: '{"untagged":true}'
          kind: doublestar
          pattern: "**"
        template: latestPushedK
      - action: retain
        params:
          nDaysSinceLastPush: 30
        scope_selectors:
          repository:
          - decoration: repoMatches
            kind: doublestar
            pattern: "**"
        tag_selectors:
        - decoration: matches
          extras: '{"untagged":true}'
          kind: doublestar
          pattern: "**"
        template: nDaysSinceLastPush
'''

class HarborRetentionModule(HarborBaseModule):
    @property
    def argspec(self):
        argument_spec = copy.deepcopy(self.COMMON_ARG_SPEC)
        argument_spec.update(
            project=dict(type='str', required=True),
            rules=dict(type='list', required=True),
            schedule_cron=dict(type='str', required=True),
            force=dict(type='bool', required=False, default=False),
            state=dict(default='present', choices=['present'])
        )
        return argument_spec

    def createDesiredRetentionPolicy(self, project_id):
        desired_retentions_policy = {
            "algorithm":"or",
            "rules": self.module.params["rules"],
            "scope":{
                "level":"project",
                "ref": project_id
            },
            "trigger":{
                "kind":"Schedule",
                "settings":{
                    "cron": self.module.params["schedule_cron"]
                }
            }
        }
        return desired_retentions_policy

    def getRetentionPolicy(self, project_retention_id):
        request = requests.get(
            self.api_url+f'/retentions/{project_retention_id}',
            auth=self.auth,
            verify=self.api_verify
        )
        if not request.status_code == 200:
            self.module.fail_json(msg=self.requestParse(request))
        return request

    def errorHandlingPostOrPutRequest(self, request):
        if request.status_code == 200 or request.status_code == 201:
            pass
        elif request.status_code == 401:
            self.module.fail_json(msg="User need to log in first.", **self.result)
        elif request.status_code == 403:
            self.module.fail_json(msg="User does not have permission of admin role.", **self.result)
        elif request.status_code == 500:
            self.module.fail_json(msg="Unexpected internal errors.", **self.result)
        else:
            self.module.fail_json(msg=f"""
                Unknown HTTP status code: {request.status_code}
                Body: {request.text}
            """)

    def __init__(self):
        self.module = AnsibleModule(
            argument_spec=self.argspec,
            supports_check_mode=True
        )

        super().__init__()

        self.result = dict(
            changed=False
        )

        # Get Project ID
        project = self.getProjectByName(self.module.params['project'])
        if not project:
            self.module.fail_json(msg="Project not found", **self.self.result)
        project_id = project["project_id"]

        desired_retention_policy = self.createDesiredRetentionPolicy(project_id)

        if 'retention_id' in project['metadata']:
            project_retention_id = project['metadata']['retention_id']

            # Get existing retention policy
            before_request = self.getRetentionPolicy(project_retention_id)
            before = before_request.json()

            if (not self.module.params['force']) and before == desired_retention_policy:
                self.result['changed'] = False
                self.module.exit_json(**self.result)

            # Test change with checkmode
            if self.module.check_mode:
                self.setChanges(before, desired_retention_policy)

            # Apply change without checkmode
            else:
                set_request = requests.put(
                    self.api_url+f'/retentions/{project_retention_id}',
                    auth=self.auth,
                    json=desired_retention_policy,
                    verify=self.api_verify
                )
                self.errorHandlingPostOrPutRequest(set_request)

                after_request = self.getRetentionPolicy(project_retention_id)
                after = after_request.json()

                if before != after:
                    self.setChanges(before, after)
        else:
            if self.module.check_mode:
                self.result['retention_policy'] = desired_retention_policy

            else:
                # Create new retention policy
                create_retentions_request = requests.post(
                    self.api_url+'/retentions',
                    auth=self.auth,
                    json=desired_retention_policy,
                    verify=self.api_verify
                )
                self.errorHandlingPostOrPutRequest(create_retentions_request)

                project = self.getProjectByName(self.module.params['project'])
                project_retention_id = project["metadata"]["retention_id"]

                after_request = self.getRetentionPolicy(project_retention_id)
                self.result['retention_policy'] = copy.deepcopy(after_request.json())

            self.result['changed'] = True

        self.module.exit_json(**self.result)

def main():
    HarborRetentionModule()

if __name__ == '__main__':
    main()
