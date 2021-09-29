## author: Bill Duncan
## summary: Contians methods for transforming data in NMDC ETL pipeline.

## add ./lib and rooth directory to sys.path so that local modules can be found
import os, sys, git_root
from datetime import datetime

sys.path.append(os.path.abspath("."))
sys.path.append(os.path.abspath("./lib"))
sys.path.append(git_root.git_root("./schema"))
# print(sys.path)

## system level modules
import pandas as pds
import jsonasobj
import json
import jq
import io
import pkgutil
import zipfile
import yaml
from yaml import CLoader as Loader, CDumper as Dumper
from dotted_dict import DottedDict
from collections import namedtuple
import nmdc_dataframes

## add all classes for local nmdc.py
## this is the file of python classes generated by linkml
from nmdc_schema import nmdc


def has_raw_value(obj, attribute: str) -> bool:
    """
    Helper function that returns True/False if a an object attribute
    has a has_raw_value property.
    E.g.: "lat_lon": {"has_raw_value": "-33.460524 150.168149"}

    Args:
        obj (dict or object):
        attribute (string): the name of the attribute in obj to check.

    Returns:
        boolean: True if haw_raw_value property is present.
    """

    val = getattr(obj, attribute)  # get value of object

    if val is None:  # check that value exists
        return False

    ## if val is a dict, check that it has a has_raw_value key
    ## and that the value is not null
    if type(val) == type({}):
        if "has_raw_value" in val.keys():
            return pds.notnull(val["has_raw_value"])
        else:
            return False

    ## if val is not a dict, assume it is a class
    ## and check has_raw_value
    obj_vars = vars(val)
    if "has_raw_value" in obj_vars.keys():
        return pds.notnull(obj_vars["has_raw_value"])
    else:
        return False


def record_has_field(nmdc_record: namedtuple, attribute_field: str) -> bool:
    """
    Returns True/False if a field is in nmdc_record (a namedtuple).

     Args:
        nmdc_record (namedtuple): the nmdc record
        attribute_field (string): the name of the attribute

    Returns:
        bool: True if the record has the field.
    """
    if pds.isnull(nmdc_record):
        return None

    if "," in attribute_field:  # e.g., "file_size_bytes, int"
        field = attribute_field.split(",")[0].strip()
    else:  # default to string datatype
        field = attribute_field.strip()

    return field in nmdc_record._fields


def coerce_value(value, dtype: str):
    """
    Coerces value into the type specified by dtype and returns the coerced value.

    Args:
        value: the value to coerece
        dtype (str): the data type to coerce/cast value into

    Returns:
        the value cast into the data type specified by dtype
    """
    if value is None:
        return None

    if dtype != "str":  # only do the eval when it is not a string
        return eval(f"""{dtype}({value})""")  # convert value to specified datatype
    else:
        return f"""{value}"""


def get_dtype_from_attribute_field(attribute_field) -> str:
    """
    Return data type part of attribute_field (e.g. 'file_size, int').
    If no dtype is given, "str" is returned.

    Args:
        attribute_field: the attribute field to get the data type from

    Returns:
        str: the string representation of the attribute field's data type
    """
    if type(attribute_field) == type({}):
        if "$const" in attribute_field.keys():
            ## NB: RECURSIVE CALL
            dtype = get_dtype_from_attribute_field(attribute_field["$const"])
        else:
            dtype = "str"
    elif "," in attribute_field:  # e.g., "file_size_bytes, int"
        dtype = attribute_field.split(",")[1].strip()
    else:  # default to string datatype
        dtype = "str"

    return dtype


