import ckan.plugins.toolkit as toolkit
from ckan.lib.navl.dictization_functions import Invalid

def float_validator(value):
    """Ensures that the value is a float and rounds to 4dp."""
    try:
        value = float(value)
        return round(value,4)
    except:
        raise Invalid('Must be a number')

custom_dataset_fields = {
    "data_quality": [
        toolkit.get_validator("int_validator"),
        toolkit.get_validator("one_of")([None, 1, 2, 3, 4, 5]),
        toolkit.get_converter("convert_to_extras"),
    ],
    "dataset_boost": [
        float_validator,
        toolkit.get_converter("convert_to_extras")
    ]
}
