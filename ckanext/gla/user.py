import ckan.lib.helpers as h
import ckan.model as model
from ckan.model.user import User
from ckan.model.group import Member, Group

import ckan.plugins.toolkit as toolkit
from ckan.common import logout_user, request
from ckan.types import Response
from ckan.views.user import RegisterView

import sqlalchemy as sa
from sqlalchemy.sql import exists


from . import email


class GlaRegisterView(RegisterView):
    def post(self) -> Response | str:
        super().post()

        # Send verification email and log the user out
        user_email = request.form.get("email")
        if user_email:
            user_obj = model.User.by_email(user_email)
            if user_obj:
                email.send_email_verification_link(user_obj)

        logout_user()

        h.flash_notice(
            "A verification email has been sent to your email address. Please click the link in the email to verify your email address."
        )

        return h.redirect_to("user.login")


@toolkit.chained_action
def user_create(original_action, context, data_dict):
    # Force username and email to be lower case
    data_dict["email"] = data_dict.get("email").lower()
    data_dict["name"] = data_dict.get("name").lower()
    result = original_action(context, data_dict)
    return result


@toolkit.chained_action
def user_list(original_action, context, data_dict):
    query = original_action(context, data_dict)
    
    # Modify the query to add the 'plugin_extras' field from the User model
    query = query.add_columns(User.plugin_extras)

    # Join with the Member table to find user memberships
    # query = query.join(Member, sa.and_(
    #     Member.table_id == sa.cast(User.id, sa.String),
    #     Member.table_name == 'user'
    # ))

    # Left join with the Member table to find user memberships, if any
    query = query.outerjoin(Member, sa.and_(
        Member.table_id == sa.cast(User.id, sa.String),
        Member.table_name == 'user'
    ))    

    
    # Join with the Group (organization) table
    query = query.outerjoin(Group, Group.id == Member.group_id)


    # Modify the query to return the user's plugin_extras and organization names
    query = query.add_columns(User.plugin_extras, Group.name.label('organization_name'))

    
    
    # Modify the query to add 'plugin_extras' and the boolean for organization membership
    # query = query.add_columns(User.plugin_extras, is_org_member)    
    
    # Return the modified query
    print(type(user_list))
    print(user_list)
    return query