def get_field_and_dtype_from_attribute_field(attribute_field) -> tuple:
    """
    Returns both the field and data type parts of attribute_field (e.g. 'file_size, int').
    If no dtype is given, a dtype of "str" is returned.

     Args:
        attribute_field: the name of the attribute field

    Returns:
        tuple: contains the (field, data type)
    """
    if type(attribute_field) == type({}):
        if "$const" in attribute_field.keys():
            ## NB: RECURSIVE CALL
            field, dtype = get_field_and_dtype_from_attribute_field(
                attribute_field["$const"]
            )
        elif "$field" in attribute_field.keys():
            ## NB: RECURSIVE CALL
            field, dtype = get_field_and_dtype_from_attribute_field(
                attribute_field["$field"]
            )
        else:
            field, dtype = attribute_field, "str"
    elif "," in attribute_field:  # e.g., "file_size_bytes, int"
        field, dtype = attribute_field.split(",")
        field, dtype = field.strip(), dtype.strip()
    else:  # default to string datatype
        field, dtype = attribute_field.strip(), "str"

    return field, dtype


def get_record_attr(record: namedtuple, attribute_field, return_field_if_none=True):
    """
    Returns the value specified by attribute_field in the record.
    E.g., get_record_attr(Record(id='gold:001', name='foo'), 'id') would return 'gold:001'.

    In some cases, the attribure_field may used for constant value (e.g., unit: meter).
    In these case the return_field_if_none (default True), specifies whether to return the
    constant value (e.g., return 'meter' instead of None)

    Args:
        record (namedtuple): the record containing the data
        attribute_field: the name of the field that contains the data
        return_field_if_none (bool, optional): Defaults to True.

    Returns:
        the value of record's field
    """
    ## check for constant
    if type({}) == type(attribute_field) and "$const" in attribute_field.keys():
        field, dtype = get_field_and_dtype_from_attribute_field(
            attribute_field["$const"]
        )
        return coerce_value(field, dtype)

    ## get field name and data type
    field, dtype = get_field_and_dtype_from_attribute_field(attribute_field)

    ## get value from record
    if record_has_field(record, field):  # check field
        val = getattr(record, field)
    else:  #### ********** Return value of field or None ******************* #######
        val = field if return_field_if_none else None

    if pds.notnull(val):
        return coerce_value(val, dtype)
    else:
        return None


def make_constructor_args_from_record(
    constructor_map: dict, nmdc_record: namedtuple
) -> dict:
    """
    Returns the constructor arguments as a dict that are needed to build an object.
    E.g., If the constructor map specifies that a Study object requires an id and name in
    the constructor, this function would return {id: gold:001, name: foo}.

    Args:
        constructor_map (dict): the arguments specified to build an object
        nmdc_record (namedtuple): holds the data that is used to build an object

    Returns:
        dict: the constructor arguments needed to build the object
    """
    ## for every mapping between a key and data field create a dict
    ## of the parameters needed to instantiate the class
    constructor_dict = {}
    for key, field in constructor_map.items():
        ## if the fields is a dict, constructor param takes an object
        ## e.g., {'latitude': 'latitude', 'longitude': 'longitude', 'has_raw_value': 'lat_lon', '$class_type': 'GeolocationValue'}
        if type({}) == type(field) and len(field) > 0:
            ## get values from the nmdc record for each field name
            record_dict = make_record_dict(nmdc_record, field)
            ## find constructors defined by the initialization key
            if "$class_type" in field.keys():
                class_type = make_nmdc_class(field["$class_type"])  # get class type

                ## update constructor dict
                constructor_dict[key] = class_type(**record_dict)
            else:
                constructor_dict[key] = record_dict
        elif type([]) == type(field) and len(field) > 0:
            constructor_dict[key] = [get_record_attr(nmdc_record, f) for f in field]
        else:
            constructor_dict[key] = get_record_attr(nmdc_record, field)

    return constructor_dict


