import logging
from typing import Any, Optional, cast

import pysolr
from ckan.common import asbool, config
from ckan.lib.search import _QUERIES
from ckan.lib.search.common import (SearchError, SearchQueryError,
                                    make_connection)
from ckan.lib.search.query import (QUERY_FIELDS, VALID_SOLR_PARAMETERS,
                                   PackageSearchQuery, solr_literal)
from werkzeug.datastructures import MultiDict

log = logging.getLogger(__name__)

VALID_SOLR_PARAMETERS.update(
    ["hl", "hl.fl", "hl.fragsize", "hl.simple.pre", "hl.simple.post", "hl.method", "hl.fragsizeIsMinimum"]
)


class PatchedPackageSearchQuery(PackageSearchQuery):
    def run(
        self,
        query: dict[str, Any],
        permission_labels: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Performs a dataset search using the given query.

        :param query: dictionary with keys like: q, fq, sort, rows, facet
        :type query: dict
        :param permission_labels: filter results to those that include at
            least one of these labels. None to not filter (return everything)
        :type permission_labels: list of unicode strings; or None

        :returns: dictionary with keys results and count

        May raise SearchQueryError or SearchError.
        """
        assert isinstance(query, (dict, MultiDict))
        # check that query keys are valid
        if not set(query.keys()) <= VALID_SOLR_PARAMETERS:
            invalid_params = [s for s in set(query.keys()) - VALID_SOLR_PARAMETERS]
            raise SearchQueryError("Invalid search parameters: %s" % invalid_params)

        # default query is to return all documents
        q = query.get("q")
        if not q or q == '""' or q == "''":
            query["q"] = "*:*"

        # number of results
        rows_to_return = int(query.get("rows", 10))
        # query['rows'] should be a defaulted int, due to schema, but make
        # certain, for legacy tests
        if rows_to_return > 0:
            # #1683 Work around problem of last result being out of order
            #       in SOLR 1.4
            rows_to_query = rows_to_return + 1
        else:
            rows_to_query = rows_to_return
        query["rows"] = rows_to_query

        fq = []
        if "fq" in query:
            fq.append(query["fq"])
        fq.extend(query.get("fq_list", []))

        # show only results from this CKAN instance
        fq.append("+site_id:%s" % solr_literal(config.get("ckan.site_id")))

        # filter for package status
        if not "+state:" in query.get("fq", ""):
            fq.append("+state:active")

        # only return things we should be able to see
        if permission_labels is not None:
            fq.append(
                "+permission_labels:(%s)"
                % " OR ".join(solr_literal(p) for p in permission_labels)
            )
        query["fq"] = fq

        # faceting
        query["facet"] = query.get("facet", "true")
        query["facet.limit"] = query.get(
            "facet.limit", config.get("search.facets.limit")
        )
        query["facet.mincount"] = query.get("facet.mincount", 1)

        # return the package ID and search scores
        query["fl"] = query.get("fl", "name")

        # return results as json encoded string
        query["wt"] = query.get("wt", "json")

        # If the query has a colon in it then consider it a fielded search and do use dismax.
        defType = query.get("defType", "dismax")
        if ":" not in query["q"] or defType == "edismax":
            query["defType"] = defType
            query["tie"] = query.get("tie", "0.1")
            # this minimum match is explained
            # http://wiki.apache.org/solr/DisMaxQParserPlugin#mm_.28Minimum_.27Should.27_Match.29
            query["mm"] = query.get("mm", "2<-1 5<80%")
            query["qf"] = query.get("qf", QUERY_FIELDS)

        query.setdefault("df", "text")
        query.setdefault("q.op", "AND")
        try:
            if query["q"].startswith("{!"):
                raise SearchError("Local parameters are not supported.")
        except KeyError:
            pass

        conn = make_connection(decode_dates=False)
        log.debug("Package query: %r" % query)
        try:
            solr_response = conn.search(**query)
        except pysolr.SolrError as e:
            # Error with the sort parameter.  You see slightly different
            # error messages depending on whether the SOLR JSON comes back
            # or Jetty gets in the way converting it to HTML - not sure why
            #
            if e.args and isinstance(e.args[0], str):
                if (
                    "Can't determine a Sort Order" in e.args[0]
                    or "Can't determine Sort Order" in e.args[0]
                    or "Unknown sort order" in e.args[0]
                ):
                    raise SearchQueryError('Invalid "sort" parameter')
            raise SearchError(
                "SOLR returned an error running query: %r Error: %r" % (query, e)
            )
        self.count = solr_response.hits
        self.results = cast("list[Any]", solr_response.docs)

        # #1683 Filter out the last row that is sometimes out of order
        self.results = self.results[:rows_to_return]

        # get any extras and add to 'extras' dict
        for result in self.results:
            extra_keys = filter(lambda x: x.startswith("extras_"), result.keys())
            extras = {}
            for extra_key in list(extra_keys):
                value = result.pop(extra_key)
                extras[extra_key[len("extras_") :]] = value
            if extra_keys:
                result["extras"] = extras

        # if just fetching the id or name, return a list instead of a dict
        if query.get("fl") in ["id", "name"]:
            self.results = [r.get(query["fl"]) for r in self.results]

        # get facets and convert facets list to a dict
        self.facets = solr_response.facets.get("facet_fields", {})
        for field, values in self.facets.items():
            self.facets[field] = dict(zip(values[0::2], values[1::2]))

        # Get Solr highlighting
        self.highlighting = solr_response.highlighting

        return {"results": self.results, "count": self.count}


_QUERIES["package"] = PatchedPackageSearchQuery
