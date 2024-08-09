import re
from collections import OrderedDict
from typing import Any, Literal

import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
from ckan.lib.helpers import markdown_extract
from ckan.types import Schema
from markupsafe import Markup

from . import auth, custom_fields, helpers, search, timestamps, views
from .search_highlight import action, query

TABLE_FORMATS = [
    "csv",
    "xls",
    "xlsx",
    "xlsm",
    "tsv",
    "spreadsheet",
    "tab",
    "google-sheet",
]
REPORT_FORMATS = ["zip", "html", "htm", "pdf", "docx", "doc", "odw"]
GEOSPATIAL_FORMATS = ["geojson" "shp" "mbtiles" "kml"]


def _get_aggregate_res_format_query(
    category: Literal["table", "report", "geospatial"]
) -> str:
    if category == "table":
        query = " OR ".join([f'"{item}"' for item in TABLE_FORMATS])
    elif category == "report":
        query = " OR ".join([f'"{item}"' for item in REPORT_FORMATS])
    elif category == "geospatial":
        query = " OR ".join([f'"{item}"' for item in GEOSPATIAL_FORMATS])

    return f"res_format:{query}"


def _calculate_res_format_totals(search_results: dict[str, Any]):
    categories = {"items": []}

    tables_format_item = {
        "count": 0,
        "display_name": "Tables",
        "name": "table",
    }
    reports_format_item = {
        "count": 0,
        "display_name": "Reports",
        "name": "report",
    }
    geospatial_format_item = {
        "count": 0,
        "display_name": "Geospatial",
        "name": "geospatial",
    }

    skipped_formats = set()
    for format in search_results["search_facets"]["res_format"]["items"]:
        if format["name"].lower() in TABLE_FORMATS:
            tables_format_item["count"] += format["count"]
            continue
        if format["name"].lower() in REPORT_FORMATS:
            reports_format_item["count"] += format["count"]
            continue
        if format["name"].lower() in GEOSPATIAL_FORMATS:
            geospatial_format_item["count"] += format["count"]
            continue

        skipped_formats.add(format["name"].lower())
        categories["items"].append(format)

    if tables_format_item["count"] > 0:
        categories["items"].append(tables_format_item)
    if reports_format_item["count"] > 0:
        categories["items"].append(reports_format_item)
    if geospatial_format_item["count"] > 0:
        categories["items"].append(geospatial_format_item)

    return categories["items"]


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
                "hl.requireFieldMatch": "true",
                "hl.snippets": "1",
                "hl.fragsize": "200",
                "hl.bs.type": "SENTENCE",
                "hl.fl": "title,notes,search_description",
                "hl.simple.pre": "[[",
                "hl.simple.post": "]]",
                "hl.maxAnalyzedChars": "250000" # only highlight matches occuring in the first 250k characters of a field we increase this from SOLRs default of 51k because some datasets have long descriptions and highlighting wasn't displaying
            }
        )

        if "fq" in search_params:
            search_params["fq_list"] = []
            if 'res_format:"table"' in search_params["fq"]:
                search_params["fq"] = search_params["fq"].replace(
                    'res_format:"table"', ""
                )
                search_params["fq_list"].append(
                    _get_aggregate_res_format_query("table")
                )
            if 'res_format:"report"' in search_params["fq"]:
                search_params["fq"] = search_params["fq"].replace(
                    'res_format:"report"', ""
                )
                search_params["fq_list"].append(
                    _get_aggregate_res_format_query("report")
                )
            if 'res_format:"geospatial"' in search_params["fq"]:
                search_params["fq"] = search_params["fq"].replace(
                    'res_format:"geospatial"', ""
                )
                search_params["fq_list"].append(
                    _get_aggregate_res_format_query("geospatial")
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
            resources = result.get("resources", [])
            result["total_file_size"] = sum(
                item["size"] for item in resources if item and item["size"] is not None
            )
            result["number_of_files"] = len(resources)

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
                result["search_description"] = sanitized_search_description_list

        if "res_format" in search_results["search_facets"]:
            search_results["search_facets"]["res_format"]["items"] = (
                _calculate_res_format_totals(search_results)
            )

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
                ],
                "harvest_source_frequency": [
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
                ("res_format", facets_dict["res_format"]),
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
