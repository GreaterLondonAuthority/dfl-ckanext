import logging
import os
from os.path import exists
from typing import Any, cast
import ckan
import ckan.model as model
import ckan.plugins.toolkit as tk
from . import auth, email
import ckan.plugins.toolkit as toolkit
import csv
from ckan import authz
import ckan.lib.base as base
from ckan.common import _

log = logging.getLogger(__name__)

ORGAINZATION_DICT = {}
try:
    with open("organisation_mappings.csv", mode='r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            ORGAINZATION_DICT[row["Original ID"]] = row["Override ID"]
except:
    log.debug("Opening CSV failed")

@toolkit.auth_disallow_anonymous_access
def migrate(context, data_dict={}): 

    requester = context.get("user", None)
    
    if not authz.is_sysadmin(requester):
        return base.abort(403, _("Not authorized to see this page"))

    base_context = {
        "model": model,
        "session": model.Session,
        "user": "ckan_admin",
    }

    organizations = toolkit.get_action("organization_list")(data_dict={})

    for organization in organizations:

        org_mapping = ORGAINZATION_DICT.get(organization, "")

        if org_mapping != "":

            new_org = None

            try:
                new_org = toolkit.get_action('organization_show')(data_dict={'id': org_mapping})
            except toolkit.ObjectNotFound:
                current_org = toolkit.get_action('organization_show')(data_dict={'id': organization})
                org_data_dict = {
                    'name': org_mapping,
                    'title': org_mapping, 
                    "id": org_mapping,
                    'description': current_org["description"],
                    'image_url' : current_org["image_url"],
                    'is_organization': True,
                    'state': 'active'
                }
                new_org = toolkit.get_action('organization_create')(base_context, org_data_dict)
                log.info("Organization %s has been newly created", org_mapping)

            datasets = get_datasets_by_org(organization, base_context)

            for dataset in datasets:
                    try:
                        toolkit.get_action('package_owner_org_update')(
                            base_context,
                            {
                                'id': dataset["id"], 
                                'organization_id': new_org["id"]
                            }
                        )
                        log.info(f"dataset updated '{dataset['id']}'")
                    except BaseException as e:
                        log.warning(f"FAILED to update dataset for org '{dataset['owner_org']}' for ID '{dataset['id']}'.")

            remaining_datasets = get_datasets_by_org(organization, base_context)
            if not remaining_datasets:
                try:
                    toolkit.get_action('organization_delete')(base_context, {'id': organization})
                    log.info(f"Old organization '{organization}' deleted.")
                except:
                    log.warning(f"FAILED to delete old organization '{organization}' as it still has datasets.")
            else:
                log.warning(f"Old organization '{organization}' still has datasets and cannot be deleted.")

    return "get_migrate_organizations completed"

def get_datasets_by_org(org_name, context):
    search_result = toolkit.get_action('package_search')(
    context, {
        'fq': f'organization:{org_name}', 
        'rows': 1000,
        'include_private': True,
        'include_drafts': True,
        'include_deleted': True
        }
    )
    return search_result['results']