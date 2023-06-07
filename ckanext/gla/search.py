import ckan.plugins.toolkit as toolkit
import ckan.lib.search.common as common
from luqum.parser import parser
import luqum.tree as tree
import luqum.auto_head_tail as ht

auto_head_tail = ht.AutoHeadTail()

# Set the amount by which the data quality field boosts a result
data_quality_boost_factor = 0.1

def _parse_query(query):
    if query == "" or query is None:
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
    params = add_quality_to_search(data_dict)
    params.setdefault("df", "text")
    params.setdefault("q.op", "AND")
    params["debugQuery"] = "true"
    conn = common.make_connection()
    try:
        return conn.search(**params).__dict__
    except Exception as e:
        raise common.SearchError(e.args)
