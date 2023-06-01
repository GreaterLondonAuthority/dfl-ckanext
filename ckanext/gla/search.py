import ckan.plugins.toolkit as toolkit
import ckan.lib.search.common as common
from luqum.parser import parser
import luqum.tree as tree
import luqum.auto_head_tail as ht

auto_head_tail = ht.AutoHeadTail()

def _parse_query(query):
    if query == "" or query is None:
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
