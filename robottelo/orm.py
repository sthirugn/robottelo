"""Module that define the model layer used to define entities"""
import booby
import booby.fields
import booby.inspection
import booby.validators
import collections


class Entity(booby.Model):
    """A logical representation of a Foreman entity.

    This class is rather useless as is, and it is intended to be subclassed.
    Subclasses can specify two useful types of information:

    * fields
    * metadata

    Fields are represented by setting class attributes, and metadata is
    represented by settings attributes on the inner class named ``Meta``.

    """
    class Meta(object):
        """Non-field information about this entity.

        Examples of information which can be set on this class are the
        ``api_names`` and ``cli_names`` dicts. See :mod:`robottelo.factories`
        for details.

        """

    @classmethod
    def get_fields(cls):
        """Return all defined fields as a dictionary.

        :return: A dictionary mapping ``str`` field names to ``robottelo.orm``
            field types.
        :rtype: dict

        """
        return booby.inspection.get_fields(cls)


# Wrappers for booby fields
class BooleanField(booby.fields.Boolean):
    """Field that represents a boolean"""


class EmailField(booby.fields.Email):
    """Field that represents a boolean"""


class Field(booby.fields.Field):
    """Base field class to implement other fields"""


class FloatField(booby.fields.Float):
    """Field that represents a float"""


class IntegerField(booby.fields.Integer):
    """Field that represents an integer"""


class StringField(booby.fields.String):
    """Field that represents a string"""


# Additional fields
class IPAddressField(StringField):
    """Field that represents an IP adrress"""


class MACAddressField(StringField):
    """Field that represents a MAC adrress"""


class OneToOneField(booby.fields.Embedded):
    """Field that represents a one to one related entity"""


class OneToManyField(Field):
    """Field that represents a one to many related entity

    The value could be a single or a list of entities, or a dictionary or even
    a list of dictionaries.

     Examples of how to set OneToManyField value::

        >>> class OneEntity(Entity):
        ...     name = StringField()
        ...
        >>> class OtherEntity(Entity):
        ...     ones = OneToManyField(OneEntity)
        ...
        >>> ent.ones = OneEntity(name='name')
        >>> ent.ones
        [<__main__.OneEntity(name='name')>]
        >>> ent.ones = [OneEntity(name='name')]
        >>> ent.ones
        [<__main__.OneEntity(name='name')>]
        >>> ent.ones = {'name': 'test'}
        >>> ent.ones
        [<__main__.OneEntity(name='test')>]
        >>> ent.ones = [{'name': 'test'}]
        >>> ent.ones
        [<__main__.OneEntity(name='test')>]

    All examples shows that the value will be converted to a list of a model
    entities.

    """

    def __init__(self, model, *args, **kwargs):
        super(OneToManyField, self).__init__(
            booby.validators.List(booby.validators.Model(model)),
            *args,
            **kwargs
        )

        self.model = model

    def __set__(self, instance, value):
        """Override __set__ to process the value before setting it.

        If the value is a single entity instance it is wrapped in a list.

        If the value is a dict convert to a self.model instance and wrap in a
        list.

        If the value is a list and have any dict on it, convert that dict to a
        self.model instance and override the dict on the list.
        """
        if isinstance(value, self.model):
            # if received a single instance wraps it in a list
            value = [value]
        elif isinstance(value, collections.MutableMapping):
            # convert a dict to a self.model instance and wraps in a list
            value = [self.model(**value)]
        elif isinstance(value, collections.MutableSequence):
            # if an element in a list is a dict convert it to a self.model
            # instance
            for index, val in enumerate(value):
                if isinstance(val, collections.MutableMapping):
                    value[index] = self.model(**val)

        super(OneToManyField, self).__set__(instance, value)


class URLField(StringField):
    """Field that represents an URL"""