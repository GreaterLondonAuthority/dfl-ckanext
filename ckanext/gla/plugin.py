from collections import OrderedDict
from typing import Any, Optional, Mapping

import logging
import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
import ckan.lib.mailer as Mailer
from ckan.common import _
from ckan.model import User
from ckan.lib import signals
from ckan.config.declaration import Declaration, Key
from ckan.lib.helpers import dict_list_reduce, markdown_extract, ungettext
from ckan.types import Schema, Validator
from markupsafe import Markup
from .email import send_reset_link

from . import auth, custom_fields, helpers, search, timestamps, views, user
from .search_highlight import (  # query is imported for initialisation, though not explicitly used
    action, query)

TABLE_FORMATS = toolkit.config.get("ckan.harvesters.table_formats").split(" ")
REPORT_FORMATS = toolkit.config.get("ckan.harvesters.report_formats").split(" ")
GEOSPATIAL_FORMATS = toolkit.config.get("ckan.harvesters.geospatial_formats").split(" ")

# Override this function to add a html template to password reset link email
Mailer.send_reset_link = send_reset_link

log = logging.getLogger(__name__)

class GlaPlugin(plugins.SingletonPlugin, toolkit.DefaultDatasetForm):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IConfigDeclaration)
    plugins.implements(plugins.IAuthFunctions, inherit=True)
    plugins.implements(plugins.IAuthenticator, inherit=True)
    plugins.implements(plugins.IPackageController, inherit=True)
    plugins.implements(plugins.IResourceController, inherit=True)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IBlueprint)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.IDatasetForm)
    plugins.implements(plugins.IFacets)
    plugins.implements(plugins.IValidators)

    def get_validators(self) -> dict[str, Validator]:
        return {"user_password_validator": auth.user_password_validator}

    # IConfigDeclaration
    def declare_config_options(self, declaration: Declaration, key: Key):
        declaration.declare_list(key.ckan.harvesters.table_formats, [])
        declaration.declare_list(key.ckan.harvesters.report_formats, [])
        declaration.declare_list(key.ckan.harvesters.geospatial_formats, [])

    # IConfigurer
    def update_config(self, config_):
        toolkit.add_template_directory(config_, "templates")
        toolkit.add_public_directory(config_, "public")
        toolkit.add_resource("assets", "gla")
        custom_fields.add_solr_config()

    # IAuthFunctions
    def get_auth_functions(self):
        auth_functions = {"user_list": auth.user_list, "user_show": auth.user_show}
        return auth_functions

    # IPackageController
    def before_dataset_search(self, search_params):
        # Include showcases *and* datasets in the search results:
        # We only want Showcases to show up when there is a search query
        search_params = search.add_quality_to_search(search_params)
        search_params.update(
            {
                "hl": "on",
                "hl.method": "unified",
                "hl.fragsizeIsMinimum": "false",
                "hl.requireFieldMatch": "true",
                "hl.snippets": "1",
                "hl.fragsize": "200",
                "hl.bs.type": "SENTENCE",
                "hl.fl": "title,extras_sanitized_notes,extras_sanitized_search_description",
                "hl.simple.pre": "[[",
                "hl.simple.post": "]]",
                "hl.maxAnalyzedChars": "250000",  # only highlight matches occuring in the first 250k characters of a field we increase this from SOLRs default of 51k because some datasets have long descriptions and highlighting wasn't displaying
            }
        )

        return search_params

    # IPackageController
    def before_dataset_view(self, package_dict):
        gla_information = []

        if package_dict.get("num_resources", 0) > 0:
            num_resources = package_dict.get("num_resources", 0)
            files_suffix = ungettext("file", "files", package_dict["num_resources"])

            formats = dict_list_reduce(package_dict.get("resources", []), "format")
            formats = list(map(str.lower, formats))
            formats.sort()
            formats_string = ", ".join(formats)
            if len(formats) > 0:
                formats_string = f"({formats_string})"
            else:
                formats_string = ""

            resource_summary = f"{num_resources} {files_suffix} {formats_string}"

            gla_information.append(resource_summary)

            total_file_size = sum(
                item["size"]
                for item in package_dict.get("resources", [])
                if item and item["size"] is not None
            )

            package_dict["total_file_size"] = total_file_size

            gla_information.append(helpers.humanise_file_size(total_file_size))
        else:
            package_dict["total_file_size"] = 0

        for extra in package_dict.get("extras", []):
            if extra["key"] == "update_frequency":
                package_dict["update_frequency_label"] = extra["value"]
                gla_information.append(f"Expected update {extra['value'].lower()}")
                break

        package_dict["gla_result_summary"] = " • ".join(gla_information)
        return package_dict

    def after_dataset_search(
        self, search_results: dict[str, Any], search_params: dict[str, Any]
    ):

        def _get_highlighted_field(
            field_name_in_highlight_dict: str, index_id: str
        ) -> str | None:
            highlighted_field = search_results["highlighting"][index_id].get(
                field_name_in_highlight_dict, None
            )

            if highlighted_field and isinstance(highlighted_field, list):
                return highlighted_field[0]

            return highlighted_field

        def _get_extras_field(
            field_name_in_extras_dict: str, extras_list: list[dict[str, str]]
        ) -> str:
            for extras_dict in extras_list:
                if extras_dict["key"] == field_name_in_extras_dict:
                    return extras_dict["value"]
            return ""

        for result in search_results["results"]:
            index_id = result.get("index_id", False)
            if index_id and index_id in search_results["highlighting"]:
                highlighted_title = _get_highlighted_field("title", index_id)
                highlighted_notes = _get_highlighted_field(
                    "extras_sanitized_notes", index_id
                )
                highlighted_search_description = _get_highlighted_field(
                    "extras_search_description", index_id
                )
                highlighted_organization_title = _get_highlighted_field(
                    "organization", index_id
                )

                title = highlighted_title or result["title"]
                notes = highlighted_notes or result.get("sanitized_notes", "")
                search_description = highlighted_search_description or result.get(
                    "sanitized_search_description", ""
                )
                organization = (
                    highlighted_organization_title or result["organization"]["title"]
                )

                # Fall back to notes if search_description is present but not highlighted
                if search_description and "[[" in search_description:
                    search_description = search_description
                else:
                    search_description = notes

                result["title"] = title.replace(
                    "[[", '<span class="dataset-search-highlight">'
                ).replace("]]", "</span>")

                result["organization"]["title"] = organization.replace(
                    "[[", '<span class="dataset-search-highlight">'
                ).replace("]]", "</span>")

                # Handle unclosed tags that flow into the next search result
                sanitized_search_description = str(
                    markdown_extract(search_description, extract_length=500)
                )
                sanitized_search_description_list = []
                for substring in sanitized_search_description.split("[["):
                    if not substring:
                        continue
                    if "]]" in substring:
                        span_content, rest = substring.split("]]")
                        sanitized_search_description_list.append(
                            Markup(
                                f'<span class="dataset-search-highlight">{span_content}</span>'
                            )
                        )
                        sanitized_search_description_list.append(
                            markdown_extract(rest, extract_length=0)
                        )
                    else:
                        sanitized_search_description_list.append(
                            markdown_extract(substring, extract_length=0)
                        )
                result["search_description"] = " ".join(
                    sanitized_search_description_list
                )

        return search_results

    def after_dataset_create(self, ctx, package):
        timestamps.override(ctx, package)

    def after_dataset_update(self, ctx, package):
        timestamps.override(ctx, package)

    def after_resource_delete(self, ctx, resources):
        timestamps.set_to_now(ctx, resources)

    def before_dataset_index(self, pkg_dict: dict[str, Any]) -> dict[str, Any]:
        new_format_list = []
        for file_format in pkg_dict.get("res_format", []):
            if file_format.lower() in TABLE_FORMATS:
                new_format_list.append("Tables")
            elif file_format.lower() in REPORT_FORMATS:
                new_format_list.append("Reports")
            elif file_format.lower() in GEOSPATIAL_FORMATS:
                new_format_list.append("Geospatial")
            else:
                continue  # new_format_list.append("Other")

        pkg_dict["dfl_res_format_group"] = new_format_list

        return pkg_dict

    # ITemplateHelpers
    def get_helpers(self):
        return helpers.get_helpers()

    # IBlueprint
    def get_blueprint(self):
        return views.get_blueprints()

    # IActions
    def get_actions(self):
        return {
            "debug_dataset_search": search.debug,
            "log_chosen_search_result": search.log_selected_result,
            "package_search": action.package_search,
            "user_create": user.user_create,
        }

    # IDatasetForm
    # Follows https://docs.ckan.org/en/2.10/extensions/adding-custom-fields.html
    def create_package_schema(self) -> Schema:
        schema = super(GlaPlugin, self).create_package_schema()
        schema.update(custom_fields.custom_dataset_fields)
        return schema

    def update_package_schema(self) -> Schema:
        schema = super(GlaPlugin, self).update_package_schema()
        schema.update(custom_fields.custom_dataset_fields)
        return schema

    def show_package_schema(self) -> Schema:
        schema = super(GlaPlugin, self).show_package_schema()
        schema.update(
            {
                field: [
                    toolkit.get_converter("convert_from_extras"),
                    toolkit.get_validator("ignore_missing"),
                ]
                for field in custom_fields.custom_dataset_fields.keys()
            }
        )
        schema.update(
            {
                "harvest_source_title": [
                    toolkit.get_converter("convert_from_extras"),
                    toolkit.get_validator("ignore_missing"),
                ],
                "harvest_source_frequency": [
                    toolkit.get_converter("convert_from_extras"),
                    toolkit.get_validator("ignore_missing"),
                ],
                "sanitized_search_description": [
                    toolkit.get_converter("convert_from_extras"),
                    toolkit.get_validator("ignore_missing"),
                ],
                "sanitized_notes": [
                    toolkit.get_converter("convert_from_extras"),
                    toolkit.get_validator("ignore_missing"),
                ],
            }
        )
        return schema

    def is_fallback(self):
        return True

    def package_types(self) -> list[str]:
        return []

    # IFacets
    def dataset_facets(self, facets_dict, _):
        return OrderedDict(
            [
                ("dfl_res_format_group", toolkit._("Format")),
                ("res_format", toolkit._("File type")),
                ("organization", facets_dict["organization"]),
                ("project_name", toolkit._("Projects")),
                # Entry type is disabled for now as the value is null for harvested datasets
                # The filter works, so enabling it will allow us to filter for datasets with
                # the field set, either by manual edit, script, or updates to harvester
                # ("entry_type", toolkit._("Type")),
                ("london_smallest_geography", toolkit._("Smallest geography")),
                ("update_frequency", toolkit._("Update frequency")),
            ]
        )

    def organization_facets(self, facets_dict, *args):
        return facets_dict

    def group_facets(self, facets_dict, *args):
        return facets_dict

    # IAuthenticator
    
    # Extend the default_authenticate() function
    # Force username and email to be lowercase when a user tries to login
    def authenticate(
        self, identity: Mapping[str, Any]
    ) -> Optional["User"]:
      if not ('login' in identity and 'password' in identity):
          return None

      login = identity['login']
      # Force username and email to be lowercase
      user_obj = User.by_name(login.lower())
      if not user_obj:
          user_obj = User.by_email(login.lower())

      if user_obj is None:
          log.debug('Login failed - username or email %r not found', login)
      elif not user_obj.is_active:
          log.debug('Login as %r failed - user isn\'t active', login)
      elif not user_obj.validate_password(identity['password']):
          log.debug('Login as %r failed - password not valid', login)
      else:
          return user_obj
      signals.failed_login.send(login)
      return None
