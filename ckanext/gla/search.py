from ckan import authz
from ckan.common import current_user
import ckan.plugins.toolkit as toolkit
import ckan.lib.search.common as common
from collections import OrderedDict
import csv
from datetime import datetime
from os.path import exists
from urllib.parse import quote


# Set the amount by which the data quality field boosts a result
data_quality_boost_factor = 0.1

# Set the amount by which the "boost" field boosts a result - left this as 1 as this field
# is intended for admins to control the boost directly, but we can change it if needed.
dataset_boost_boost_factor = 1

def _empty_or_none(string):
    return string == "" or string is None

def add_quality_to_search(search_params):
    search_terms = search_params.get("q")
    if _empty_or_none(search_terms):
        q = "*:*"
    else:
        q = f"text:{quote(search_terms)}"
    query = f"{q} _val_:copy_data_quality^{data_quality_boost_factor} _val_:copy_dataset_boost^{dataset_boost_boost_factor}"

    return {**search_params,
            "q": query}

@toolkit.side_effect_free
def debug(context, data_dict={}):
    if not current_user.is_authenticated:
        raise toolkit.NotAuthorized()
    if not authz.is_sysadmin(current_user.name):
        raise toolkit.NotAuthorized()
    else:
        params = add_quality_to_search(data_dict)
        params.setdefault("df", "text")
        params.setdefault("q.op", "AND")
        params["debugQuery"] = "true"
        conn = common.make_connection()
        try:
            return conn.search(**params).__dict__
        except Exception as e:
            raise common.SearchError(e.args)

logfile = "/srv/app/search_logs.csv"

def _result_index(page, index_in_page):
    page_idx = 0 if _empty_or_none(page) else int(page) - 1
    from ckan.common import config
    return page_idx * config.get('ckan.datasets_per_page') + int(index_in_page)

@toolkit.auth_allow_anonymous_access
def log_selected_result(context, data_dict={}):
    data_to_log = {k: v for k, v in data_dict.items() if k not in ["page", "index", "is_search_result"]}
    data_to_log["index"] = _result_index(data_dict["page"], data_dict["index"])
    data_to_log["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    headers = ["time", "query", "sort", "org", "tags", "format", "licence", "package-id", "index"]
    if not exists(logfile.strip()):
        with open(logfile, "w") as f:
            csv.writer(f).writerow(headers)
    with open(logfile, "a") as f:
        csv.writer(f).writerow([data_to_log[k] for k in headers])