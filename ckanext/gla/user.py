import ckan.plugins.toolkit as toolkit
from ckan.types import Response
from ckan.views.user import RegisterView


class GlaRegisterView(RegisterView):
    def post(self) -> Response | str:
        response = super().post()
        return response


@toolkit.chained_action
def user_create(original_action, context, data_dict):
    # Force username and email to be lower case
    data_dict["email"] = data_dict.get("email").lower()
    data_dict["name"] = data_dict.get("name").lower()
    result = original_action(context, data_dict)
    return result