def make_dict_from_nmdc_obj(nmdc_obj) -> dict:
    """
    Returns a dict based on the nmdc_obj.

    Args:
        nmdc_obj: an object containing nmdc data

    Returns:
        dict: representation of the object
    """

    def is_value(variable):
        """
        Checks if variable has a value. Returns True if:
        - variable is not None and
        - has length > 0 if variable is a list and dict and
        - has an id and/or has raw value key if variable is a dict
        """
        ## check if variable is None
        if variable is None:
            return False

        ## check for zero len variable
        if (
            type([]) == type(variable)
            or type({}) == type(variable)
            or type("") == type(variable)
        ):
            if len(variable) == 0:
                return False
        else:
            if pds.isnull(variable):
                return False  ## check for null

        ## if variable is a dict, make sure it has an id or raw value
        if type({}) == type(variable):
            if "id" in variable.keys():
                return is_value(variable["id"])  # check if id has a value
            elif "has_raw_value" in variable.keys():
                return is_value(
                    variable["has_raw_value"]
                )  # check if has_raw_value has a value
            else:
                return False  # if it makes it here, there wasn't an id or has_raw_value

        return True  # if it makes it here, all good

    def make_dict(obj):
        """
        Transforms an nmdc object into a dict
        """
        if obj == None:
            return  # make sure the object has a value

        ## check if obj can convert to dict
        if not hasattr(obj, "_as_dict"):
            return obj

        # temp_dict = jsonasobj.as_dict(obj) # convert obj dict
        temp_dict = {}
        obj_dict = {}

        ## include only valid values in lists and dicts
        for key, val in jsonasobj.as_dict(obj).items():
            # print('key:', key, '\n', ' val:', val, '\n')
            if type({}) == type(val):  # check values in dict
                temp_dict[key] = {k: v for k, v in val.items() if is_value(v)}
            elif type([]) == type(val):  # check values in list
                temp_dict[key] = [element for element in val if is_value(element)]
            else:
                temp_dict[key] = val

        ## check for {} or [] that may resulted from prevous loop
        for key, val in temp_dict.items():
            if is_value(val):
                obj_dict[key] = val

        return obj_dict

    if type([]) == type(nmdc_obj):
        # print('nndc_obj:', nmdc_obj)
        nmdc_dict = [make_dict(o) for o in nmdc_obj if is_value(o)]
        # print('nmdc_dict:', nmdc_dict)
    else:
        nmdc_dict = make_dict(nmdc_obj)

    return nmdc_dict

    def make_dict(obj):
        """
        transforms an nmdc object into a dict
        """
        if obj == None:
            return  # make sure the object has a value

        ## check if obj can convert to dict
        if not hasattr(obj, "_as_dict"):
            return obj

        # temp_dict = jsonasobj.as_dict(obj) # convert obj dict
        temp_dict = {}
        obj_dict = {}

        ## include only valid values in lists and dicts
        for key, val in jsonasobj.as_dict(obj).items():
            # print('key:', key, '\n', ' val:', val, '\n')
            if type({}) == type(val):  # check values in dict
                temp_dict[key] = {k: v for k, v in val.items() if is_value(v)}
            elif type([]) == type(val):  # check values in list
                temp_dict[key] = [element for element in val if is_value(element)]
            else:
                temp_dict[key] = val

        ## check for {} or [] that may resulted from prevous loop
        for key, val in temp_dict.items():
            if is_value(val):
                obj_dict[key] = val

        return obj_dict

    if type([]) == type(nmdc_obj):
        # print('nndc_obj:', nmdc_obj)
        nmdc_dict = [make_dict(o) for o in nmdc_obj if is_value(o)]
        # print('nmdc_dict:', nmdc_dict)
    else:
        nmdc_dict = make_dict(nmdc_obj)

    return nmdc_dict


