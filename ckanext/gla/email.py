from ckan import model
import ckan.lib.mailer as Mailer
from ckan.lib.base import render
from ckan.common import config

def get_reset_link_html_body(user: model.User) -> str:
    extra_vars = {
        'reset_link': Mailer.get_reset_link(user),
        'site_title': config.get('ckan.site_title'),
        'site_url': config.get('ckan.site_url'),
        'user_name': user.name,
    }
    return render('emails/reset_password.html', extra_vars)

# Override ckan's send_reset_link function to pass body_html into mail_user
# So that the password reset link email will be sent as multipart/alternative with both a plain text version and a html version
def send_reset_link(user: model.User) -> None:
    Mailer.create_reset_key(user)
    body = Mailer.get_reset_link_body(user)
    body_html = get_reset_link_html_body(user)
    extra_vars = {
        'site_title': config.get('ckan.site_title')
    }
    subject = render('emails/reset_password_subject.txt', extra_vars)

    # Make sure we only use the first line
    subject = subject.split('\n')[0]

    Mailer.mail_user(user, subject, body, body_html)