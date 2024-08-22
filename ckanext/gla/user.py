import ckan.plugins.toolkit as toolkit

@toolkit.chained_action
def user_create(original_action, context, data_dict):
    # Force username and email to be lower case
    data_dict['email'] = data_dict.get("email").lower()
    data_dict['name'] = data_dict.get('name').lower()
    return original_action(context, data_dict)