def set_nmdc_object(
    nmdc_obj, nmdc_record: namedtuple, attribute_map: dict, attribute_field
):
    """
    Sets the properties of nmdc_obj using the values stored in the nmdc_record.
    The update nmdc_obj is returned.

    Args:
        nmdc_obj: the nmdc object that will modified
        nmdc_record (namedtuple): the record who's data will be used to set the values of the nmdc_obj
        attribute_map (dict): a dict/map based on the sssom file used to update the object's field
        attribute_field: the nmdc_obj's field to be set

    Returns:
        updated nmdc_obj
    """
    ## by default property values are represented as dicts
    ## the exception is when an value is created using '$class_type'
    ## e.g. {latitude': 'latitude', 'longitude': 'longitude', 'has_raw_value': 'lat_lon', '$class_type': 'GeolocationValue'}
    ## when '$class_type' is used the represent as dict flag is changed
    represent_as_dict = True

    ## check if attribute is a dict; e.g. part_of: gold_study_id
    if type({}) == type(attribute_field):
        ## get the field and value parts from dict
        field, val = list(attribute_field.items())[0]
        if type([]) == type(val):
            ## e.g. has_output: ["data_object_id, str"]
            av = make_object_from_list(nmdc_record, val)
        elif type({}) == type(val):
            ## # e.g. has_output: {id: gold:0001, name: 'foo', $class_type: Study}
            ## check if the av needs to be represented as an object
            if "$class_type" in val.keys():
                represent_as_dict = False
            av = make_object_from_dict(nmdc_record, val)  # val is a dict
        elif type("") == type(val):
            # e.g. has_output: "data_object_id, str" (not a list)
            av = get_record_attr(nmdc_record, val)
        else:
            ## val names the field in the record
            av = make_attribute_value_from_record(nmdc_record, val)
    elif type("") == type(attribute_field):
        if "," in attribute_field:
            ## e.g., "file_size_bytes, int"
            field = attribute_field.split(",")[0].strip()
        else:
            field = attribute_field.strip()

        av = get_record_attr(nmdc_record, attribute_field)
    else:
        field = attribute_field
        av = make_attribute_value_from_record(nmdc_record, field)

    ## convert attribute value into a dict
    if represent_as_dict == True:
        av = make_dict_from_nmdc_obj(av)

    ## check if attribute has been mapped in the sssom file
    if (len(attribute_map) > 0) and (field in attribute_map.keys()):
        setattr(nmdc_obj, attribute_map[field], av)
    else:
        setattr(nmdc_obj, field, av)

    return nmdc_obj


def make_attribute_value_from_record(nmdc_record: namedtuple, field, object_type=""):
    """
    Creates an attribute value object linked the value in the nmdc record's field.

     Args:
        nmdc_record (namedtuple): holds the data
        field: the field to get the data from
        object_type (str, optional): used to specify the type of object retured; defaults to ""

    Returns:
        an attribute value object (by default) with the has_raw_value property set to value in field
    """
    # val = getattr(nmdc_record, field)
    val = get_record_attr(nmdc_record, field)
    av = make_attribute_value(val, object_type)

    return av


def make_attribute_map(sssom_map_file: str = "") -> dict:
    """
    Retuns a dict based on the SSSOM mapping.
    By default the SSSOM mappping comes from the nmdc-schema package,
    but an optional path to an SSSOM formed tsv may be used.

     Args:
        sssom_map_file (str): an optional path to the sssom file

    Returns:
        dict: map relating the subject to the object where there is a skos:exactMatch
    """
    attr_map = {}
    if len(sssom_map_file) > 0:
        ## load sssom mapping file and subset to skos:exactMatch
        mapping_df = nmdc_dataframes.make_dataframe(
            sssom_map_file, comment_str="#"
        ).query("predicate_id == 'skos:exactMatch'")
    else:
        sssom = io.BytesIO(pkgutil.get_data("nmdc_schema", "gold-to-mixs.sssom.tsv"))
        mapping_df = pds.read_csv(sssom, sep="\t", comment="#", encoding="utf-8")

    attr_map = {
        subj: obj
        for idx, subj, obj in mapping_df[["subject_label", "object_label"]].itertuples()
    }  # build attribute dict

    return attr_map


def make_attribute_value(val):
    """
    Creates an attribute value object that has_raw_value val.

    Args:
        val: the value that is set as the value of has_raw_value

    Returns:
        attribute value object that has_raw_value val
    """
    av = nmdc.AttributeValue()
    if pds.notnull(val):
        av.has_raw_value = val

    return av


def make_nmdc_class(class_type):
    """
    Returns the NMDC class from the NMDC module as specified by class_type.

    Args:
        class_type: they type of class to return

    Returns:
        the specfied class reference (not string) that can be used to build an object
    """
    ## check if the class type is being passed as a string e.g., '$class_type': 'GeolocationValue'
    if type("") == type(class_type):
        class_type = getattr(nmdc, class_type)
    return class_type


