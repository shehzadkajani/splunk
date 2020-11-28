from __future__ import absolute_import
from abc import ABCMeta, abstractmethod
from rapid_diag.abstractstatic import abstractstatic
import re
from splunklib import six

INVALID_FILE_CHARS = r'[\\/:*?"<>|]'
PYTHON_ESCAPE_CHARS = r'[\n\t\r\x0b\x0c]'

class Serializable(six.with_metaclass(ABCMeta, object)):
    classes = {}

    @abstractmethod
    def toJsonObj(self):
        pass

    @abstractstatic
    def fromJsonObj(obj):
        pass

    @abstractstatic
    def validateJson(obj):
        pass

    @staticmethod
    def check_value_in_range(value, field_range, key):
        """Validates the value in given range

        Parameters
        ----------
        value : number
            Value of variable 
        field_range : array
            minimum and maximum bounds for the value
        key : string
            key of dict

        Raises
        ------
        ValueError
            raises exception when value doesn't fall in between the range
        """
        if value is not None and not(field_range[0] <= value <= field_range[1]):
            raise ValueError(str(key) + " : value should be at least " + str(field_range[0]) + " and at most " + str(field_range[1]) + ".")

    @staticmethod
    def check_data_type(value, data_type, key):
        """Validates data type of value

        Parameters
        ----------
        value : any
            value of variable
        data_type : tuple
             valid data types for value
        key : string
            key of dict

        Raises
        ------
        TypeError
            raises exception when value doesn't have valid data type
        """
        if not(isinstance(value, data_type)):
            raise TypeError(str(key) + ": Invalid data type, expected " + ' or '.join(list(map(lambda dt: dt.__name__, data_type))) + " .")

    @staticmethod
    def check_string_value(value, key):
        """method check if string contains any invalid characters or vulnerable code 

        Parameters
        ----------
        value : [string]
            value of the field
        key : [string]
            name of field

        Raises
        ------
        ValueError
            if string contains invalid chars
        """

        if re.search(INVALID_FILE_CHARS, value):
            raise ValueError(str(value) + " " + str(type(value)) + ": contains invalid character(s).")

        if re.search(PYTHON_ESCAPE_CHARS, value):
            raise ValueError(str(key) + ": contains invalid escape character(s).")

        if value == '.' or value == '..':
            raise ValueError(str(key) + ": contains invalid character(s).")

    @staticmethod
    def register(klass):
        classSpec = klass.__module__ + '.' + klass.__name__
        Serializable.classes[classSpec] = klass

    @staticmethod
    def jsonDecode(jsonDict):
        if '__class__' not in jsonDict or jsonDict['__class__'] not in Serializable.classes:
            raise Exception("Error decoding the json object " + str(jsonDict))
        Serializable.classes[jsonDict['__class__']].validateJson(jsonDict)
        return Serializable.classes[jsonDict['__class__']].fromJsonObj(jsonDict)

    @staticmethod
    def jsonEncode(obj):
        if callable(getattr(obj, "toJsonObj", None)):
            jsonObj = obj.toJsonObj()
            classSpec = obj.__class__.__module__ + '.' + obj.__class__.__name__
            if '__class__' in jsonObj and jsonObj['__class__']!=classSpec:
                raise TypeError('Invalid __class__={!s} for object of type "{!s}"'.format(jsonObj['__class__'], classSpec))
            jsonObj['__class__'] = classSpec
            return jsonObj
        raise TypeError('Can\'t serialize "{!s}"={!s}'.format(type(obj), obj))
