from ckan.types import Schema
import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit

from . import auth, helpers, views, search, timestamps, custom_fields


class GlaPlugin(plugins.SingletonPlugin, toolkit.DefaultDatasetForm):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IAuthFunctions, inherit=True)
    plugins.implements(plugins.IPackageController, inherit=True)
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
        custom_fields.add_copy_fields()

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
        timestamps.restore_upstream(ctx, package)

    def after_dataset_update(self, ctx, package):
        timestamps.restore_upstream(ctx, package)

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
        facets_dict["project_name"] = toolkit._("Project name")
        facets_dict["entry_type"] = toolkit._("Type")
        facets_dict["harvest_source_title"] = toolkit._("Source")
        return facets_dict
