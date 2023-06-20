from ckan import authz
from ckan.common import current_user
import ckan.plugins.toolkit as toolkit
import ckan.lib.search.common as common
from collections import OrderedDict
import csv
from datetime import datetime
from luqum.parser import parser
import luqum.tree as tree
import luqum.auto_head_tail as ht
from os.path import exists

auto_head_tail = ht.AutoHeadTail()


# Set the amount by which the data quality field boosts a result
data_quality_boost_factor = 0.1

def _empty_or_none(string):
    return string == "" or string is None

def _parse_query(query):
    if _empty_or_none(query):
        query = "*:*"
    parsed = parser.parse(query)
    if isinstance(parsed, tree.Word):
        return tree.SearchField("text", parsed)
    else:
        return parsed

def add_quality_to_search(search_params):
    data_quality_boosts = [tree.Boost(tree.SearchField("extras_data_quality", tree.Term(str(quality))),
                                      data_quality_boost_factor * quality)
                           for quality in range(1, 6)]
    parsed_query = _parse_query(search_params.get("q"))
    boosted_query = tree.Plus(tree.Boost(parsed_query, 1))
    new_query = tree.OrOperation(boosted_query, *data_quality_boosts)
    new_query = auto_head_tail(new_query)
    return {**search_params, "q": str(new_query)}

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