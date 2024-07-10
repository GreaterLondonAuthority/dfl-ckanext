from ckan.types import Schema
import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit

from . import auth, helpers, views, search, timestamps, custom_fields
from collections import OrderedDict


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
        if search_params.get("q", "") != "":
            fq = search_params.get("fq", "")
            search_params.update(
                {"fq": fq + " dataset_type:dataset || dataset_type:showcase"}
            )

        # Then add the quality parts to the search query:
        return search.add_quality_to_search(search_params)

    def after_dataset_create(self, ctx, package):
        timestamps.override(ctx, package)

    def after_dataset_update(self, ctx, package):
        timestamps.override(ctx, package)

    def after_resource_delete(self, ctx, resources):
        timestamps.set_to_now(ctx, resources)


    def after_dataset_search(self, search_results, search_params):
        for result in search_results['results']:
            result['total_file_size'] = sum(item['size'] for item in result['resources'] if item and item['size'] is not None)
 
        return search_results
        
    # ITemplateHelpers
    def get_helpers(self):
        return helpers.get_helpers()

    # IBlueprint
    def get_blueprint(self):
        return views.get_blueprints()

    # IActions
    def get_actions(self):
        return {"debug_dataset_search": search.debug,
                "log_chosen_search_result": search.log_selected_result}

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
        schema.update({
            field: [
                toolkit.get_converter("convert_from_extras"),
                toolkit.get_validator("ignore_missing"),
            ]
            for field in custom_fields.custom_dataset_fields.keys()})
        schema.update({
            "harvest_source_title":
            [
                toolkit.get_converter("convert_from_extras"),
                toolkit.get_validator("ignore_missing"),
            ]

        })
        return schema

    def is_fallback(self):
        return True

    def package_types(self) -> list[str]:
        return []

    # IFacets
    def dataset_facets(self, facets_dict, _):
        return OrderedDict([("res_format", facets_dict["res_format"]),
                               ("organization", facets_dict["organization"]),
                               ("project_name", toolkit._("Projects")),
                               ("private", toolkit._("private")),
                               # Entry type is disabled for now as the value is null for harvested datasets
                               # The filter works, so enabling it will allow us to filter for datasets with
                               # the field set, either by manual edit, script, or updates to harvester
                               # ("entry_type", toolkit._("Type")),
                               ("harvest_source_title", toolkit._("Sources")),
                               ("license_id", facets_dict["license_id"])])

    def organization_facets(self, facets_dict, *args):
        return facets_dict

    def group_facets(self, facets_dict, *args):
        return facets_dict
