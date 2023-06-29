import dateutil.parser


def restore_upstream(ctx, package):
    """
    CKAN's dataset create/update method sets the metadata_created and
    metadata_modified fields to the current time, with no option to override
    them. We want to inherit the upstream fields, so patch them back to the
    upstream values after every change.

    Uses the SQLAlchemy interface directly to update the metadata fields.
    """
    metadata_created = None
    metadata_modified = None

    for extra in package["extras"]:
        if extra["key"] == "upstream_metadata_created":
            metadata_created = dateutil.parser.parse(extra["value"])
        if extra["key"] == "upstream_metadata_modified":
            metadata_modified = dateutil.parser.parse(extra["value"])

    if metadata_created is None or metadata_modified is None:
        return

    # CKAN assumes tzinfo is None (so that printed timestamps don't have
    # timezone specifiers on them) so strip timezone information.
    metadata_created = metadata_created.replace(tzinfo=None)
    metadata_modified = metadata_modified.replace(tzinfo=None)

    model = ctx["model"]

    (
        model.Session.query(model.Package)
        .filter_by(id=package["id"])
        .update(
            {
                "metadata_created": metadata_created,
                "metadata_modified": metadata_modified,
            }
        )
    )