def make_record_dict(
    nmdc_record: namedtuple, object_dict: dict, return_field_if_none=True
) -> dict:
    """
    Transforms nmdc_record into a dict in which the record field/properties are the keys.

    Args:
        nmdc_record (namedtuple): the record/tuple that holds the data
        object_dict (dict): holds the specificaion of fields to get data from
        return_field_if_none (bool, optional): defaults to True;
            speficies return type if field doesn't have any data
            this is useful returning constants; e.g: depth {has_unit: meter} will return
            'meter' for the has_unit property even though 'has_unit' is not a field in the record

    Returns:
        dict: a dict representation of the nmdc record
    """
    ## build record from the field names in the object dict
    ## note: $class_type is a special key that is ignored
    record_dict = {}
    for field_key, field in object_dict.items():
        if field_key != "$class_type":
            if type({}) == type(field):
                ## if the object value is a dict (e.g., {has_unit: {const: 'meter'}})
                ## then set the value to the dict's value
                ## needed if a field name conflicts with constant (e.g, if there was field named 'meter')
                if list(field.keys())[0] == "$const":
                    record_dict[field_key] = list(field.values())[0]
            else:
                ## get records value from nmdc record
                ## note: if the field is not in the nmdc record and return_field_if_none=True, the field is returned
                ## e.g., adding a constant or type: {has_raw_value: '10', type: QuantityValue}
                record_dict[field_key] = get_record_attr(
                    nmdc_record, field, return_field_if_none
                )

    return record_dict


def make_object_from_dict(nmdc_record: namedtuple, object_dict: dict):
    """
    Creates and returns an "object" based on nmdc_record.
    If the object_dict has a $class_type key, an instantiated object is returned.
    Otherwise, a dict is returned.

    Args:
        nmdc_record (namedtuple): the record that holds the data
        object_dict (dict): the dict that specifies the field/data (key/value) pairings

    Returns:
        an object built from the record and object_dict information
    """
    record_dict = make_record_dict(nmdc_record, object_dict)

    if "$class_type" in object_dict.keys():
        class_type = make_nmdc_class(object_dict["$class_type"])
        obj = class_type(**record_dict)  # build object
    else:
        obj = record_dict

    return obj


def make_object_from_list_item_dict(nmdc_record: namedtuple, item: dict) -> list:
    """
    When the item in the list is a dict; e.g.;
      [{id: 'gold_id, int', name: project_name, $class_type: Study}]
    A list of objects is returned that were created from the keys
    in the dict.

    This function is called from make_object_from_list.

    Args:
        nmdc_record (namedtuple): the record that holds the data values
        item (dict): holds the information needed to build the object

    Returns:
        list: holds objects built from data in the record
    """
    ## set split value for values in dict (globally)
    if "$spit_val" in item.keys():
        split_val = item.pop("$split_val")
    else:
        split_val = ","

    ## get class type if prestent
    if "$class_type" in item.keys():
        class_type = item.pop("$class_type")
        class_type = make_nmdc_class(class_type)  # convert to a type
    else:
        class_type = None

    ## get list of record values from nmdc record and split
    ## e.g., [{id: 'gold_id, int', name: project_name, $class_type: Study}]
    ## -> [['gold:001', 'gold:0002'], ['name 1', 'name 2']]
    record_values = []
    for field_name in item.values():
        ## get value in nmdc record
        val = get_record_attr(nmdc_record, field_name, return_field_if_none=False)

        if val is not None:
            dtype = get_dtype_from_attribute_field(field_name)  # determine data type

            ## check for local spit val; e.g., [{id: {$field: 'gold_id, int', $split_val:'|'}}
            mysplit = (
                field_name["$split_val"]
                if type({}) == type(field_name) and "$split_val" in field_name.keys()
                else split_val
            )

            rv = [coerce_value(v.strip(), dtype) for v in str(val).split(mysplit)]
            record_values.append(rv)
        else:
            record_values.append([None])

    ## get list of keys from item
    keys = [key for key in item.keys() if key != "$class_type"]

    ## build list of objects
    ## this works by using zip build dictionary using the keys and record values
    ## first the values are zipped/paired/collated; e.g.:
    ## zip(*[['gold:001', 'gold:0002'], ['name 1', 'name 2']])
    ## -> [['gold:001', 'name 1'], ['gold:002', 'name 2']]
    ## then the keys are zipped as a dict to the values; e.g.:
    ## dict(zip(['id', 'name'], [['gold:001', 'name 1'], ['gold:002', 'name 2']]))
    ## -> [{id: gold:001, name: 'name 1'}, {id: gold:002, name: 'name 2'}]
    obj_list = []
    for rv in zip_longest(*record_values):
        obj_dict = dict(zip(keys, rv))

        if class_type is not None:
            ## add the instantiated object to the list; e.g. obj_list.append(Study(id='gold:001'))
            obj_list.append(class_type(**obj_dict))
        else:
            ## simply add the object; e.g., obj_list.append({id: gold:001, name: name1})
            obj_list.append(obj_dict)

    return obj_list


