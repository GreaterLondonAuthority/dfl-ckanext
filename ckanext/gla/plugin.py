from collections import OrderedDict
from typing import Any

import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
from ckan.lib.helpers import markdown_extract
from ckan.types import Schema
from markupsafe import Markup

from . import auth, custom_fields, helpers, search, timestamps, views
from .search_highlight import action, query


class GlaPlugin(plugins.SingletonPlugin, toolkit.DefaultDatasetForm):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IAuthFunctions, inherit=True)
    plugins.implements(plugins.IPackageController, inherit=True)
    plugins.implements(plugins.IResourceController, inherit=True)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IBlueprint)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.IDatasetForm)
    plugins.implements(plugins.IFacets)

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
                "hl.fragsize": 200,
                "hl.fl": "title,notes,search_description",
                "hl.simple.pre": "[[",
                "hl.simple.post": "]]",
            }
        )
        return search_params


    # IPackageController
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

        for result in search_results["results"]:
            resources = result.get('resources',[])
            result['total_file_size'] = sum(item['size'] for item in resources if item and item['size'] is not None)
            result['number_of_files'] = len(resources)

            index_id = result.get("index_id", False)
            if index_id and index_id in search_results["highlighting"]:
                highlighted_title = _get_highlighted_field("title", index_id)
                highlighted_notes = _get_highlighted_field("notes", index_id)
                highlighted_search_description = _get_highlighted_field(
                    "extras_search_description", index_id
                )
                highlighted_organization_title = _get_highlighted_field(
                    "organization", index_id
                )

                title = highlighted_title or result["title"]
                notes = highlighted_notes or result.get("notes")
                search_description = highlighted_search_description or result.get(
                    "search_description"
                )
                organization = highlighted_organization_title or result["organization"]["title"]

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
                sanitized_search_description = str(markdown_extract(search_description, extract_length=240))
                sanitized_search_description_list = []
                for substring in sanitized_search_description.split("[["):
                    if not substring:
                        continue
                    if "]]" in substring:
                        span_content, rest = substring.split("]]")
                        sanitized_search_description_list.append(Markup(f'<span class="dataset-search-highlight">{span_content}</span>'))
                        sanitized_search_description_list.append(markdown_extract(rest, extract_length=0))
                    else:
                        sanitized_search_description_list.append(markdown_extract(substring, extract_length=0))
                result["search_description"] = sanitized_search_description_list

        return search_results

    def after_dataset_create(self, ctx, package):
        timestamps.override(ctx, package)

    def after_dataset_update(self, ctx, package):
        timestamps.override(ctx, package)

    def after_resource_delete(self, ctx, resources):
        timestamps.set_to_now(ctx, resources)

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
                ]
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
                ("res_format", facets_dict["res_format"]),
                ("organization", facets_dict["organization"]),
                ("project_name", toolkit._("Projects")),
                # Entry type is disabled for now as the value is null for harvested datasets
                # The filter works, so enabling it will allow us to filter for datasets with
                # the field set, either by manual edit, script, or updates to harvester
                # ("entry_type", toolkit._("Type")),
                ("harvest_source_title", toolkit._("Sources")),
                ("license_id", facets_dict["license_id"]),
            ]
        )

    def organization_facets(self, facets_dict, *args):
        return facets_dict

    def group_facets(self, facets_dict, *args):
        return facets_dict
