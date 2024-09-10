import logging
import re
import string
from typing import Any

import ckan.lib.navl.dictization_functions as df
import ckan.plugins.toolkit as tk
from ckan import authz, model
from ckan.common import _
from ckan.types import Context, FlattenDataDict, FlattenErrorDict, FlattenKey
from itsdangerous import URLSafeTimedSerializer

logger = logging.getLogger(__name__)


SECRET_KEY = tk.config.get("ckan.verification.security_key")
SECURITY_PASSWORD_SALT = tk.config.get("ckan.verification.security_password_salt")


def _requester_is_sysadmin(context):
    requester = context.get("user", None)
    return authz.is_sysadmin(requester)


def _requester_is_manager(context):
    requester = context.get("user", None)
    return authz.has_user_permission_for_some_org(requester, "manage_group")


def user_list(context, data_dict=None):
    """Only sysadmins should be allowed to view the full list of users"""
    return {
        "success": _requester_is_sysadmin(context) or _requester_is_manager(context)
    }


def user_show(context, data_dict=None):
    """sysadmins can view all user profiles.
    If not a sysadmin, a user can only view their own profile.
    Based on: https://github.com/qld-gov-au/ckanext-qgov/blob/master/ckanext/qgov/common/auth_functions.py#L126
    """
    if _requester_is_sysadmin(context) or _requester_is_manager(context):
        return {"success": True}
    requester = context.get("user")
    id = data_dict.get("id", None)
    if id:
        user_obj = model.User.get(id)
    else:
        user_obj = data_dict.get("user_obj", None)
    if user_obj:
        return {"success": requester in [user_obj.name, user_obj.id]}

    return {"success": False}


def has_consecutive_numbers(password_string):
    # Regular expression to find consecutive numbers
    pattern = r"(?=(\d)(\d)(\d))"
    matches = re.findall(pattern, password_string)

    for match in matches:
        # Convert the matched string to a list of integers
        numbers = list(map(int, match))

        # Check if they are consecutive
        if all(numbers[i] + 1 == numbers[i + 1] for i in range(len(numbers) - 1)):
            return True
    return False


def user_password_validator(
    key: FlattenKey, data: FlattenDataDict, errors: FlattenErrorDict, context: Context
) -> Any:
    """Ensures that password is safe enough."""
    value = data[key]

    if isinstance(value, df.Missing):
        pass
    elif not isinstance(value, str):
        errors[("password",)].append(_("Passwords must be strings"))
    elif value == "":
        pass
    if isinstance(value, str):
        if len(value) < 13:
            errors[("password",)].append(
                _("Your password must be 13 characters or longer")
            )

        rules = [
            any(x.isupper() for x in value),
            any(x.islower() for x in value),
            any(x.isdigit() for x in value),
            any(x in string.punctuation for x in value),
        ]

        if sum(rules) != 4:
            errors[("password",)].append(
                _(
                    "Your password must contain at least one of each of the following: upper case character, lower case character, number and a non alpha character (e.g. !$#,%)"
                )
            )

        if data.get(("name",)) and data[("name",)].lower() in value.lower():
            errors[("password",)].append(
                _("Your password shouldn't contain your username")
            )

        if data.get(("fullname",)) and data[("fullname",)].lower() in value.lower():
            errors[("password",)].append(
                _("Your password shouldn't contain your full name")
            )

        if isinstance(value, str) and has_consecutive_numbers(value):
            errors[("password",)].append(
                _("Your password must not contain consecutive numbers such as '123'")
            )

        for password_char in value:
            if password_char * 3 in value:
                errors[("password",)].append(
                    _(
                        'Your password must not contain repeating characters such as "aaa"'
                    )
                )


def generate_token(email: str) -> str:
    serializer = URLSafeTimedSerializer(SECRET_KEY)
    return serializer.dumps(email, salt=SECURITY_PASSWORD_SALT)


def verify_user(token, expiration=86400) -> str:
    serializer = URLSafeTimedSerializer(SECRET_KEY)

    try:
        email = serializer.loads(token, salt=SECURITY_PASSWORD_SALT, max_age=expiration)
        user_obj = model.User.by_email(email.lower())

        if not user_obj:
            raise Exception("User not found")

        if not user_obj.plugin_extras:
            user_obj.plugin_extras = {"gla": {"verified_email": email.lower()}}
        else:
            user_obj.plugin_extras["gla"]["verified_email"] = email.lower()

        user_obj.save()

        return email
    except Exception as e:
        logger.error(e)
        return None


def is_email_verified(user_obj: model.User) -> bool:
    if user_obj.plugin_extras:
        return (
            user_obj.plugin_extras.get("gla", {}).get("verified_email", False)
            == user_obj.email.lower()
        )
    else:
        return False