def make_value_from_list_item_dict(nmdc_record: namedtuple, item: dict) -> list:
    """
    When the item in the list is a dict; e.g.;
      [{$field: 'data_object_id, int'}]
      [{$field: 'data_object_id, int', $split=','}]
    A list of values is returned that were created from the keys
    in the dict.

    This function is called from make_object_from_list.

    Args:
        nmdc_record (namedtuple): the record that holds the data values
        item (dict): holds the information needed to build the object

    Returns:
        list: values retrieved from data in the record
    """
    # ****** add info to documentation ********
    dtype = get_dtype_from_attribute_field(item["$field"])

    ## set value to split on
    if "$split_val" in item.keys():
        split_val = item["$split_val"]
    else:
        split_val = ","

    ## e.g., [{$field: data_object_id, $split=','}]
    ## get record value for the field
    ## returns None if the field is not in record
    if "$const" in item.keys():
        return [coerce_value(item["$const"], dtype)]
    elif "$field" in item.keys():
        record_val = get_record_attr(
            nmdc_record, item["$field"], return_field_if_none=False
        )
    else:
        record_val = None

    ## check the record value is not None
    if record_val is not None:
        ## check if record needs to be split
        if split_val is not None:
            # make sure record_val is a string, needed for splitting
            if type(record_val) != type(""):
                record_val = str(record_val)

            return [
                coerce_value(rv.strip(), dtype) for rv in record_val.split(split_val)
            ]
        else:
            return [coerce_value(record_val.strip(), dtype)]
    else:
        return [None]  # note: a list is returned


def make_object_from_list(nmdc_record: namedtuple, nmdc_list: list) -> list:
    """
    When a list is specified as the value of a field; e.g.:
      ['gold_id, str']
      {$field: data_object_id, $split=','}]
      [{id: gold_id, name: project_name, $class_type: Study}]
    A list of items (either values objects) is returned.

    Args:
        nmdc_record (namedtuple): [description]
        nmdc_list (list): [description]

    Returns:
        list: [description]
    """
    obj_list = []
    for val in nmdc_list:
        if type({}) == type(val):
            if "$field" in val.keys():
                ## e.g., [{$field: data_object_id, $split=','}]
                obj_list.extend(make_value_from_list_item_dict(nmdc_record, val))
            else:
                ## e.g., [{id: gold_id, name: project_name, $class_type: Study}]
                obj_list.extend(make_object_from_list_item_dict(nmdc_record, val))
        else:
            ## e.g., ['gold_id, str']
            dtype = get_dtype_from_attribute_field(val)  # determine the data type
            record_val = get_record_attr(nmdc_record, val)
            if record_val is not None:
                obj_list.extend(
                    [
                        coerce_value(rv.strip(), dtype)
                        for rv in str(record_val).split(",")
                    ]
                )
            else:
                obj_list.append(None)

    return obj_list


