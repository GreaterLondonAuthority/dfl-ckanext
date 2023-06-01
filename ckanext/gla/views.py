from flask import Blueprint

import ckan.model as model
import ckan.plugins.toolkit as tk

from typing import Any, Optional, Union, cast

import ckan.logic as logic
import ckan.lib.base as base
import ckan.lib.helpers as h
from ckan import authz
from ckan.common import _, g, current_user
from ckan.types import Context


favourites = Blueprint("favourites_blueprint", __name__)
users = Blueprint("users_blueprint", __name__)


def show_favourites():
    # If an unregistered user ends up on the /dataset/following page
    # show them a message saying that they need to create an account
    if not tk.g.userobj:
        return tk.render(
            "following.html",
            extra_vars={"unregistered": True},
        )

    context = {
        "model": model,
        "session": model.Session,
        "user": tk.g.user or tk.g.author,
        "for_view": True,
        "auth_user_obj": tk.g.userobj,
    }
    data_dict = {"id": tk.g.userobj.id}
    followed_datasets = tk.get_action("dataset_followee_list")(context, data_dict)
    return tk.render("following.html", extra_vars={"packages": followed_datasets})


favourites.add_url_rule(
    "/dataset/following",
    methods=["GET"],
    view_func=show_favourites,
    endpoint="show_favourites",
)

## Users routes:


# Copied from:
# https://github.com/ckan/ckan/blob/3c676e3cf1f075c5e9bae3b625b86247edf3cc1d/ckan/views/user.py#L60
# and edited to catch NotAuthorized and NotFound together and return
# a 403 error for both, to avoid disclosure of usernames through enumeration
def _extra_template_variables(
    context: Context, data_dict: dict[str, Any]
) -> dict[str, Any]:
    is_sysadmin = False
    if current_user.is_authenticated:
        is_sysadmin = authz.is_sysadmin(current_user.name)
    try:
        user_dict = tk.get_action("user_show")(context, data_dict)
    # Catch NotAuthorized and NotFound and return 403 for both:
    except (logic.NotAuthorized, logic.NotFound) as e:
        base.abort(403, _("Not authorized to see this page"))

    is_myself = user_dict["name"] == current_user.name
    about_formatted = h.render_markdown(user_dict["about"])
    extra: dict[str, Any] = {
        "is_sysadmin": is_sysadmin,
        "user_dict": user_dict,
        "is_myself": is_myself,
        "about_formatted": about_formatted,
    }
    return extra


# Copied from:
# https://github.com/ckan/ckan/blob/3c676e3cf1f075c5e9bae3b625b86247edf3cc1d/ckan/views/user.py#L124
def view_user(id):
    context = cast(
        Context,
        {
            "model": model,
            "session": model.Session,
            "user": current_user.name,
            "auth_user_obj": current_user,
            "for_view": True,
        },
    )
    data_dict: dict[str, Any] = {
        "id": id,
        "user_obj": current_user,
        "include_datasets": True,
        "include_num_followers": True,
    }
    # FIXME: line 331 in multilingual plugins expects facets to be defined.
    # any ideas?
    g.fields = []

    extra_vars = _extra_template_variables(context, data_dict)
    return base.render("user/read.html", extra_vars)


users.add_url_rule("/user/<id>", methods=["GET"], view_func=view_user)


def get_blueprints():
    return [favourites, users]
