import copy
from ansible_collections.swisstxt.harbor.plugins.module_utils.base import HarborBaseModule
import requests
from ansible.module_utils.basic import AnsibleModule

DOCUMENTATION = r'''
---
module: harbor_tag_immutability
author:
  - Enes Malik Sen (@esen-transporeon)
version_added: ""
short_description: Deploy tag immutability list
description:
  - Deploys all tag immutabilities from the list and deletes all which don't match the list
options:
  project:
    description:
    - Name of the project where the tag immutabilities will be applied
    required: true
    type: str
    default: {}
  tag_immutability_list:
    description:
    - List with the tag immutabilities
    required: true
    type: list
    default: {}
    suboptions:
      repository:
        description:
        - Dict with the kind and the pattern to match or exclude the repositories
        required: true
        type: list
        default: {}
        suboptions:
          kind:
            description:
            - Defines if the repositories should be matched or excluded
            required: true
            type: str
            default: {}
            choices:
            - repoMatches
            - repoExcludes
          pattern:
            description:
            - Defines the pattern to match or exclude the repositories
            required: true
            type: str
            default: {}
      tag:
        description:
        - Dict with the kind and the pattern to match or exclude the tags
        required: true
        type: list
        default: {}
        suboptions:
          kind:
            description:
            - Defines if the tag should be matched or excluded
            required: true
            type: str
            default: {}
            choices:
            - matches
            - excludes
          pattern:
            description:
            - Defines the pattern to match or exclude the tag
            required: true
            type: str
            default: {}
extends_documentation_fragment:
  - joschi36.harbor.api
'''

EXAMPLES = r'''
- name: Create tag immutabilities for project library
  harbor_tag_immutability:
    api_url: https://localhost/api/v2.0
    api_username: username
    api_password: password
    api_verify: False
    project: library
    tag_immutability_list:
    - repository:
        kind: repoMatches
        pattern: "**"
      tag:
        kind: matches
        pattern: test
'''

class HarborTagImmutabilityModule(HarborBaseModule):
    @property
    def argspec(self):
        argument_spec = copy.deepcopy(self.COMMON_ARG_SPEC)
        argument_spec.update(
            project=dict(type='str', required=True),
            tag_immutability_list=dict(type='list',
              repository=dict(type='dict',
                kind=dict(type='str', required=True, choices=['repoMatches', 'repoExcludes']),
                pattern=dict(type='str', required=True),
                required=True
                ),
              tag=dict(type='dict',
                kind=dict(type='str', required=True, choices=['matches', 'excludes']),
                pattern=dict(type='str', required=True),
                required=True
                ),
              required=True
              )
        )
        return argument_spec

    def createDesiredTagImmutabilityList(self, project_id):
        desired_tag_immutability_list=[]
        for tag_immutability_object in self.module.params['tag_immutability_list']:
          desired_tag_immutability_list.append(self.createDesiredTagImmutability(tag_immutability_object, project_id))

        return desired_tag_immutability_list

    def createDesiredTagImmutability(self, tag_immutability_object, project_id):
        desired_tag_immutability = {
            "disabled": False,
            "action": "immutable",
            "scope_selectors": {
              "repository": [{
                "kind": "doublestar",
                "decoration": tag_immutability_object['repository']['kind'],
                "pattern": tag_immutability_object['repository']['pattern']
                }]
              },
            "tag_selectors": [{
              "kind": "doublestar",
              "decoration": tag_immutability_object['tag']['kind'],
              "pattern": tag_immutability_object['tag']['pattern']
            }],
            "project_id": project_id,
            "priority": 0,
            "template": "immutable_template"
        }

        return desired_tag_immutability

    def getTagImmutabilityList(self, project_id):
        request = requests.get(
            self.api_url+f'/projects/{project_id}/immutabletagrules',
            auth=self.auth,
            verify=self.api_verify
        )
        if not request.status_code == 200:
            self.module.fail_json(msg=self.requestParse(request))
        return request

    def formatGetTagImmutabilityList(self, tag_immutability_list, project_id, tag_immutability_list_project_ids):
        for key in range(len(tag_immutability_list)):
          tag_immutability_list_project_ids[key] = tag_immutability_list[key].pop("id")
          tag_immutability_list[key]["project_id"] = project_id
          tag_immutability_list[key]["priority"] = 0
          tag_immutability_list[key]["disabled"] = False

    def createTagImmutabilities(self, tag_immutability_list, project_id):
        for tag_immutability in tag_immutability_list:
          set_request = requests.post(
                self.api_url+f'/projects/{project_id}/immutabletagrules',
                auth=self.auth,
                json=tag_immutability,
                verify=self.api_verify
            )
          self.errorHandlingHttpRequest(set_request)

    def deleteTagImmutabilities(self, tag_immutability_ids, project_id):
        for tag_immutability_id in tag_immutability_ids:
          set_request = requests.delete(
                self.api_url+f'/projects/{project_id}/immutabletagrules/{tag_immutability_id}',
                auth=self.auth,
                verify=self.api_verify
            )
          self.errorHandlingHttpRequest(set_request)

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

        desired_tag_immutability_list = self.createDesiredTagImmutabilityList(project_id)

        # Get existing Tag Immutabilities
        before_request = self.getTagImmutabilityList(project_id)
        before = before_request.json()

        before_tag_immutability_ids = [None] * len(before)
        self.formatGetTagImmutabilityList(before, project_id, before_tag_immutability_ids)

        if before == desired_tag_immutability_list:
            self.result['changed'] = False
            self.module.exit_json(**self.result)

        # Test change with checkmode
        if self.module.check_mode:
            self.setChanges(before, desired_tag_immutability_list)

        # Apply change without checkmode
        else:

            tag_immutabilities_to_add = [x for x in desired_tag_immutability_list if x not in before]

            self.createTagImmutabilities(tag_immutabilities_to_add, project_id)

            tag_immutabilities_to_delete_keys = [x for x in range(len(before)) if before[x] not in desired_tag_immutability_list]
            tag_immutabilities_to_delete_ids = [before_tag_immutability_ids[x] for x in tag_immutabilities_to_delete_keys]

            self.deleteTagImmutabilities(tag_immutabilities_to_delete_ids, project_id)


            after_request = self.getTagImmutabilityList(project_id)
            after = after_request.json()

            after_tag_immutability_ids = [None] * len(after)
            self.formatGetTagImmutabilityList(after, project_id, after_tag_immutability_ids)

            if before != after:
                self.setChanges(before, after)
            else:
                self.result['changed'] = False

        self.module.exit_json(**self.result)

def main():
    HarborTagImmutabilityModule()

if __name__ == '__main__':
    main()
