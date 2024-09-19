import ckan.lib.helpers as h
import ckan.lib.dictization.model_dictize as model_dictize
import ckan.model as model
from ckan.model.user import User
from ckan.model.group import Member, Group
from ckan.model.package import PackageMember

import ckan.plugins.toolkit as toolkit
from ckan.types import ActionResult

from ckan.common import asbool, logout_user, request
from ckan.types import Response
from ckan.views.user import RegisterView

import sqlalchemy as sa
from sqlalchemy.sql import exists

from .auth import is_email_verified
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
    query = original_action(context | {'return_query': True}, data_dict)

    # Modify CKAN query to return extra information to assist admins in auditing users
    is_org_member = sa.case(
        [(sa.exists().where(sa.and_(
            Member.table_id == sa.cast(User.id, sa.String),
            Member.table_name == 'user',
            Member.state == 'active',            
            Member.group_id.isnot(None)            
        )), True)], else_=False).label('is_organization_member')

    is_collaborator = sa.case(
        [(sa.exists().where(sa.and_(        
            PackageMember.user_id == sa.cast(User.id, sa.String),
            PackageMember.capacity == 'member',
            PackageMember.package_id.isnot(None)
        )), True)], else_=False).label('is_collaborator')

    
    query = query.add_columns(User.sysadmin, User.plugin_extras, is_org_member, is_collaborator)    

    if context.get('return_query'):
        return query
    else:
        # an API request so run query and dictize results
        users_list: ActionResult.UserList = []
        all_fields = asbool(data_dict.get('all_fields', None))
        
        for user in query.all():                
            result_dict = model_dictize.user_dictize(user[0], context)
            result_dict['is_collaborator'] = user.is_collaborator
            result_dict['is_email_verified'] = is_email_verified(user)
            result_dict['is_organization_member'] = user.is_organization_member
            
            users_list.append(result_dict)
        
        return users_list
