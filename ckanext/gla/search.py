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
    parsed_query = _parse_query(search_params.get("q"))
    boosted_query = tree.Plus(tree.Boost(parsed_query, 1))
    data_quality_search = tree.Boost(tree.SearchField("extras_data_quality", tree.Range(tree.Word("0"),tree.Word("5"),include_high=True,include_low=True)), 0.1)
    new_query = tree.OrOperation(boosted_query, data_quality_search)
    new_query = auto_head_tail(new_query)
    return {**search_params, "q": str(new_query)}

@toolkit.side_effect_free
def debug(context, data_dict={}):
    params = add_quality_to_search(data_dict)
    params.setdefault("df", "text")
    params.setdefault("q.op", "AND")
    params["debugQuery"] = "true"
    conn = common.make_connection()
    try:
        return conn.search(**params).__dict__
    except Exception as e:
        raise common.SearchError(e.args)

logfile = "search_logs.csv"

def _result_index(page, index_in_page):
    page_idx = 0 if _empty_or_none(page) else int(page) - 1
    return page_idx * 20 + int(index_in_page) + 1

@toolkit.side_effect_free
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
