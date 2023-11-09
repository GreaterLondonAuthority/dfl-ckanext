import ckan.plugins.toolkit as toolkit
from ckan.lib.navl.dictization_functions import Invalid
import requests
import json
import os


solr_endpoint = os.getenv("CKAN_SOLR_URL")


def float_validator(value):
    """Ensures that the value is a float and rounds to 4dp."""
    try:
        value = float(value)
        return round(value, 4)
    except:
        raise Invalid("Must be a number")


custom_dataset_fields = {
    "archived": [
        toolkit.get_validator("boolean_validator"),
        toolkit.get_converter("convert_to_extras"),
    ],
    "archived_description": [
        toolkit.get_validator("ignore_missing"),
        toolkit.get_converter("convert_to_extras"),
    ],
    "data_quality": [
        toolkit.get_validator("int_validator"),
        toolkit.get_validator("one_of")([None, 1, 2, 3, 4, 5]),
        toolkit.get_converter("convert_to_extras"),
    ],
    "dataset_boost": [float_validator, toolkit.get_converter("convert_to_extras")],
}


fields_to_copy = {
    "extras_data_quality": {"type": "int", "name": "copy_data_quality"},
    "extras_dataset_boost": {"type": "double", "name": "copy_dataset_boost"},
}


def field_exists(field_name):
    api_url = f"{solr_endpoint}/schema/fields/{field_name}"
    response = requests.head(api_url)
    if response.status_code == 200:
        return True
    elif response.status_code == 404:
        return False
    else:
        raise Exception("An error occurred while checking the field.")

def add_field(field_name, field_type):
    api_url = f"{solr_endpoint}/schema/fields"
    field_config = {
        "add-field": {
            "name": field_name,
            "type": field_type,
            "stored": "true",
            "indexed": "true"
        }
    }
    response = requests.post(api_url, json=field_config)
    response_json = response.json()
    if not response.status_code == 200 and response_json.get("responseHeader", {}).get("status", -1) == 0:
        raise Exception("Failed to add field", {"name": field_name, "error": response_json})

def add_copy_field(from_field, to_field):
    copy_field_config = {
        "add-copy-field": {
            "source": from_field,
            "dest": [to_field]
        }
    }
    api_url = f"{solr_endpoint}/schema"
    response = requests.post(api_url, json=copy_field_config)
    response_json = response.json()
    if not response.status_code == 200 and response_json.get("responseHeader", {}).get("status", -1) == 0:
        print("Copy field added successfully!")
        raise Exception("Failed to add copy field", {"config": copy_field_config,
                                                     "error": response_json})

def add_copy_fields():
    for field, new_field_conf in fields_to_copy.items():
        new_field = new_field_conf["name"]
        if not field_exists(new_field):
            add_field(new_field, new_field_conf["type"])
            add_copy_field(field, new_field)
