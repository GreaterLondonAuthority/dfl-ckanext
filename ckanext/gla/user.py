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


import ckan.logic as logic
import ckan.lib.base as base
from ckan import authz
from ckan.common import (
    _, config, g, current_user, login_user
)

from typing import Any, Optional, Union
import ckan.lib.captcha as captcha
import ckan.lib.navl.dictization_functions as dictization_functions

class GlaRegisterView(RegisterView):
    # Code taken from:
    # https://github.com/ckan/ckan/blob/9915ba0022b9a74a65e61c097b2fee584b044087/ckan/views/user.py#L420-L476
    def post(self) -> Union[Response, str]:        
        context = self._prepare()
        try:
            data_dict = logic.clean_dict(
                dictization_functions.unflatten(
                    logic.tuplize_dict(logic.parse_params(request.form))))
            data_dict.update(logic.clean_dict(
                dictization_functions.unflatten(
                    logic.tuplize_dict(logic.parse_params(request.files)))
            ))

        except dictization_functions.DataError:
            base.abort(400, _(u'Integrity Error'))

        try:
            captcha.check_recaptcha(request)
        except captcha.CaptchaError:
            error_msg = _(u'Bad Captcha. Please try again.')
            h.flash_error(error_msg)
            return self.get(data_dict)

        try:
            user_dict = logic.get_action(u'user_create')(context, data_dict)
        except logic.NotAuthorized:
            base.abort(403, _(u'Unauthorized to create user %s') % u'')
        except logic.NotFound:
            base.abort(404, _(u'User not found'))
        except logic.ValidationError as e:
            errors = e.error_dict
            error_summary = e.error_summary
                
            return self.get(data_dict, errors, error_summary)

        user = current_user.name
        if user:
            # #1799 User has managed to register whilst logged in - warn user
            # they are not re-logged in as new user.
            h.flash_success(
                _(u'User "%s" is now registered but you are still '
                  u'logged in as "%s" from before') % (data_dict[u'name'],
                                                       user))
            if authz.is_sysadmin(user):
                # the sysadmin created a new user. We redirect him to the
                # activity page for the newly created user
                if "activity" in g.plugins:
                    return h.redirect_to(
                        u'activity.user_activity', id=data_dict[u'name'])
                return h.redirect_to(u'user.read', id=data_dict[u'name'])
            else:
                return base.render(u'user/logout_first.html')
        # log the user in programatically
        userobj = model.User.get(user_dict["id"])
        if userobj:
            login_user(userobj)
            rotate_token()
        resp = h.redirect_to(u'user.me')
        return resp    

    
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
