import dateutil.parser

import ckan.plugins.toolkit as tk


def override(ctx, package):
    """
    CKAN's dataset create/update method sets the metadata_created and
    metadata_modified fields to the current time, with no option to override
    them. We want to inherit the upstream fields when they exist, or set the
    dataset's last modified time to match the most recently updated resource.

    Uses the SQLAlchemy interface directly to update the metadata fields.
    """
    metadata_created = None
    metadata_modified = None

    for extra in package["extras"]:
        if extra["key"] == "upstream_metadata_created":
            metadata_created = dateutil.parser.parse(extra["value"])
        if extra["key"] == "upstream_metadata_modified":
            metadata_modified = dateutil.parser.parse(extra["value"])

    # If there's no upstream fields then this isn't a harvested dataset,
    # so set the last modified date based on the dataset's resources
    if metadata_created is None or metadata_modified is None:
        p = tk.get_action("package_show")(None, {"id": package["id"]})

        def resource_date(resource):
            return resource.get("last_modified") or resource.get("created")

        # For each of the dataset's resources, get the "last_modified" timestamp
        # or the "created" timestamp if that doesn't exist
        resource_modified_dates = [resource_date(r) for r in p["resources"]]

        # Sort the timestamps in descending order and get the first one
        most_recent = sorted(resource_modified_dates, reverse=True)[0]
        most_recent_datetime = dateutil.parser.parse(most_recent)
        updated_timestamps = {
            "metadata_modified": most_recent_datetime.replace(tzinfo=None)
        }
    else:
        updated_timestamps = {
            # CKAN assumes tzinfo is None (so that printed timestamps don't have
            # timezone specifiers on them) so strip timezone information.
            "metadata_created": metadata_created.replace(tzinfo=None),
            "metadata_modified": metadata_modified.replace(tzinfo=None),
        }

    model = ctx["model"]

    # Use SQLAlchemy directly to avoid re-triggering after_package_update:
    (
        model.Session.query(model.Package)
        .filter_by(id=package["id"])
        .update(updated_timestamps)
    )