def dataframe_to_dict(
    nmdc_df: pds.DataFrame,
    nmdc_class,
    constructor_map={},
    attribute_fields=[],
    attribute_map={},
    transform_map={},
) -> list:
    """
    This is the main interface for the module.
    The nmdc dataframe (nmdc_df) is transformed and returned as a list of dicts.

    Args:
        nmdc_df (pds.DataFrame): the Pandas dataframe to be transformed
        nmdc_class: the NMDC class used to build objects
        constructor_map (dict, optional): specifies constructor arguments need to build the object; defaults to {}
        attribute_fields (list, optional): specifies which data fields to use as properties/keys; defaults to []
        attribute_map (dict, optional): maps data fields to MIxS (or other standard) fields; defaults to {}
        transform_map (dict, optional): specfies pre/post transformations to preform on the data; defaults to {}

    Returns:
        list: list of dicts that represent hte dataframe
    """

    def make_nmdc_object(nmdc_record: namedtuple, nmdc_class):
        """
        Creates an object from the nmdc records of the type nmdc_class.

        Args:
            nmdc_record (namedtuple): the records that holds the data
            nmdc_class ([type]): the class that the object will instantiate

        Returns:
            an object of the type specified by class_type
        """
        ## check for constructor_map  containing the paramaters necessary to instantiate the class
        if len(constructor_map) > 0:
            constructor_args = make_constructor_args_from_record(
                constructor_map, nmdc_record
            )
            nmdc_obj = nmdc_class(**constructor_args)
        else:
            nmdc_obj = nmdc_class()

        # print("****\n", nmdc_obj)

        nmdc_obj.type = (
            nmdc_class.class_class_curie
        )  ## add info about the type of entity it is

        ## get mappings for attribute fields
        for af in attribute_fields:
            nmdc_obj = set_nmdc_object(nmdc_obj, nmdc_record, attribute_map, af)

        return nmdc_obj

    ## create transform kwargs and pre and post transform lists
    tx_kwargs = {
        "nmdc_class": nmdc_class,
        "constructor_map": constructor_map,
        "attribute_fields": attribute_fields,
        "attribute_map": attribute_map,
    }
    pre_transforms = transform_map["pre"] if "pre" in transform_map.keys() else []
    post_transforms = transform_map["post"] if "post" in transform_map.keys() else []

    ## execute specified pre transformations; note: this transforms the dataframe
    for transform in pre_transforms:
        tx_function = eval(transform["function"])  # dynamically load function
        tx_attributes = transform["attributes"]  # get list of attibutes

        ## apply transform funciton
        nmdc_df = tx_function(nmdc_df, tx_attributes)

    ## transform each record into an nmdc object and store in list
    ## NB: SSSOM mapping is performed during this step
    nmdc_objs = [
        make_nmdc_object(record, nmdc_class)
        for record in nmdc_df.itertuples(index=False)
    ]

    ## set value to None for fields that have dicts as values
    ## but not an id or has_raw_value key
    ## this needed in case conversions resulted in junk values
    for obj in nmdc_objs:
        for key, val in obj.__dict__.items():
            if type(val) == type({}):
                if (not "id" in val.keys()) and (not "has_raw_value" in val.keys()):
                    obj.__dict__[key] = None

    ## execute specified post transformations; note: this transforms the nmdc objects
    for transform in post_transforms:
        tx_function = eval(transform["function"])  # dynamically load function
        tx_attributes = transform["attributes"]  # get list of attibutes

        ## apply transform funciton
        nmdc_objs = tx_function(nmdc_objs, tx_attributes, **tx_kwargs)

    ## transform each nmdc object in a dict and store in list
    nmdc_dicts = [make_dict_from_nmdc_obj(obj) for obj in nmdc_objs]

    ## return list of dicts
    return nmdc_dicts


def test_pre_transform(nmdc_df, tx_attributes, **kwargs):
    """
    Dummy function to test pre-transform declarations.
    """
    print("*** test pre-transform ******")
    return nmdc_df


