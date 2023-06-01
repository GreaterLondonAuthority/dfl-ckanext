import ckan.plugins.toolkit as toolkit


def __page_context(request):
    page_info = {"source": "", "is_search": False}
    if request.view_args.get("is_organization"):
        page_info["source"] = "organization"
    else:
        page_info["source"] = "datasets"
    page_info["is_search"] = request.args.get("q") is not None
    return page_info


def __maybe_filter_by_organization(request, datasets):
    if __page_context(request)["source"] == "organization":
        org = request.view_args.get("id")
        return [x for x in datasets if x["dict"]["organization"]["name"] == org]
    else:
        return datasets


def followed(user, request):
    """Get a list of the users followed datasets"""
    if user == "":
        return []
    else:
        followed = toolkit.get_action("followee_list")(None, {"id": user.id})
        followed_datasets = [x for x in followed if x["type"] == "dataset"]
        return __maybe_filter_by_organization(request, followed_datasets)


def should_show_favourites(user, request):
    """Check the dataset page query params to see if we need to show
    the favourite datasets: they're only shown on the first page of items,
    if there is no search term"""
    if user == "" or __page_context(request)["is_search"]:
        return False
    else:
        page = request.args.get("page")
        return page is None or page == "1"


def remove_favourites(user, request, all_items):
    """Filter the list of datasets to exclude favourites shown
    on the top of the page if present"""
    if should_show_favourites(user, request):
        am_following_ds = toolkit.get_action("am_following_dataset")
        return [i for i in all_items if not am_following_ds(None, i)]
    else:
        return all_items


def last_updated(package):
    if "extras" in package.keys():
        for extra in package["extras"]:
            if extra["key"] == "upstream_metadata_modified":
                return extra["value"]
    return package.get("metadata_modified", "")


def get_helpers():
    return {
        "get_followed_datasets": followed,
        "remove_favourites": remove_favourites,
        "show_favourite_datasets": should_show_favourites,
        "last_updated": last_updated,
    }
