import csv
from collections import OrderedDict
from datetime import datetime
from os.path import exists
from urllib.parse import quote

import ckan.lib.search.common as common
import ckan.plugins.toolkit as toolkit
from ckan import authz
from ckan.common import current_user

# Set the amount by which the data quality field boosts a result
data_quality_boost_factor = 0.1

# Set the amount by which the "boost" field boosts a result - left this as 1 as this field
# is intended for admins to control the boost directly, but we can change it if needed.
dataset_boost_boost_factor = 1

def _empty_or_none(string):
    return string == "" or string is None

def query_fields(search_params):
    if '"' in search_params.get('q',''):
        # If the query contains any text inside quotes search the
        # fields that are unstemmed, and have synonym expansion
        # disabled.
        #
        # NOTE: This is a brute force approach as it essentially
        #       disables synonyms and stemming across the whole query,
        #       not just the phrase portion.
        #
        #       Unfortunately due to how query analysis happens in
        #       SOLR and the dismax/edismax parsers we couldn't find a
        #       way to implement this more precisely, such that the
        #       phrase variants of fields were used only on the quoted
        #       portions of the query; without significantly rewriting
        #       how SOLR queries are generated.
        #
        #       Methods tried were with both dismax/edismax and using
        #       the pf/ps/sow/qf parameters. Similarly constructing
        #       queries targeting specific fields was tried too e.g.
        #       title:hospitality (which unfortunately is synonym
        #       expanded incorrectly by edismax to be an AND query not
        #       a localised OR).
        #
        return "title_phrase^4 search_description_phrase^2 notes_phrase" # limit matching of text queries to agreed fields
    else: 
        return "title^4 search_description^2 notes" # limit matching of text queries to agreed fields

def add_quality_to_search(search_params):
    return {**search_params
            # NOTE the bf parameter adds these additional boosts into
            # the query/results. There are two numeric fields stored
            # in our dataset records which admins can adjust to
            # influence a datasets ranking
            #
            # These fields are weighted by the appropriate boost
            # factors, and the computed boost is added via addition to
            # the relevance score. It may be better in the future to
            # move this to a multiplicative boosting approach, as the
            # boosts will then become a function of text-match
            # relevance, rather than being universally applied.
            #
            # A good article on the subject is here:
            #
            # https://nolanlawson.com/2012/06/02/comparing-boost-methods-in-solr/
            # 
            ,"bf": f"copy_data_quality^{data_quality_boost_factor} copy_dataset_boost^{dataset_boost_boost_factor}"

            # NOTE
            #
            # The query field settings shown below are the CKAN
            # defaults. If in the future it becomes desirable to tweak
            # the importance of these fields for relevance, this line
            # can be uncommented and the values can be changed.
            #
            # Note also that the text field contains a large amount of
            # metadata copied from other fields in a stemmed form.
            #
            #,"qf":"name^4 title^4 tags^2 groups^2 text" # CKAN Defaults
            ,"qf":query_fields(search_params) # limit matching of text queries to agreed fields
            }

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

logfile = "/logs/search_logs.csv"

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