def make_quantity_value(nmdc_objs: list, tx_attributes: list, **kwargs) -> list:
    """
    Takes each nmdc object (either a dict or class instance) and
    and adds has_numeric_value and has_unit information.


    Args:
        nmdc_objs (list): list of objects to be updated with has_numeric_value and/or c values
        tx_attributes (list): list of attributes whose values need to updated

    Returns:
        list: updated nmdc_objs with has_numeric_value and/or has_numeric_value values
    """
    print(f"*** executing make_quantity_value for attributes {tx_attributes}")
    for attribute in tx_attributes:
        for obj in nmdc_objs:
            if has_raw_value(obj, attribute):

                val = getattr(obj, attribute)
                # print("*** pre ***", val)

                ## split raw value after first space
                if type(val) == type({}):
                    value_list = str(val["has_raw_value"]).split(" ", 1)
                else:
                    value_list = str(getattr(val, "has_raw_value")).split(" ", 1)

                ## assign numeric quantity value
                if type(val) == type({}):
                    try:
                        val["has_numeric_value"] = float(value_list[0].strip())
                    except Exception as ex:
                        pass
                else:
                    try:
                        val.has_numeric_value = float(value_list[0].strip())
                    except Exception as ex:
                        pass

                ## assign unit if present
                if len(value_list) > 1:
                    if type(val) == type({}):
                        val["has_unit"] = value_list[1].strip()
                    else:
                        val.has_unit = value_list[1].strip()

                # print("*** post ***", val)

    return nmdc_objs


def make_iso_8601_date_value(nmdc_objs: list, tx_attributes: list, **kwargs) -> list:
    """
    Converts date values in ISO-8601 format.
    E.g., "30-OCT-14 12.00.00.000000000 AM" -> "30-OCT-14" is converted to "2014-10-14".

    Parameters
    ----------
    nmdc_objs : list
        List of objects to whose attributes will converted to ISO-8601 format.
    tx_attributes : list
        List of attributes whose values need to updated to ISO-8601 format.

    Returns
    -------
    list
        List of updated nmdc_objs with ISO-8601 formated strings as values.
    """
    print(f"*** executing make_iso_8601_date for attributes {tx_attributes}")
    for attribute in tx_attributes:
        for obj in nmdc_objs:
            # check if object has a date field (attribute)
            if hasattr(obj, attribute):
                # get the current date string value and return just the date part
                # e.g.: "30-OCT-14 12.00.00.000000000 AM" -> "30-OCT-14"
                date_str = str(getattr(obj, attribute)).split(" ", 1)[0]

                # convert date string in ISO-8601
                # e.g.: "30-OCT-14" -> "2014-10-14"
                if not (date_str is None) and date_str != "None":
                    try:
                        date_val = datetime.strptime(date_str, "%d-%b-%y").strftime(
                            "%Y-%m-%d"
                        )
                        setattr(obj, attribute, date_val)
                    except Exception as ex:
                        print(getattr(obj, "id"), f"property {attribute}", "error:", ex)

    return nmdc_objs


def get_json(file_path: str, replace_single_quote=False):
    """
    Returns a json object from the file specied by file_path.

    Args:
        file_path (sting): path file holding json
        replace_single_quote (bool, optional): specifies if "'" is replaced with '"'; defaults to False

    Returns:
        json object
    """
    ## load json
    with open(file_path, "r") as in_file:
        if replace_single_quote:  # json
            text = in_file.read()
            json_data = json.loads(text.replace("'", '"'))
        else:
            json_data = json.load(in_file)
    return json_data


def save_json(json_data: str, file_path):
    """
    Saves json_data to file specified by file_path.

    Args:
        json_data: json data
        file_path (sting): path to where json is saved

    Returns:
        [type]: [description]
    """
    ## if json data is a string, it will need to be
    ## loaded into a variable to for "\" escape characters
    if type(json_data) == type(""):
        json_data = json.loads(json_data)

    ## save json with changed data types
    with open(file_path, "w") as out_file:
        json.dump(json_data, out_file, indent=2)
    return json_data


if __name__ == "__main__":
    ## code for testing
    file_path = "../output/nmdc_etl/test.json"
    # test_json = collapse_json_file(file_path, 'part_of')
    # test_json = collapse_json_file(file_path, 'has_input')
    test_json = collapse_json_file(file_path, "has_output")
    print(test_json)
